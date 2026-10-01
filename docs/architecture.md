# Architecture

```text
CLI / future adapters
        ↓
Runtime state machine
        ↓
Task + ToolSpec + TaskEvent
        ↓
Append-only EventStore (JSONL)
```

The runtime owns state transitions and event persistence. Model providers, shell execution, and
network integrations are intentionally outside the first slice. Recovery reconstructs the latest
state from events; an approval event is required before a declared side effect can run.
