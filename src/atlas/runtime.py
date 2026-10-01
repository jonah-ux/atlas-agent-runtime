"""A dependency-free durable task state machine for the Atlas baseline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import json
import hashlib
from pathlib import Path
from typing import Any, Callable
import uuid


class TaskState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TransitionError(ValueError):
    """Raised when a task attempts an illegal lifecycle transition."""


class EventStoreIntegrityError(ValueError):
    """Raised when persisted lifecycle evidence cannot be replayed safely."""


_ALLOWED: dict[TaskState, set[TaskState]] = {
    TaskState.QUEUED: {TaskState.RUNNING, TaskState.CANCELLED},
    TaskState.RUNNING: {TaskState.WAITING_FOR_APPROVAL, TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.WAITING_FOR_APPROVAL: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    side_effect: bool = False
    requires_approval: bool = False


@dataclass(frozen=True)
class TaskEvent:
    task_id: str
    sequence: int
    kind: str
    state: TaskState
    detail: str = ""
    tool: str | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data


@dataclass
class Task:
    task_id: str
    request: str
    state: TaskState = TaskState.QUEUED
    sequence: int = 0
    events: list[TaskEvent] = field(default_factory=list)
    approved_tools: set[str] = field(default_factory=set)

    def transition(self, state: TaskState, detail: str = "") -> TaskEvent:
        if state not in _ALLOWED[self.state]:
            raise TransitionError(f"cannot transition {self.state.value} -> {state.value}")
        self.sequence += 1
        self.state = state
        event = TaskEvent(self.task_id, self.sequence, "state_changed", state, detail)
        self.events.append(event)
        return event

    def event(self, kind: str, detail: str = "", tool: str | None = None) -> TaskEvent:
        self.sequence += 1
        event = TaskEvent(self.task_id, self.sequence, kind, self.state, detail, tool)
        self.events.append(event)
        return event


class EventStore:
    """Append-only JSONL store; incomplete tasks can be reconstructed after restart."""

    def __init__(self, path: Path):
        self.path = path

    def append(self, event: TaskEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.as_dict(), sort_keys=True) + "\n")

    def read(self) -> list[TaskEvent]:
        if not self.path.exists():
            return []
        events: list[TaskEvent] = []
        expected_sequences: dict[str, int] = {}
        for line_number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                event = TaskEvent(**{**row, "state": TaskState(row["state"])})
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise EventStoreIntegrityError(f"invalid event at line {line_number}") from exc
            expected = expected_sequences.get(event.task_id, 0) + 1
            if event.sequence != expected:
                raise EventStoreIntegrityError(
                    f"non-contiguous sequence for {event.task_id}: expected {expected}, got {event.sequence}"
                )
            expected_sequences[event.task_id] = event.sequence
            events.append(event)
        return events


class Runtime:
    def __init__(self, store: EventStore, tools: list[ToolSpec] = ()):  # noqa: B008
        self.store = store
        self.tools = {tool.name: tool for tool in tools}
        self.tasks: dict[str, Task] = {}
        self.recover()

    def recover(self) -> None:
        for event in self.store.read():
            task = self.tasks.setdefault(event.task_id, Task(event.task_id, request="recovered"))
            task.state = event.state
            task.sequence = event.sequence
            task.events.append(event)
            if event.kind == "approval_granted" and event.tool:
                task.approved_tools.add(event.tool)

    def submit(self, request: str, task_id: str | None = None) -> Task:
        task = Task(task_id or f"task-{uuid.uuid4().hex[:12]}", request)
        if task.task_id in self.tasks:
            raise ValueError(f"task already exists: {task.task_id}")
        self.tasks[task.task_id] = task
        return task

    def move(self, task_id: str, state: TaskState, detail: str = "") -> TaskEvent:
        task = self.tasks[task_id]
        event = task.transition(state, detail)
        self.store.append(event)
        return event

    def call_tool(self, task_id: str, name: str, handler: Callable[[], str]) -> str:
        task = self.tasks[task_id]
        spec = self.tools.get(name)
        if spec is None:
            raise KeyError(f"unknown tool: {name}")
        if spec.requires_approval and name not in task.approved_tools:
            if task.state is not TaskState.WAITING_FOR_APPROVAL:
                self.move(task_id, TaskState.WAITING_FOR_APPROVAL, f"approval required for tool {name}")
            raise PermissionError(f"approval required for tool: {name}")
        self.store.append(task.event("tool_called", tool=name))
        return handler()

    def approve(self, task_id: str, tool: str) -> TaskEvent:
        task = self.tasks[task_id]
        if task.state is not TaskState.WAITING_FOR_APPROVAL:
            raise TransitionError("task is not waiting for approval")
        spec = self.tools.get(tool)
        if spec is None:
            raise KeyError(f"unknown tool: {tool}")
        if not spec.requires_approval:
            raise PermissionError(f"tool does not require approval: {tool}")
        task.approved_tools.add(tool)
        event = task.event("approval_granted", f"approved tool {tool}", tool=tool)
        self.store.append(event)
        self.move(task_id, TaskState.RUNNING, f"approved tool {tool}")
        return event

    def receipt(self, task_id: str) -> dict[str, Any]:
        """Return a deterministic, content-addressed lifecycle receipt."""

        task = self.tasks[task_id]
        events = [event.as_dict() for event in task.events]
        payload = {
            "schema": "atlas-receipt/v1",
            "task_id": task.task_id,
            "state": task.state.value,
            "event_count": len(events),
            "events": events,
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload["receipt_sha256"] = hashlib.sha256(canonical).hexdigest()
        return payload
