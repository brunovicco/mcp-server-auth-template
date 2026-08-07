"""Value object for OIDC discovery metadata.

Lives in the domain layer (not in the adapter that fetches it) so the
application-layer port in ``application/auth_ports.py`` can reference its
shape without depending on the adapters layer.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OidcMetadata:
    """The subset of OIDC discovery metadata this template depends on."""

    issuer: str
    jwks_uri: str
