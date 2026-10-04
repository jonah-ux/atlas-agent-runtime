import json
from pathlib import Path
import tempfile
import unittest

from atlas.interop import project_receipt, validate_receipt
from atlas.runtime import EventStore, Runtime, TaskState, ToolSpec


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "agent-systems-lab"


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


def failed_receipt(root: Path):
    runtime = Runtime(EventStore(root / "failed.jsonl"))
    task = runtime.submit("synthetic request", "failed-task")
    runtime.move(task.task_id, TaskState.RUNNING, "start")
    runtime.move(task.task_id, TaskState.FAILED, "fixture failure")
    return runtime.receipt(task.task_id)


class ConsumerConformanceTest(unittest.TestCase):
    def test_owner_manifest_matches_producer_schema_boundaries(self):
        path = Path(__file__).parents[1] / "conformance" / "agent-systems-lab.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            receipt = completed_receipt(Path(directory))
            evidence = project_receipt(
                receipt, evidence_id="fixture:owner-manifest", created_at="2026-01-01T00:00:00Z",
                subject="Synthetic", summary="Producer boundary", fixture="agent-systems-lab",
            )
        self.assertEqual(manifest["owner"], "atlas-agent-runtime")
        self.assertCountEqual(manifest["native_schemas"], [receipt["schema"], evidence["schema"]])
        for test_path in manifest["tests"]:
            self.assertTrue((Path(__file__).parents[1] / test_path).is_file())
        self.assertTrue((Path(__file__).parents[1] / manifest["consumer_manifest"]).is_file())

    def test_corpus_manifest_names_the_forgeyard_owner(self):
        path = FIXTURE_ROOT / "conformance.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["owner_corpus"], "forgeyard/conformance")
        self.assertEqual(manifest["schema"], "agent-systems-lab-consumer-conformance/v1")
        self.assertEqual(manifest["owner_manifest"], "forgeyard-conformance/manifest.json")
        self.assertRegex(manifest["owner_revision"], r"^[0-9a-f]{40}$")

    def test_forgeyard_owner_corpus_is_mirrored(self):
        root = FIXTURE_ROOT / "forgeyard-conformance"
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "forgeyard-conformance-manifest/v1")
        self.assertEqual(manifest["contract"], "ai-work-evidence/v1")
        self.assertEqual(
            [case["name"] for case in manifest["cases"]],
            [
                "valid-observed",
                "status-unknown",
                "status-failed",
                "unknown-version",
                "unsafe-artifact",
                "bad-hash",
                "malformed",
            ],
        )
        for case in manifest["cases"]:
            self.assertTrue((root / case["file"]).is_file(), case["file"])

    def test_completed_queued_and_failed_receipts_match_corpus(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = completed_receipt(root)
            observed = project_receipt(completed, evidence_id="fixture:complete", created_at="2026-01-01T00:00:00Z", subject="Synthetic", summary="Fixture", fixture="agent-systems-lab")
            queued_runtime = Runtime(EventStore(root / "queued.jsonl"))
            queued = queued_runtime.submit("synthetic request", "queued-task")
            unknown = project_receipt(queued_runtime.receipt(queued.task_id), evidence_id="fixture:queued", created_at="2026-01-01T00:00:00Z", subject="Synthetic", summary="Fixture", fixture="agent-systems-lab")
            failed = project_receipt(failed_receipt(root), evidence_id="fixture:failed", created_at="2026-01-01T00:00:00Z", subject="Synthetic", summary="Fixture", fixture="agent-systems-lab")
        self.assertEqual(observed["status"], "observed")
        self.assertEqual(unknown["status"], "unknown")
        self.assertEqual(failed["status"], "failed")

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
