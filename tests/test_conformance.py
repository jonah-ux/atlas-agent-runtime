import json
from pathlib import Path
import tempfile
import unittest

from atlas.interop import project_receipt, validate_receipt
from atlas.runtime import EventStore, Runtime, TaskState, ToolSpec


def completed_receipt(root: Path):
    runtime = Runtime(EventStore(root / "events.jsonl"), [ToolSpec("publish", requires_approval=True)])
    task = runtime.submit("synthetic request", "fixture-task")
    runtime.move(task.task_id, TaskState.RUNNING, "start")
    try:
        runtime.call_tool(task.task_id, "publish", lambda: "ok")
    except PermissionError:
        pass
    runtime.approve(task.task_id, "publish")
    runtime.call_tool(task.task_id, "publish", lambda: "ok")
    runtime.move(task.task_id, TaskState.COMPLETED, "done")
    return runtime.receipt(task.task_id)


class ConsumerConformanceTest(unittest.TestCase):
    def test_corpus_manifest_names_the_forgeyard_owner(self):
        path = Path(__file__).parent / "fixtures" / "agent-systems-lab" / "conformance.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["owner_corpus"], "forgeyard/conformance")
        self.assertEqual(manifest["schema"], "agent-systems-lab-consumer-conformance/v1")

    def test_completed_and_queued_receipts_match_corpus(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = completed_receipt(root)
            observed = project_receipt(completed, evidence_id="fixture:complete", created_at="2026-01-01T00:00:00Z", subject="Synthetic", summary="Fixture", fixture="agent-systems-lab")
            queued_runtime = Runtime(EventStore(root / "queued.jsonl"))
            queued = queued_runtime.submit("synthetic request", "queued-task")
            unknown = project_receipt(queued_runtime.receipt(queued.task_id), evidence_id="fixture:queued", created_at="2026-01-01T00:00:00Z", subject="Synthetic", summary="Fixture", fixture="agent-systems-lab")
        self.assertEqual(observed["status"], "observed")
        self.assertEqual(unknown["status"], "unknown")

    def test_tampered_receipt_and_unknown_schema_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = completed_receipt(Path(directory))
        receipt["events"][0]["detail"] = "tampered"
        with self.assertRaises(ValueError):
            validate_receipt(receipt)
        unknown = dict(receipt)
        unknown["schema"] = "atlas-receipt/v2"
        with self.assertRaises(ValueError):
            validate_receipt(unknown)
