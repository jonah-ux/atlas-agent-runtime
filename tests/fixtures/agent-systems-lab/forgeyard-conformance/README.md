# Mirrored Forgeyard interop corpus

These synthetic documents are copied from Forgeyard's `conformance/` corpus at the owner revision
recorded in `../conformance.json`. They contain no real transcripts, paths, credentials, or
provider data.

Atlas keeps this copy so its consumer conformance surface names the complete owner corpus. Atlas
does not run the Forgeyard validator or reinterpret these documents at runtime; run
`python scripts/run_interop_conformance.py --json` from a Forgeyard checkout to execute the owner
validation report.
