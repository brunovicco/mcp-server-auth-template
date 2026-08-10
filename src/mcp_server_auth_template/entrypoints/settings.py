"""Process configuration, read from the environment.

Exactly one authorization-server mode is active per deployment: set
``MCP_SERVER_AUTH_PROVIDER`` to ``entra`` or ``generic`` and fill in the
matching block below. See ``.env.example`` for a filled-out sample of each.
"""

from ipaddress import ip_address
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import AliasChoices, AnyHttpUrl, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from mcp_server_auth_template.domain.scope_claims import qualify_scopes


class Settings(BaseSettings):
    """Runtime configuration for the MCP resource server."""

    model_config = SettingsConfigDict(
        env_prefix="MCP_SERVER_",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    service_name: str = "mcp-server-auth-template"
    app_env: Literal["development", "test", "staging", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENV", "MCP_SERVER_APP_ENV"),
    )
    runtime_host: str = Field(
        default_factory=lambda: str(ip_address(0)), min_length=1, max_length=253
    )
    runtime_port: int = Field(default=8000, ge=1, le=65535)
    runtime_workers: int = Field(default=1, ge=1, le=32)
    runtime_backlog: int = Field(default=2048, ge=1, le=65535)
    runtime_keep_alive_seconds: int = Field(default=5, ge=1, le=120)
    runtime_graceful_shutdown_seconds: int = Field(default=30, ge=1, le=300)

    resource_server_url: AnyHttpUrl
    required_scopes: list[str] = []

    # OIDC discovery/JWKS network trust boundary.
    oidc_allow_insecure_loopback: bool = False

    # Streamable HTTP admission bounds. MCP 2026-07-28 is served statelessly
    # and with JSON responses; these limits constrain the remaining HTTP surface.
    transport_max_request_body_bytes: int = Field(default=1024 * 1024, ge=1024, le=16 * 1024 * 1024)
    transport_max_header_count: int = Field(default=64, ge=8, le=256)
    transport_max_header_bytes: int = Field(default=32 * 1024, ge=1024, le=128 * 1024)
    transport_max_concurrent_requests: int = Field(default=64, ge=1, le=1024)
    transport_allowed_hosts: list[str] = Field(default_factory=list)
    transport_allowed_origins: list[str] = Field(default_factory=list)

    auth_provider: Literal["entra", "generic"]

    # --- Entra ID mode ---
    entra_tenant_id: str | None = None
    entra_audience: str | None = None
    entra_application_id_uri: str | None = None

    # --- Generic OIDC mode ---
    generic_issuer_url: str | None = None
    generic_audience: str | None = None
    generic_jwks_allowed_origins: list[str] = Field(default_factory=list)

    @property
    def effective_required_scopes(self) -> list[str]:
        """Return scope strings in the form that should be advertised and enforced."""
        if self.auth_provider == "entra" and self.entra_application_id_uri:
            return qualify_scopes(self.required_scopes, self.entra_application_id_uri)
        return self.required_scopes

    def _validate_runtime_settings(self) -> None:
        if self.runtime_host.strip() != self.runtime_host or any(
            ord(ch) < 0x21 for ch in self.runtime_host
        ):
            raise ValueError("runtime_host must be a non-empty visible string without whitespace")

    def _validate_resource_server_transport_url(self) -> None:
        parsed = urlsplit(str(self.resource_server_url))
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("resource_server_url must not contain credentials, query, or fragment")
        if parsed.scheme == "https":
            return
        host = parsed.hostname
        if parsed.scheme != "http" or host is None:
            raise ValueError("resource_server_url must use https")
        try:
            address = ip_address(host)
        except ValueError as exc:
            raise ValueError(
                "HTTP resource_server_url is allowed only for an IP-literal loopback host"
            ) from exc
        if not address.is_loopback:
            raise ValueError(
                "HTTP resource_server_url is allowed only for an IP-literal loopback host"
            )

    def _validate_transport_allowlists(self) -> None:
        for field_name, values in (
            ("transport_allowed_hosts", self.transport_allowed_hosts),
            ("transport_allowed_origins", self.transport_allowed_origins),
        ):
            if any(
                not value
                or value.strip() != value
                or any(ord(ch) < 0x21 for ch in value)
                or "*" in value
                for value in values
            ):
                raise ValueError(f"{field_name} entries must be non-empty exact visible strings")

        for host in self.transport_allowed_hosts:
            parsed_host = urlsplit(f"//{host}")
            try:
                _ = parsed_host.port
            except ValueError as exc:
                raise ValueError("transport_allowed_hosts contains an invalid port") from exc
            if (
                parsed_host.hostname is None
                or parsed_host.username is not None
                or parsed_host.password is not None
                or parsed_host.path
                or parsed_host.query
                or parsed_host.fragment
                or host.endswith(":")
            ):
                raise ValueError("transport_allowed_hosts entries must be host[:port] values")

        for origin in self.transport_allowed_origins:
            parsed_origin = urlsplit(origin)
            try:
                _ = parsed_origin.port
            except ValueError as exc:
                raise ValueError("transport_allowed_origins contains an invalid port") from exc
            if (
                parsed_origin.scheme not in {"http", "https"}
                or parsed_origin.hostname is None
                or parsed_origin.username is not None
                or parsed_origin.password is not None
                or parsed_origin.path
                or parsed_origin.query
                or parsed_origin.fragment
            ):
                raise ValueError("transport_allowed_origins entries must be exact http(s) origins")

    @staticmethod
    def _is_placeholder_hostname(hostname: str | None) -> bool:
        if hostname is None:
            return True
        normalized = hostname.rstrip(".").lower()
        if normalized == "localhost" or normalized.endswith((".localhost", ".invalid", ".test")):
            return True
        return any(
            normalized == suffix or normalized.endswith(f".{suffix}")
            for suffix in ("example.com", "example.net", "example.org")
        )

    def _validate_production_profile(self) -> None:
        if self.app_env != "production":
            return

        resource = urlsplit(str(self.resource_server_url))
        if resource.scheme != "https":
            raise ValueError("production requires an HTTPS resource_server_url")
        if self._is_placeholder_hostname(resource.hostname):
            raise ValueError("production resource_server_url must not use a placeholder hostname")
        if self.oidc_allow_insecure_loopback:
            raise ValueError("production forbids oidc_allow_insecure_loopback=true")

        for origin in self.transport_allowed_origins:
            parsed = urlsplit(origin)
            if parsed.scheme != "https":
                raise ValueError("production transport_allowed_origins must use HTTPS")
            if self._is_placeholder_hostname(parsed.hostname):
                raise ValueError(
                    "production transport_allowed_origins must not use placeholder hostnames"
                )

        zero_uuid = "00000000-0000-0000-0000-000000000000"
        if self.auth_provider == "entra":
            if self.entra_tenant_id == zero_uuid:
                raise ValueError("production entra_tenant_id must not use the all-zero placeholder")
            for value in (self.entra_audience, self.entra_application_id_uri):
                if value is not None and zero_uuid in value.lower():
                    raise ValueError(
                        "production Entra identifiers must not use all-zero placeholders"
                    )
            return

        issuer = urlsplit(self.generic_issuer_url or "")
        try:
            _ = issuer.port
        except ValueError as exc:
            raise ValueError("production generic_issuer_url contains an invalid port") from exc
        if (
            issuer.scheme != "https"
            or issuer.hostname is None
            or issuer.username is not None
            or issuer.password is not None
            or issuer.query
            or issuer.fragment
        ):
            raise ValueError(
                "production generic_issuer_url must be an absolute HTTPS issuer "
                "without credentials, query, or fragment"
            )
        if self._is_placeholder_hostname(issuer.hostname):
            raise ValueError("production generic_issuer_url must not use a placeholder hostname")

        audience = urlsplit(self.generic_audience or "")
        if audience.hostname is not None and self._is_placeholder_hostname(audience.hostname):
            raise ValueError("production generic_audience must not use a placeholder hostname")

        for origin in self.generic_jwks_allowed_origins:
            parsed = urlsplit(origin)
            try:
                _ = parsed.port
            except ValueError as exc:
                raise ValueError(
                    "production generic_jwks_allowed_origins contains an invalid port"
                ) from exc
            if (
                parsed.scheme != "https"
                or parsed.hostname is None
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "production generic_jwks_allowed_origins entries must be exact HTTPS origins"
                )
            if self._is_placeholder_hostname(parsed.hostname):
                raise ValueError(
                    "production generic_jwks_allowed_origins must not use placeholder hostnames"
                )

    @model_validator(mode="after")
    def _require_matching_provider_fields(self) -> "Settings":
        self._validate_runtime_settings()
        self._validate_resource_server_transport_url()
        self._validate_transport_allowlists()
        if "offline_access" in self.required_scopes:
            raise ValueError(
                "required_scopes must not include offline_access; refresh-token consent belongs "
                "to the OAuth client and authorization server"
            )
        if self.auth_provider == "entra":
            if self.entra_tenant_id:
                try:
                    self.entra_tenant_id = str(UUID(self.entra_tenant_id))
                except ValueError as exc:
                    raise ValueError(
                        "entra_tenant_id must be a tenant-specific UUID, not an alias or path"
                    ) from exc
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
        self._validate_production_profile()
        return self
