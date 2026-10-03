# Provenance

Atlas Agent Runtime is an independent public implementation of general patterns from durable
automation and agent systems. The existing private/fleet Atlas map is a separate project and was
not copied into this repository. No employer source, customer data, credentials, private paths,
production logs, or proprietary operating policy is included.

The release workflow checks annotated tag identity, builds a wheel and source archive, writes
`SHA256SUMS`, and runs isolated consumers. The `scripts/audit_public_surface.py` command exposes a
bounded dependency/license/provenance/privacy receipt and can compare a caller-supplied `dist/`
directory with its checksum manifest. The audit's high-signal scan is not complete DLP, and missing
artifact inputs remain `unavailable`.
