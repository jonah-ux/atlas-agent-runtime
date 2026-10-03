# Changelog

## 0.2.0 — shared work evidence projection

- Add `atlas evidence` and strict `ai-work-evidence/v1` receipt projection.
- Preserve local lifecycle integrity while keeping request text and event details out of shared records.

## 0.1.1 — durable recovery contracts

- Persist lifecycle events with flush and `fsync` before append returns.
- Reject malformed, non-contiguous, or semantically impossible recovered events.
- Scope approval to registered tools that explicitly require it.
- Keep deterministic lifecycle receipts and synthetic recovery proofs provider-neutral.
- Add a dependency-free `ai-work-evidence/v1` projection that validates lifecycle receipts and
  exports only bounded metadata and artifact hashes.
