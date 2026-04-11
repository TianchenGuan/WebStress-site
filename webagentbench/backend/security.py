from __future__ import annotations

import hmac
from typing import Any

from fastapi import HTTPException, Request, status

CONTROLLER_SECRET_ENV = "WEBAGENTBENCH_CONTROLLER_SECRET"
CONTROLLER_SECRET_HEADER = "X-WAB-Controller-Secret"


def has_controller_access(request: Request) -> bool:
    """Return True if the request carries a valid controller secret."""
    expected = getattr(request.app.state, "controller_secret", None)
    provided = request.headers.get(CONTROLLER_SECRET_HEADER)
    if not isinstance(expected, str) or not expected:
        return False
    if not isinstance(provided, str):
        return False
    return hmac.compare_digest(provided, expected)


def require_controller_access(request: Request) -> None:
    expected = getattr(request.app.state, "controller_secret", None)
    provided = request.headers.get(CONTROLLER_SECRET_HEADER)
    if not isinstance(expected, str) or not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Controller authentication is not configured",
        )
    if not isinstance(provided, str) or not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Controller access required",
        )


def build_public_session_response(
    *,
    session_id: str,
    start_path: str,
    title: str,
    instruction: str,
    degradation_active: bool,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "start_path": start_path,
        "title": title,
        "instruction": instruction,
        "degradation_active": degradation_active,
    }


def build_public_session_summary(
    summary: dict[str, Any],
    *,
    title: str,
    instruction: str,
) -> dict[str, Any]:
    public = {
        key: summary[key]
        for key in ("session_id", "env_id", "created_at", "updated_at", "audit_entries", "degradation")
        if key in summary
    }
    public["title"] = title
    public["instruction"] = instruction
    public["degradation_active"] = bool(summary.get("degradation"))
    return public
