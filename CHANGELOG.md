# Changelog

## 0.1.1 — durable recovery contracts

- Persist lifecycle events with flush and `fsync` before append returns.
- Reject malformed, non-contiguous, or semantically impossible recovered events.
- Scope approval to registered tools that explicitly require it.
- Keep deterministic lifecycle receipts and synthetic recovery proofs provider-neutral.
