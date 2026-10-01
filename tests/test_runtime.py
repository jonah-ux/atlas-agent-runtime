from pathlib import Path

from atlas.runtime import EventStore, Runtime, TaskState, ToolSpec, TransitionError


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
