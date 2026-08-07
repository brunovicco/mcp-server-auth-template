"""Domain errors for bearer-token verification.

These are internal signals used by adapters while they resolve a token; the
public contract with the MCP SDK is still "return ``None`` from
:meth:`~mcp.server.auth.provider.TokenVerifier.verify_token` on any failure"
(see ``AGENTS.md`` for why we never leak verification detail to the caller).
"""


class TokenVerificationError(Exception):
    """Base class for any failure while verifying a bearer token."""


class DiscoveryError(TokenVerificationError):
    """The authorization server's OIDC discovery document could not be resolved."""


class SigningKeyError(TokenVerificationError):
    """No matching JWKS signing key was found for the token's ``kid``."""


class ClaimValidationError(TokenVerificationError):
    """The token's signature is valid but a required claim failed validation."""
