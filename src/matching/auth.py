"""Service-token authentication with explicit organization grants."""

from __future__ import annotations

import hmac
from uuid import UUID

from fastapi import Header, HTTPException, Request, status


async def authorize_organization(
    request: Request,
    organizationId: UUID,
    service_token: str | None = Header(default=None, alias="X-Weft-Service-Token"),
) -> UUID:
    """Check the configured service credential and its explicit organization allowlist."""
    if not service_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="service_authentication_required"
        )
    tokens: dict[str, list[str]] = request.app.state.settings.matching_service_tokens
    allowed: list[str] | None = None
    for expected, scopes in tokens.items():
        if hmac.compare_digest(service_token, expected):
            allowed = scopes
    if allowed is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_service_credential"
        )
    if str(organizationId) not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="organization_scope_denied"
        )
    return organizationId
