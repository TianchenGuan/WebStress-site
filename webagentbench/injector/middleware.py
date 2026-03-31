"""Server-side network degradation middleware.

Applies network-layer degradation effects (delays, errors, silent failures)
on the server side so they work for BOTH Playwright agents AND human browsers.

When a session has network degradations configured, this middleware intercepts
matching API requests and applies the effects before the real handler runs.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


# Per-session stores
_SESSION_NETWORK: dict[str, list[dict]] = {}   # session_id → network injections
_SESSION_CLIENT: dict[str, list[dict]] = {}    # session_id → client injections
_CALL_COUNTERS: dict[str, dict[str, int]] = {} # session_id → per-pattern counters


def register_session_degradation(session_id: str, injections: list[dict]) -> None:
    """Store degradation config for a session (network + client)."""
    unregister_session_degradation(session_id)
    network = [inj for inj in injections if inj.get("layer") == "network"]
    client = [inj for inj in injections if inj.get("layer") == "client"]
    if network:
        _SESSION_NETWORK[session_id] = network
        _CALL_COUNTERS[session_id] = {}
    if client:
        _SESSION_CLIENT[session_id] = client
    if network or client:
        logger.info(
            "Registered %d network + %d client degradation(s) for session %s",
            len(network), len(client), session_id,
        )


def unregister_session_degradation(session_id: str) -> None:
    """Remove degradation config when session is destroyed."""
    _SESSION_NETWORK.pop(session_id, None)
    _SESSION_CLIENT.pop(session_id, None)
    _CALL_COUNTERS.pop(session_id, None)


def clear_all_degradations() -> None:
    """Reset all degradation state. Useful for test teardown and server restart."""
    _SESSION_NETWORK.clear()
    _SESSION_CLIENT.clear()
    _CALL_COUNTERS.clear()


def get_client_injections(session_id: str) -> list[dict]:
    """Return client injections for a session (used by the JS endpoint)."""
    return _SESSION_CLIENT.get(session_id, [])


def _seeded_should_fire(seed: int, call_index: int, probability: float) -> bool:
    """Deterministic coin flip using md5 hash."""
    h = hashlib.md5(f"{seed}:{call_index}".encode()).hexdigest()
    return (int(h[:8], 16) / 0x100000000) < probability


def _glob_to_regex(pattern: str) -> str:
    """Convert a glob pattern to regex, escaping literal characters."""
    parts = re.split(r'(\*\*|\*)', pattern)
    result = []
    for part in parts:
        if part == '**':
            result.append('.*')
        elif part == '*':
            result.append('[^/]*')
        else:
            result.append(re.escape(part))
    return ''.join(result)


def _url_matches_pattern(url: str, pattern: str) -> bool:
    """Check if URL matches a glob-like pattern (** = any path).

    For ``**/`` prefixed patterns, anchors the suffix to a path boundary
    so ``**/emails`` won't accidentally match ``/emails/e001/star``.
    Query strings and fragments are stripped before matching.
    """
    # Strip query string and fragment for matching
    clean = url.split("?")[0].split("#")[0]
    if pattern.startswith("**/"):
        suffix = pattern[3:]
        regex = _glob_to_regex(suffix)
        # Anchor: must appear after a '/' and reach end-of-path
        return bool(re.search(r"/" + regex + r"$", clean))
    regex = "^" + _glob_to_regex(pattern) + "$"
    return bool(re.match(regex, clean))


def _get_counter(session_id: str, key: str) -> int:
    """Increment and return per-session counter."""
    counters = _CALL_COUNTERS.setdefault(session_id, {})
    counters[key] = counters.get(key, 0) + 1
    return counters[key]


def _extract_session_from_referer(referer: str) -> str | None:
    """Extract session ID from the Referer header.

    The SPA page URL looks like: http://host/env/gmail/inbox?session=xxx
    All API calls from that page include this as the Referer.
    """
    if not referer:
        return None
    match = re.search(r'[?&]session=([^&]+)', referer)
    return match.group(1) if match else None


def _extract_session_from_cookie(cookies: str) -> str | None:
    """Extract session ID from the wab_session cookie."""
    if not cookies:
        return None
    for part in cookies.split(";"):
        part = part.strip()
        if part.startswith("wab_session="):
            return part[len("wab_session="):]
    return None


class DegradationMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that applies network degradation effects server-side.

    Session extraction strategy (without reading request body):
      1. Query param: ``?session_id=xxx`` or ``?session=xxx``
      2. Referer header: SPA page URL contains ``?session=xxx``
      3. Cookie: ``wab_session=xxx`` (set by session-create response)
      4. Brute-force: if only ONE session has degradation, use it
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        session_id = (
            request.query_params.get("session_id")
            or request.query_params.get("session")
            or _extract_session_from_referer(request.headers.get("referer", ""))
            or _extract_session_from_cookie(request.headers.get("cookie", ""))
        )

        # Fallback: if exactly one session has network degradation AND the
        # request targets an API endpoint but the session_id could not be
        # extracted, assume it belongs to the sole degraded session.
        # Includes GET so that stale_data and delay degradations on read
        # endpoints are not silently skipped.
        if not session_id and len(_SESSION_NETWORK) == 1:
            url_path = request.url.path
            if "/api/env/" in url_path:
                session_id = next(iter(_SESSION_NETWORK))

        if not session_id or session_id not in _SESSION_NETWORK:
            return await call_next(request)

        # Check each network injection
        url = str(request.url)
        method = request.method
        injections = _SESSION_NETWORK[session_id]

        for inj_idx, inj in enumerate(injections):
            params = inj.get("params", {})
            action = params.get("action", "")
            url_pattern = params.get("url_pattern", "**/*")

            if not _url_matches_pattern(url, url_pattern):
                continue

            # For method-filtered actions, check the method BEFORE
            # incrementing the counter so that non-matching methods
            # (e.g. a GET to load a page) don't consume the fail budget.
            if action == "silent_fail":
                methods = set(params.get("methods", ["POST", "PUT"]))
                if method not in methods:
                    continue
            elif action == "stale_data":
                if method not in ("GET",):
                    continue
            elif action == "error_then_success":
                ets_methods = params.get("methods")
                if ets_methods and method not in set(ets_methods):
                    continue
            elif action == "delay":
                delay_methods = params.get("methods")
                if delay_methods and method not in set(delay_methods):
                    continue

            behavior = params.get("behavior", {})
            mode = behavior.get("mode", "once")
            beh_seed = behavior.get("seed", 42)
            counter_key = f"{action}:{url_pattern}:{inj_idx}"
            call_num = _get_counter(session_id, counter_key)

            if action == "delay":
                delay_ms = params.get("delay_ms", 3000)
                should_delay = False

                if mode == "progressive":
                    stages = behavior.get("stages", [{"after_call": 0, "delay_ms": delay_ms}])
                    current_delay = 0
                    for stage in stages:
                        # Accept common key name variants from YAML files
                        threshold = (
                            stage.get("after_call")
                            or stage.get("call_number")
                            or stage.get("requests")
                            or stage.get("until_count")
                            or 0
                        )
                        if call_num >= threshold:
                            current_delay = stage.get("delay_ms", 0)
                    if current_delay > 0:
                        delay_ms = current_delay
                        should_delay = True
                elif mode == "intermittent":
                    prob = behavior.get("probability", 0.3)
                    should_delay = _seeded_should_fire(beh_seed, call_num, prob)
                else:  # once — always delay
                    should_delay = True

                if should_delay:
                    await asyncio.sleep(delay_ms / 1000)

            elif action == "error_then_success":
                error_status = params.get("error_status", 503)
                should_error = False

                if mode == "intermittent":
                    prob = behavior.get("probability", 0.2)
                    should_error = _seeded_should_fire(beh_seed, call_num, prob)
                else:
                    error_count = params.get("error_count", 2)
                    should_error = call_num <= error_count

                if should_error:
                    return JSONResponse(
                        status_code=error_status,
                        content={"error": "Server Error", "degradation": True},
                    )

            elif action == "silent_fail":
                fake_body = params.get("response_body", {"success": True})
                should_fail = False

                if mode == "intermittent":
                    prob = behavior.get("probability", 0.3)
                    should_fail = _seeded_should_fire(beh_seed, call_num, prob)
                else:
                    fail_count = params.get("fail_count", 1)
                    should_fail = call_num <= fail_count

                if should_fail:
                    return JSONResponse(
                        status_code=200,
                        content=fake_body,
                    )

            elif action == "stale_data":
                stale_body = params.get("stale_body", {})
                should_stale = False

                if mode == "intermittent":
                    prob = behavior.get("probability", 0.3)
                    should_stale = _seeded_should_fire(beh_seed, call_num, prob)
                else:
                    stale_count = params.get("stale_count", 1)
                    should_stale = call_num <= stale_count

                if should_stale:
                    return JSONResponse(
                        status_code=200,
                        content=stale_body,
                    )

        return await call_next(request)
