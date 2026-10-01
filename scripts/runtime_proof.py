from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.runtime import EventStore, Runtime, TaskState, ToolSpec


with TemporaryDirectory() as directory:
    path = Path(directory) / "events.jsonl"
    runtime = Runtime(EventStore(path), [ToolSpec("publish", side_effect=True, requires_approval=True)])
    task = runtime.submit("publish fixture", "proof-task")
    runtime.move(task.task_id, TaskState.RUNNING, "started")
    try:
        runtime.call_tool(task.task_id, "publish", lambda: "published")
    except PermissionError:
        pass
    runtime = Runtime(EventStore(path), [ToolSpec("publish", side_effect=True, requires_approval=True)])
    assert runtime.tasks["proof-task"].state is TaskState.WAITING_FOR_APPROVAL
    runtime.approve("proof-task", "publish")
    assert runtime.call_tool("proof-task", "publish", lambda: "published") == "published"
    runtime = Runtime(EventStore(path), [ToolSpec("publish", side_effect=True, requires_approval=True)])
    assert "publish" in runtime.tasks["proof-task"].approved_tools
    runtime.move("proof-task", TaskState.COMPLETED, "published")
    assert runtime.tasks["proof-task"].state is TaskState.COMPLETED

print("atlas approval/recovery proof: PASS")
