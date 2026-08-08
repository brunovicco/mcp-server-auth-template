"""Application use cases, ports, commands, and queries.

Ports here (see `auth_ports.py`) are `Protocol`s that `adapters` implement, per the dependency
rule in `docs/ARCHITECTURE.md`; see `docs/adr/0001-clean-architecture.md` for why this template
uses that indirection - it's what lets the token-verifier tests run offline against fakes.
"""
