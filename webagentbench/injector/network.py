"""Network injection layer: HTTP interception via Playwright page.route().

Design principles:
  1. FILTER not WALL — task remains solvable with the target primitive.
  2. DISTRIBUTED not ONE-SHOT — degradations persist throughout the task.
  3. DETERMINISTIC — same seed produces same challenge sequence every run.

Behavior modes (set via `behavior.mode` in params):
  once         — fail first N requests, then pass (current default)
  intermittent — fail with probability P, seeded for determinism
  progressive  — escalate difficulty over time (stages)

Targets Patience and Verification primitives.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any


def _seeded_should_fire(seed: int, call_index: int, probability: float) -> bool:
    """Deterministic coin flip: given seed + call index, return True with `probability`.

    Same seed + index always returns the same result across runs.
    """
    h = hashlib.md5(f"{seed}:{call_index}".encode()).hexdigest()
    return (int(h[:8], 16) / 0x100000000) < probability


async def apply_network_injection(page: Any, params: dict[str, Any]) -> None:
    """Register a network injection on a Playwright page."""
    url_pattern = params.get("url_pattern", "**/*")
    action = params.get("action", "")
    behavior = params.get("behavior", {})
    mode = behavior.get("mode", "once")
    behavior_seed = behavior.get("seed", 42)

    if action == "delay":
        # Patience: adds latency. Agent with patience waits; without acts prematurely.
        if mode == "progressive":
            stages = behavior.get("stages", [{"after_call": 0, "delay_ms": params.get("delay_ms", 3000)}])
            call_counter = {"n": 0}

            async def progressive_delay_handler(route):
                call_counter["n"] += 1
                # Find the current stage
                current_delay = 0
                for stage in stages:
                    if call_counter["n"] >= stage.get("after_call", 0):
                        current_delay = stage.get("delay_ms", 0)
                if current_delay > 0:
                    await asyncio.sleep(current_delay / 1000)
                await route.continue_()

            await page.route(url_pattern, progressive_delay_handler)

        elif mode == "intermittent":
            probability = behavior.get("probability", 0.3)
            delay_ms = params.get("delay_ms", 3000)
            call_counter = {"n": 0}

            async def intermittent_delay_handler(route):
                call_counter["n"] += 1
                if _seeded_should_fire(behavior_seed, call_counter["n"], probability):
                    await asyncio.sleep(delay_ms / 1000)
                await route.continue_()

            await page.route(url_pattern, intermittent_delay_handler)

        else:  # mode == "once" or default
            delay_ms = params.get("delay_ms", 3000)

            async def delay_handler(route):
                await asyncio.sleep(delay_ms / 1000)
                await route.continue_()

            await page.route(url_pattern, delay_handler)

    elif action == "transient_flash":
        # Patience: briefly shows wrong content before real content.
        flash_html = params.get("html", "<div>Loading...</div>")
        duration_ms = params.get("duration_ms", 3000)

        if mode == "intermittent":
            probability = behavior.get("probability", 0.4)
            call_counter = {"n": 0}

            async def intermittent_flash_handler(route):
                call_counter["n"] += 1
                if _seeded_should_fire(behavior_seed, call_counter["n"], probability):
                    response = await route.fetch()
                    body = await response.text()
                    injected = (
                        f'<div id="__flash_{call_counter["n"]}">{flash_html}</div>'
                        f'<div id="__real_{call_counter["n"]}" style="display:none">{body}</div>'
                        f"<script>setTimeout(()=>{{"
                        f"document.getElementById('__flash_{call_counter['n']}')?.remove();"
                        f"const r=document.getElementById('__real_{call_counter['n']}');"
                        f"if(r)r.style.display='';}},{duration_ms});</script>"
                    )
                    await route.fulfill(status=200, body=injected, headers=dict(response.headers))
                else:
                    await route.continue_()

            await page.route(url_pattern, intermittent_flash_handler)
        else:
            async def flash_handler(route):
                response = await route.fetch()
                body = await response.text()
                injected = (
                    f'<div id="__transient_flash">{flash_html}</div>'
                    f'<div id="__real_content" style="display:none">{body}</div>'
                    f"<script>setTimeout(()=>{{"
                    f"document.getElementById('__transient_flash')?.remove();"
                    f"const r=document.getElementById('__real_content');"
                    f"if(r)r.style.display='';}},{duration_ms});</script>"
                )
                await route.fulfill(status=200, body=injected, headers=dict(response.headers))

            await page.route(url_pattern, flash_handler)

    elif action == "silent_fail":
        # Verification: writes silently fail — agent must check and retry.
        fake_body = params.get("response_body", {"success": True})
        methods = set(params.get("methods", ["POST", "PUT"]))

        if mode == "intermittent":
            # Randomly fail writes with probability P — agent must verify EVERY action
            probability = behavior.get("probability", 0.3)
            call_counter = {"n": 0}

            async def intermittent_silent_handler(route):
                if route.request.method in methods:
                    call_counter["n"] += 1
                    if _seeded_should_fire(behavior_seed, call_counter["n"], probability):
                        await route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps(fake_body),
                        )
                        return
                await route.continue_()

            await page.route(url_pattern, intermittent_silent_handler)

        else:  # mode == "once"
            # First N writes fail, rest succeed
            fail_count = params.get("fail_count", 1)
            write_counter: dict[str, int] = {}

            async def silent_handler(route):
                if route.request.method in methods:
                    req_url = route.request.url
                    write_counter.setdefault(req_url, 0)
                    write_counter[req_url] += 1
                    if write_counter[req_url] <= fail_count:
                        await route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps(fake_body),
                        )
                        return
                await route.continue_()

            await page.route(url_pattern, silent_handler)

    elif action == "stale_data":
        # Verification: first N reads return stale data, then real data.
        stale_body = params.get("stale_body", {})
        stale_count = params.get("stale_count", 1)

        if mode == "intermittent":
            probability = behavior.get("probability", 0.3)
            call_counter = {"n": 0}

            async def intermittent_stale_handler(route):
                call_counter["n"] += 1
                if _seeded_should_fire(behavior_seed, call_counter["n"], probability):
                    await route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(stale_body),
                    )
                else:
                    await route.continue_()

            await page.route(url_pattern, intermittent_stale_handler)
        else:
            call_counter = {"n": 0}

            async def stale_handler(route):
                call_counter["n"] += 1
                if call_counter["n"] <= stale_count:
                    await route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(stale_body),
                    )
                else:
                    await route.continue_()

            await page.route(url_pattern, stale_handler)

    elif action == "error_then_success":
        # Patience: transient errors that resolve on retry.
        error_status = params.get("error_status", 500)
        methods_raw = params.get("methods")
        methods = (
            {str(method).upper() for method in methods_raw}
            if isinstance(methods_raw, list) and methods_raw
            else None
        )
        error_body = params.get("error_body")
        error_message = params.get("error_message", "Server Error")

        async def _fulfill_error(route: Any) -> None:
            if isinstance(error_body, (dict, list)):
                await route.fulfill(
                    status=error_status,
                    content_type="application/json",
                    body=json.dumps(error_body),
                )
                return
            await route.fulfill(
                status=error_status,
                body=str(error_body if error_body is not None else error_message),
            )

        if mode == "intermittent":
            probability = behavior.get("probability", 0.2)
            call_counter = {"n": 0}

            async def intermittent_error_handler(route):
                if methods is not None and route.request.method.upper() not in methods:
                    await route.continue_()
                    return
                call_counter["n"] += 1
                if _seeded_should_fire(behavior_seed, call_counter["n"], probability):
                    await _fulfill_error(route)
                else:
                    await route.continue_()

            await page.route(url_pattern, intermittent_error_handler)
        else:
            error_count = params.get("error_count", 2)
            call_counter = {"n": 0}

            async def error_handler(route):
                if methods is not None and route.request.method.upper() not in methods:
                    await route.continue_()
                    return
                call_counter["n"] += 1
                if call_counter["n"] <= error_count:
                    await _fulfill_error(route)
                else:
                    await route.continue_()

            await page.route(url_pattern, error_handler)
