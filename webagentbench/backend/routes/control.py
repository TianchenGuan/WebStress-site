"""Control-panel API: recording state sync between control tab and benchmark tab.

Env-agnostic. The benchmark tab polls `record-state` to know whether to
capture DOM events. The control tab calls `start`/`stop` to toggle.

Recording state is in-memory only (dies with the process). Events are
buffered in the benchmark page's JS and submitted in bulk via the existing
`/api/env/{env}/trajectory` endpoint.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/control", tags=["control"])


class RecordState(BaseModel):
    recording: bool = False
    started_at_ms: int = 0
    event_count: int = 0
    last_heartbeat_ms: int = 0


# In-memory state keyed by session_id.
_RECORD_STATE: dict[str, RecordState] = {}


def _get(session_id: str) -> RecordState:
    return _RECORD_STATE.setdefault(session_id, RecordState())


@router.get("/{session_id}/record-state")
def get_record_state(session_id: str) -> dict[str, Any]:
    state = _get(session_id)
    return state.model_dump()


@router.post("/{session_id}/record/start")
def record_start(session_id: str) -> dict[str, Any]:
    state = _get(session_id)
    if state.recording:
        raise HTTPException(status_code=409, detail="Already recording")
    state.recording = True
    state.started_at_ms = int(time.time() * 1000)
    state.event_count = 0
    return state.model_dump()


@router.post("/{session_id}/record/stop")
def record_stop(session_id: str) -> dict[str, Any]:
    state = _get(session_id)
    state.recording = False
    return state.model_dump()


class EventCountUpdate(BaseModel):
    event_count: int


@router.post("/{session_id}/record/heartbeat")
def record_heartbeat(session_id: str, body: EventCountUpdate) -> dict[str, Any]:
    """Benchmark page reports its current event count so the control tab can show it.

    Also updates ``last_heartbeat_ms`` so the control tab knows whether a
    benchmark tab is still open.
    """
    state = _get(session_id)
    state.event_count = body.event_count
    state.last_heartbeat_ms = int(time.time() * 1000)
    return state.model_dump()


@router.post("/{session_id}/record/reset")
def record_reset(session_id: str) -> dict[str, Any]:
    """Clear recording state. Does not touch the simulated env state."""
    _RECORD_STATE.pop(session_id, None)
    return {"ok": True}
