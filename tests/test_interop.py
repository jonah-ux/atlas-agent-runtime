import hashlib
import json
from pathlib import Path

import pytest

from atlas.interop import canonical_receipt_bytes, project_receipt, validate_receipt
from atlas.runtime import EventStore, Runtime, TaskState, ToolSpec


def completed_receipt(tmp_path: Path):
    runtime = Runtime(EventStore(tmp_path / "events.jsonl"), [ToolSpec("publish", side_effect=True, requires_approval=True)])
    task = runtime.submit("publish synthetic fixture", "fixture-task")
    runtime.move(task.task_id, TaskState.RUNNING, "start")
    with pytest.raises(PermissionError):
        runtime.call_tool(task.task_id, "publish", lambda: "published")
    runtime.approve(task.task_id, "publish")
    runtime.call_tool(task.task_id, "publish", lambda: "published")
    runtime.move(task.task_id, TaskState.COMPLETED, "done")
    return runtime.receipt(task.task_id)


def test_receipt_projects_without_copying_event_details(tmp_path: Path):
    receipt = completed_receipt(tmp_path)
    evidence = project_receipt(receipt, evidence_id="fixture-task:001", created_at="2026-01-01T00:00:00Z", subject="Synthetic approval", summary="A bounded approval recovery fixture", fixture="portfolio-suite-v2")
    assert evidence["schema"] == "ai-work-evidence/v1"
    assert evidence["source"] == "atlas"
    assert evidence["status"] == "observed"
    assert "publish synthetic fixture" not in json.dumps(evidence)
    assert "done" not in json.dumps(evidence)
    artifact = evidence["artifacts"][0]
    assert artifact["sha256"] == hashlib.sha256(canonical_receipt_bytes(receipt)).hexdigest()


def test_receipt_validation_rejects_tampering(tmp_path: Path):
    receipt = completed_receipt(tmp_path)
    receipt["events"][0]["detail"] = "tampered"
    with pytest.raises(ValueError, match="digest"):
        validate_receipt(receipt)


@pytest.mark.parametrize("created_at", ["2026-01-01", "2026-01-01T00:00:00+00:00"])
def test_projection_requires_explicit_utc_timestamp(tmp_path: Path, created_at: str):
    with pytest.raises(ValueError, match="RFC 3339 UTC"):
        project_receipt(completed_receipt(tmp_path), evidence_id="fixture-task:002", created_at=created_at, subject="Synthetic", summary="Fixture", fixture="portfolio-suite-v2")


def test_incomplete_receipt_does_not_claim_verified(tmp_path: Path):
    runtime = Runtime(EventStore(tmp_path / "events.jsonl"))
    task = runtime.submit("synthetic", "queued-task")
    evidence = project_receipt(runtime.receipt(task.task_id), evidence_id="queued-task", created_at="2026-01-01T00:00:00Z", subject="Synthetic", summary="Fixture", fixture="portfolio-suite-v2")
    assert evidence["status"] == "unknown"
