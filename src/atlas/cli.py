"""Noninteractive JSON CLI for the Atlas runtime baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .runtime import EventStore, Runtime, TaskState, ToolSpec


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atlas")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run a deterministic approval/recovery demo")
    demo.add_argument("--state", type=Path, required=True)
    receipt = sub.add_parser("receipt", help="emit a deterministic lifecycle receipt")
    receipt.add_argument("task_id")
    receipt.add_argument("--state", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "demo":
        runtime = Runtime(EventStore(args.state), [ToolSpec("publish", side_effect=True, requires_approval=True)])
        task = runtime.submit("publish the fixture result", "demo-task")
        runtime.move(task.task_id, TaskState.RUNNING, "worker started")
        try:
            runtime.call_tool(task.task_id, "publish", lambda: "published fixture")
        except PermissionError:
            runtime.approve(task.task_id, "publish")
        result = runtime.call_tool(task.task_id, "publish", lambda: "published fixture")
        runtime.move(task.task_id, TaskState.COMPLETED, result)
        print(json.dumps({"task_id": task.task_id, "state": task.state.value, "events": len(task.events)}))
        return 0
    if args.command == "receipt":
        runtime = Runtime(EventStore(args.state), [ToolSpec("publish", side_effect=True, requires_approval=True)])
        try:
            print(json.dumps(runtime.receipt(args.task_id), ensure_ascii=False, sort_keys=True))
        except KeyError:
            print(json.dumps({"schema": "atlas-receipt/v1", "error": "task not found", "task_id": args.task_id}))
            return 1
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
