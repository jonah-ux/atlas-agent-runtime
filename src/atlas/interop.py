"""Project durable Atlas receipts into the portfolio evidence contract."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Any, Mapping

from .runtime import TaskState, _ALLOWED


SCHEMA = "ai-work-evidence/v1"
RECEIPT_SCHEMA = "atlas-receipt/v1"
_STATUSES = frozenset({"observed", "verified", "failed", "unknown"})
_RECEIPT_KEYS = {"schema", "task_id", "state", "event_count", "events", "receipt_sha256"}
_EVENT_KEYS = {"task_id", "sequence", "kind", "state", "detail", "tool"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_receipt_bytes(receipt: Mapping[str, Any]) -> bytes:
    """Return the full receipt representation used as the interop artifact."""

    validate_receipt(receipt)
    return _canonical(receipt) + b"\n"


def validate_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Validate receipt integrity and replay its lifecycle semantics."""

    if not isinstance(receipt, Mapping) or set(receipt) != _RECEIPT_KEYS:
        raise ValueError("Atlas receipt has an unexpected shape")
    if receipt["schema"] != RECEIPT_SCHEMA:
        raise ValueError("unsupported Atlas receipt schema")
    task_id = receipt["task_id"]
    if not isinstance(task_id, str) or not _SAFE_ID.fullmatch(task_id):
        raise ValueError("Atlas receipt task_id is invalid")
    state = receipt["state"]
    try:
        final_state = TaskState(state)
    except ValueError as exc:
        raise ValueError("Atlas receipt state is invalid") from exc
    events = receipt["events"]
    count = receipt["event_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0 or not isinstance(events, list) or count != len(events):
        raise ValueError("Atlas receipt event_count does not match events")
    current = TaskState.QUEUED
    for expected_sequence, event in enumerate(events, start=1):
        if not isinstance(event, Mapping) or set(event) != _EVENT_KEYS:
            raise ValueError("Atlas receipt event has an unexpected shape")
        if event["task_id"] != task_id or event["sequence"] != expected_sequence:
            raise ValueError("Atlas receipt event identity or sequence is invalid")
        try:
            event_state = TaskState(event["state"])
        except ValueError as exc:
            raise ValueError("Atlas receipt event state is invalid") from exc
        if not isinstance(event["kind"], str) or not isinstance(event["detail"], str):
            raise ValueError("Atlas receipt event fields are invalid")
        tool = event["tool"]
        if tool is not None and (not isinstance(tool, str) or not tool.strip() or not _SAFE_ID.fullmatch(tool)):
            raise ValueError("Atlas receipt event tool is invalid")
        kind = event["kind"]
        if kind == "state_changed":
            if event_state not in _ALLOWED[current]:
                raise ValueError("Atlas receipt contains an illegal state transition")
            current = event_state
        elif kind == "approval_granted":
            if current is not TaskState.WAITING_FOR_APPROVAL or not tool:
                raise ValueError("Atlas receipt contains an invalid approval event")
        elif kind == "tool_called":
            if current is not TaskState.RUNNING or not tool:
                raise ValueError("Atlas receipt contains an invalid tool event")
        else:
            raise ValueError("Atlas receipt contains an unknown event kind")
        if event_state is not current and kind != "approval_granted":
            raise ValueError("Atlas receipt event state does not match replay state")
    if current is not final_state:
        raise ValueError("Atlas receipt final state does not match replay")
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    expected_digest = hashlib.sha256(_canonical(unsigned)).hexdigest()
    if not isinstance(receipt["receipt_sha256"], str) or not _SHA256.fullmatch(receipt["receipt_sha256"]) or receipt["receipt_sha256"] != expected_digest:
        raise ValueError("Atlas receipt digest is invalid")
    return dict(receipt)


def project_receipt(
    receipt: Mapping[str, Any],
    *,
    evidence_id: str,
    created_at: str,
    subject: str,
    summary: str,
    fixture: str,
    source_version: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Produce metadata plus hashes; receipt events and request text stay private to Atlas."""

    normalized = validate_receipt(receipt)
    _validate_metadata(evidence_id, created_at, subject, summary, fixture)
    final_state = TaskState(normalized["state"])
    derived_status = "observed" if final_state is TaskState.COMPLETED else "failed" if final_state in {TaskState.FAILED, TaskState.CANCELLED} else "unknown"
    chosen_status = status or derived_status
    if chosen_status not in _STATUSES:
        raise ValueError("Atlas interop status is invalid")
    artifact_bytes = canonical_receipt_bytes(normalized)
    return {
        "schema": SCHEMA,
        "evidence_id": evidence_id,
        "source": "atlas",
        "source_version": source_version or _package_version(),
        "created_at": created_at,
        "subject": subject,
        "summary": summary,
        "artifacts": [{"name": "atlas-receipt", "size": len(artifact_bytes), "sha256": hashlib.sha256(artifact_bytes).hexdigest()}],
        "provenance": {"fixture": fixture, "receipt_sha256": normalized["receipt_sha256"]},
        "status": chosen_status,
    }


def _validate_metadata(evidence_id: str, created_at: str, subject: str, summary: str, fixture: str) -> None:
    for label, value in (("evidence_id", evidence_id), ("fixture", fixture)):
        if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
            raise ValueError(f"Atlas interop {label} is invalid")
    for label, value in (("subject", subject), ("summary", summary)):
        if not isinstance(value, str) or not value.strip() or len(value) > 2048 or any(ord(char) < 32 for char in value):
            raise ValueError(f"Atlas interop {label} is invalid")
    if not isinstance(created_at, str) or not created_at.endswith("Z"):
        raise ValueError("Atlas interop created_at must be an RFC 3339 UTC timestamp")
    try:
        datetime.fromisoformat(created_at[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("Atlas interop created_at must be an RFC 3339 UTC timestamp") from exc


def _package_version() -> str:
    from . import __version__

    return __version__
