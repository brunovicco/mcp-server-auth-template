"""Provider-neutral authenticated principal used by authorization policies."""

from dataclasses import dataclass
from enum import StrEnum


class PrincipalKind(StrEnum):
    """Security-relevant identity modes understood by the template."""

    DELEGATED = "delegated"
    APPLICATION = "application"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Principal:
    """Validated identity facts safe for application-layer authorization.

    The principal deliberately carries only normalized authorization facts, not
    the raw bearer token or the complete JWT claims mapping.
    """

    client_id: str
    subject: str | None
    issuer: str | None
    kind: PrincipalKind
    scopes: frozenset[str]
    roles: frozenset[str]
