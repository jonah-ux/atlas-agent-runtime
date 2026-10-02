# Atlas projection: `ai-work-evidence/v1`

Atlas keeps `atlas-receipt/v1` as its authoritative lifecycle format. The additive interop
projection validates that receipt, then exports only bounded labels and opaque hashes for the
portfolio evidence chain. It never copies the task request, event details, tool rows, prompts,
paths, or credentials.

Completed local lifecycles map to `observed`; failed or cancelled lifecycles map to `failed`; a
queued, running, or approval-waiting lifecycle maps to `unknown`. The projection does not claim a
provider call, deployment, or user-visible outcome.

The `atlas-receipt` artifact is the canonical full receipt JSON with sorted keys, compact UTF-8
encoding, and a trailing newline. Its artifact hash is distinct from the existing
`receipt_sha256`, which remains a provenance value for the receipt core.
