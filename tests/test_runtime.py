from pathlib import Path

from atlas.runtime import EventStore, EventStoreIntegrityError, Runtime, TaskState, ToolSpec, TransitionError


def test_illegal_transition_is_refused(tmp_path: Path):
    runtime = Runtime(EventStore(tmp_path / "events.jsonl"))
    task = runtime.submit("demo", "task-1")
    try:
        runtime.move(task.task_id, TaskState.COMPLETED)
    except TransitionError:
        pass
    else:
        raise AssertionError("queued task was allowed to complete")


def test_approval_gate_and_restart_recovery(tmp_path: Path):
    event_path = tmp_path / "events.jsonl"
    runtime = Runtime(EventStore(event_path), [ToolSpec("publish", side_effect=True, requires_approval=True)])
    task = runtime.submit("publish", "task-2")
    runtime.move(task.task_id, TaskState.RUNNING, "started")
    try:
        runtime.call_tool(task.task_id, "publish", lambda: "done")
    except PermissionError:
        pass
    else:
        raise AssertionError("side effect ran before approval")
    assert runtime.tasks["task-2"].state is TaskState.WAITING_FOR_APPROVAL
    recovered = Runtime(EventStore(event_path), [ToolSpec("publish", side_effect=True, requires_approval=True)])
    assert recovered.tasks["task-2"].state is TaskState.WAITING_FOR_APPROVAL
    recovered.approve("task-2", "publish")
    assert recovered.call_tool("task-2", "publish", lambda: "done") == "done"


def test_tool_and_approval_events_have_monotonic_sequences(tmp_path: Path):
    event_path = tmp_path / "events.jsonl"
    runtime = Runtime(EventStore(event_path), [ToolSpec("publish", side_effect=True, requires_approval=True)])
    task = runtime.submit("publish", "task-3")
    runtime.move(task.task_id, TaskState.RUNNING)
    try:
        runtime.call_tool(task.task_id, "publish", lambda: "never")
    except PermissionError:
        pass
    runtime.approve(task.task_id, "publish")
    runtime.call_tool(task.task_id, "publish", lambda: "done")
    assert [event.sequence for event in task.events] == sorted({event.sequence for event in task.events})
    recovered = Runtime(EventStore(event_path), [ToolSpec("publish", side_effect=True, requires_approval=True)])
    assert "publish" in recovered.tasks["task-3"].approved_tools
    assert recovered.tasks["task-3"].sequence == task.sequence


def test_receipt_is_deterministic_and_content_addressed(tmp_path: Path):
    runtime = Runtime(EventStore(tmp_path / "events.jsonl"))
    task = runtime.submit("demo", "task-4")
    runtime.move(task.task_id, TaskState.RUNNING, "started")
    first = runtime.receipt(task.task_id)
    second = runtime.receipt(task.task_id)
    assert first == second
    assert first["schema"] == "atlas-receipt/v1"
    assert len(first["receipt_sha256"]) == 64


def test_approval_cannot_admit_unknown_or_non_gated_tools(tmp_path: Path):
    runtime = Runtime(
        EventStore(tmp_path / "events.jsonl"),
        [ToolSpec("publish", side_effect=True, requires_approval=True), ToolSpec("inspect")],
    )
    task = runtime.submit("publish", "task-5")
    runtime.move(task.task_id, TaskState.RUNNING)
    try:
        runtime.call_tool(task.task_id, "publish", lambda: "never")
    except PermissionError:
        pass
    for tool, expected in (("missing", KeyError), ("inspect", PermissionError)):
        try:
            runtime.approve(task.task_id, tool)
        except expected:
            pass
        else:
            raise AssertionError(f"approval admitted {tool}")
    assert task.approved_tools == set()


def test_recovery_rejects_corrupt_event_sequence(tmp_path: Path):
    event_path = tmp_path / "events.jsonl"
    runtime = Runtime(EventStore(event_path), [ToolSpec("publish", requires_approval=True)])
    task = runtime.submit("demo", "task-corrupt")
    runtime.move(task.task_id, TaskState.RUNNING)
    try:
        runtime.call_tool(task.task_id, "publish", lambda: "never")
    except PermissionError:
        pass
    rows = event_path.read_text(encoding="utf-8").splitlines()
    rows[1] = rows[1].replace('"sequence": 2', '"sequence": 4')
    event_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    try:
        Runtime(EventStore(event_path))
    except EventStoreIntegrityError as exc:
        assert "non-contiguous sequence" in str(exc)
    else:
        raise AssertionError("corrupt event sequence was silently recovered")


def test_recovery_rejects_impossible_state_transition(tmp_path: Path):
    event_path = tmp_path / "events.jsonl"
    runtime = Runtime(EventStore(event_path))
    task = runtime.submit("demo", "task-transition-corrupt")
    runtime.move(task.task_id, TaskState.RUNNING)
    rows = event_path.read_text(encoding="utf-8").splitlines()
    rows[0] = rows[0].replace('"state": "running"', '"state": "completed"')
    event_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    try:
        Runtime(EventStore(event_path))
    except EventStoreIntegrityError as exc:
        assert "invalid recovered transition" in str(exc)
    else:
        raise AssertionError("impossible recovered transition was accepted")


def test_event_append_is_immediately_recoverable(tmp_path: Path):
    event_path = tmp_path / "events.jsonl"
    runtime = Runtime(EventStore(event_path))
    task = runtime.submit("demo", "task-durable")
    runtime.move(task.task_id, TaskState.RUNNING)
    recovered = Runtime(EventStore(event_path))
    assert recovered.tasks[task.task_id].state is TaskState.RUNNING
