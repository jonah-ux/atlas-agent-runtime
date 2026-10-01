# Atlas Agent Runtime

Atlas is a small, durable runtime for inspectable AI tasks. It records lifecycle events, refuses
illegal state transitions, pauses side-effecting tools for approval, and reconstructs unfinished
tasks from an append-only JSONL event store after restart.

This repository is the public runtime project. The existing `asm-agent-atlas` repository is a
separate fleet map and source-of-truth vault; this project does not copy its private notes or
operational data.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
atlas demo --state ./artifacts/demo-events.jsonl
atlas receipt demo-task --state ./artifacts/demo-events.jsonl
```

The demo starts a task, pauses before a side effect, reconstructs it from the event store, records
approval, and completes it. Output is JSON and the state file contains no model credentials or
private transcript data.

`receipt` reconstructs the task from the event store and emits an `atlas-receipt/v1` document with
ordered events and a SHA-256 content fingerprint. The fingerprint is an integrity aid, not a
signature or a claim that the task was deployed.

## Design boundaries

- The core is provider-neutral and has no model SDK dependency.
- Tools declare whether they have side effects and whether approval is required.
- State transitions are explicit and illegal moves raise an error.
- Event records are append-only and replayable.
- Recovery fails closed when the event store contains malformed JSON or a non-contiguous per-task sequence.
- Approval grants and tool calls are persisted as ordered events, so an approved task keeps its
  authorization after restart.
- Approval is task-scoped and only admits registered tools that explicitly require approval;
  unknown or non-gated tool names are rejected.
- The first slice does not execute arbitrary shell commands or contact a model provider.

## Status

Version 0.1.0 is a runtime foundation. Provider adapters, distributed workers, richer receipts,
and a dashboard are future slices and are not represented as implemented here.

## Provenance and security

This is an independent public implementation of general agent-runtime patterns. It contains no
employer source, customer data, credentials, private paths, production logs, or proprietary
operating policy. See `PROVENANCE.md` and `SECURITY.md`.
