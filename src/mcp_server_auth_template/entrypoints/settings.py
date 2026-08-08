"""Process configuration, read from the environment.

Exactly one authorization-server mode is active per deployment: set
``MCP_SERVER_AUTH_PROVIDER`` to ``entra`` or ``generic`` and fill in the
matching block below. See ``.env.example`` for a filled-out sample of each.
"""

from typing import Literal

from pydantic import AnyHttpUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from mcp_server_auth_template.domain.scope_claims import qualify_scopes


class Settings(BaseSettings):
    """Runtime configuration for the MCP resource server."""

    model_config = SettingsConfigDict(env_prefix="MCP_SERVER_", env_file=".env", extra="ignore")

    service_name: str = "mcp-server-auth-template"
    resource_server_url: AnyHttpUrl
    required_scopes: list[str] = []

    auth_provider: Literal["entra", "generic"]

    # --- Entra ID mode ---
    entra_tenant_id: str | None = None
    entra_audience: str | None = None
    entra_application_id_uri: str | None = None

    # --- Generic OIDC mode ---
    generic_issuer_url: str | None = None
    generic_audience: str | None = None

    @property
    def effective_required_scopes(self) -> list[str]:
        """Return scope strings in the form that should be advertised and enforced."""
        if self.auth_provider == "entra" and self.entra_application_id_uri:
            return qualify_scopes(self.required_scopes, self.entra_application_id_uri)
        return self.required_scopes

    @model_validator(mode="after")
    def _require_matching_provider_fields(self) -> "Settings":
        if self.auth_provider == "entra":
            missing = [
                name
                for name, value in (
                    ("entra_tenant_id", self.entra_tenant_id),
                    ("entra_audience", self.entra_audience),
                    ("entra_application_id_uri", self.entra_application_id_uri),
                )
                if not value
            ]
        else:
            missing = [
                name
                for name, value in (
                    ("generic_issuer_url", self.generic_issuer_url),
                    ("generic_audience", self.generic_audience),
                )
                if not value
            ]
        if missing:
            raise ValueError(f"auth_provider={self.auth_provider!r} requires: {', '.join(missing)}")
        return self
