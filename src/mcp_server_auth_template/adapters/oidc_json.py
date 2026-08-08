"""Strict JSON parsing helpers for OIDC control-plane documents."""

import json
from collections.abc import Iterable


class OidcDocumentError(ValueError):
    """Raised when a discovery or JWKS document is structurally unsafe or invalid."""


def _object_without_duplicates(pairs: Iterable[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise OidcDocumentError("OIDC document contains duplicate JSON object keys")
        result[key] = value
    return result


def parse_json_object(content: bytes, *, max_bytes: int) -> dict[str, object]:
    """Parse one bounded UTF-8 JSON object while rejecting duplicate member names."""
    if not content or len(content) > max_bytes:
        raise OidcDocumentError("OIDC document size is invalid")
    try:
        decoded = content.decode("utf-8")
        value = json.loads(decoded, object_pairs_hook=_object_without_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OidcDocumentError("OIDC document is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise OidcDocumentError("OIDC document root must be a JSON object")
    return value
