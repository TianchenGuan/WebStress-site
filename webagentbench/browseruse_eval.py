"""Browser-use evaluation harness.

Utilities for observation masking, agent output parsing, trajectory
conversion, and the full async agent loop + evaluation orchestrator
used by the browser-use evaluation path.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── 1. mask_observations ──────────────────────────────────────────────

def mask_observations(messages: list[dict], window: int = 10) -> list[dict]:
    """Keep first obs + last *window* obs in full; mask middle observations.

    All assistant messages are preserved unconditionally.
    """
    user_indices = [i for i, m in enumerate(messages) if m["role"] == "user"]
    if len(user_indices) <= window + 1:
        return list(messages)
    keep = {user_indices[0]} | set(user_indices[-window:])
    return [
        {"role": "user", "content": "[observation omitted]"}
        if m["role"] == "user" and i not in keep
        else dict(m)
        for i, m in enumerate(messages)
    ]


# ── 2. parse_agent_output ────────────────────────────────────────────

_EMPTY_RESULT: dict[str, Any] = {
    "thinking": "",
    "memory": "",
    "next_goal": "",
    "action": [],
}

_PLAIN_RE = re.compile(
    r"^(click|input|scroll|go_back|done)\s*(\d+)?\s*(.*)$", re.IGNORECASE
)


def _strip_markdown_fences(raw: str) -> str:
    """Remove ```json ... ``` wrappers if present."""
    stripped = raw.strip()
    if stripped.startswith("```"):
        # Remove opening fence (```json or ```)
        stripped = re.sub(r"^```[a-zA-Z]*\n?", "", stripped)
        # Remove closing fence
        stripped = re.sub(r"\n?```\s*$", "", stripped)
    return stripped.strip()


def _parse_plain_text(raw: str) -> dict[str, Any]:
    """Best-effort parse of plain-text action like ``click 33``."""
    m = _PLAIN_RE.match(raw.strip())
    if not m:
        return dict(_EMPTY_RESULT)
    verb = m.group(1).lower()
    idx_str = m.group(2)
    rest = m.group(3).strip().strip('"').strip("'")

    result = dict(_EMPTY_RESULT)

    if verb == "click" and idx_str is not None:
        result["action"] = [{"click": {"index": int(idx_str)}}]
    elif verb == "input" and idx_str is not None:
        result["action"] = [{"input_text": {"index": int(idx_str), "text": rest}}]
    elif verb == "scroll":
        direction = idx_str or rest or "down"
        if direction in ("up",):
            result["action"] = [{"scroll_up": {"amount": 300}}]
        else:
            result["action"] = [{"scroll_down": {"amount": 300}}]
    elif verb == "go_back":
        result["action"] = [{"go_back": {}}]
    elif verb == "done":
        result["action"] = [{"done": {"text": rest or "done", "success": True}}]

    return result


def parse_agent_output(raw: str) -> dict[str, Any]:
    """Parse structured JSON (or plain-text fallback) from agent output."""
    if not raw or not raw.strip():
        return dict(_EMPTY_RESULT)

    cleaned = _strip_markdown_fences(raw)

    # Try JSON first
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return {
                "thinking": parsed.get("thinking", ""),
                "memory": parsed.get("memory", ""),
                "next_goal": parsed.get("next_goal", ""),
                "action": parsed.get("action", []),
            }
    except json.JSONDecodeError:
        pass

    # Plain-text fallback
    return _parse_plain_text(cleaned)


# ── 3. action_to_trajectory_format ───────────────────────────────────

def action_to_trajectory_format(action: dict) -> dict:
    """Convert a single browser-use action dict to demo-site replay format."""
    if "click" in action:
        return {"action": "click", "ref": str(action["click"]["index"])}

    if "input_text" in action:
        payload = action["input_text"]
        return {"action": "fill", "ref": str(payload["index"]), "value": payload["text"]}

    if "select_option" in action:
        payload = action["select_option"]
        return {"action": "select", "ref": str(payload["index"]), "value": payload["option"]}

    if "scroll_down" in action:
        return {"action": "scroll", "direction": "down"}

    if "scroll_up" in action:
        return {"action": "scroll", "direction": "up"}

    if "go_back" in action:
        return {"action": "back"}

    if "done" in action:
        return {"action": "finish", "answer": action["done"].get("text", "")}

    return {"action": "unknown"}


# ── 4. dom_element_to_target ─────────────────────────────────────────

_TAG_TO_ROLE: dict[str, str] = {
    "button": "button",
    "a": "link",
    "input": "textbox",
    "textarea": "textbox",
    "select": "combobox",
    "article": "article",
}


def dom_element_to_target(tag_name: str, attributes: dict, text: str = "") -> dict:
    """Convert DOM element info to a replay target ``{role, name}``."""
    tag_lower = tag_name.lower()
    role = _TAG_TO_ROLE.get(tag_lower, tag_lower)

    # Name priority: aria-label > placeholder > text
    name = (
        attributes.get("aria-label")
        or attributes.get("placeholder")
        or text
        or ""
    )

    return {"role": role, "name": name}


# ── 5. build_trajectory_step ─────────────────────────────────────────

_ENV_PATH_RE = re.compile(r"/env/(?:gmail|robinhood)(/[^?]*)")


def _extract_replay_path(url: str) -> str:
    """Extract path component after ``/env/gmail`` or ``/env/robinhood``."""
    m = _ENV_PATH_RE.search(url)
    if not m:
        return "/"
    path = m.group(1)
    # Normalise trailing slash to bare "/"
    return path if path and path != "/" else "/"


def _get_action_index(action: dict) -> int | None:
    """Return the element index referenced by an action, or None."""
    for key in ("click", "input_text", "select_option"):
        if key in action:
            return action[key].get("index")
    return None


def build_trajectory_step(
    step_num: int,
    thinking: str,
    memory: str,
    actions: list[dict],
    dom_elements: dict[int, tuple | dict],
    url: str,
    status: str,
    elapsed: float,
) -> dict:
    """Build one trajectory step matching the demo-site replay format."""
    # Action conversion
    if actions:
        first = actions[0]
        converted_action = action_to_trajectory_format(first)
        idx = _get_action_index(first)
    else:
        converted_action = {"action": "unknown"}
        idx = None

    # Target lookup
    targets: dict = {}
    if idx is not None and idx in dom_elements:
        elem = dom_elements[idx]
        if isinstance(elem, tuple):
            targets = dom_element_to_target(*elem)
        else:
            targets = dom_element_to_target(
                elem.get("tag_name", ""),
                elem.get("attributes", {}),
                elem.get("text", ""),
            )

    replay_path = _extract_replay_path(url)

    return {
        "step": step_num,
        "thought": thinking,
        "action": converted_action,
        "targets": targets,
        "status": status,
        "elapsed_seconds": elapsed,
        "replay_path": replay_path,
        "result_path": replay_path,
    }


# ── 6. System prompt ────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """\
You are a web agent. Complete the task below by interacting with the browser.

## Task
{goal}

## Observation Format
You receive a compact DOM tree of interactive page elements:
- `[index]<tagname attribute=value />` -- interactive elements
- Text content appears on indented child lines
- `*[index]` marks NEW elements since your last action
- Tab indentation shows nesting
- Only `[index]` elements are interactive

## Output Format
Respond with valid JSON:
{{
  "thinking": "Brief analysis of current state and what to do next",
  "memory": "Key facts to remember (progress, counts, findings)",
  "next_goal": "What you will do next",
  "action": [
    {{"click": {{"index": N}}}},
    {{"input_text": {{"index": N, "text": "value"}}}},
    {{"select_option": {{"index": N, "option": "value"}}}},
    {{"scroll_down": {{"amount": 300}}}},
    {{"scroll_up": {{"amount": 300}}}},
    {{"go_back": {{}}}},
    {{"done": {{"text": "result or summary", "success": true}}}}
  ]
}}

## Rules
1. Use element indices from the CURRENT observation only.
2. Up to 3 actions per step. Place page-changing actions last.
3. If an action fails, the error tells you what went wrong. Adapt.
4. Call done with success=true only when the task is fully complete.
5. Output valid JSON only -- no extra text.
"""


# ── 7. HTTP helper ──────────────────────────────────────────────────

def _http_json(url: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        text = resp.read().decode("utf-8")
        return json.loads(text) if text else {}


# ── 8. run_episode ──────────────────────────────────────────────────

async def run_episode(
    task_id: str,
    model: str,
    provider: str = "openai",
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    max_steps: int = 200,
    timeout_seconds: int = 3600,
    headless: bool = True,
    server_host: str = "127.0.0.1",
    server_port: int = 8080,
    seed: int = 42,
    degradation: str | None = None,
    degradation_config: Any | None = None,
    verbose: bool = True,
) -> dict:
    """Run one browser-use agent episode on a WebAgentBench task.

    Returns a result dict compatible with agent_eval's output format.
    """
    from browser_use.browser.session import BrowserSession

    from .agent import create_client, llm_complete
    from .tasks._registry import get_task as _get_task

    task_def = _get_task(task_id)
    env_id = task_def.env_id

    bench_url = f"http://{server_host}:{server_port}"

    # ── 1. Create server session ────────────────────────────────────
    session_payload: dict[str, Any] = {"task_id": task_id, "seed": seed}
    if degradation_config:
        session_payload["degradation"] = {
            "variant_id": degradation_config.variant_id,
            "base_task_id": degradation_config.base_task_id,
            "target_primitive": degradation_config.target_primitive,
            "description": degradation_config.description,
            "injections": [
                {"layer": inj.layer, "params": inj.params}
                for inj in degradation_config.injections
            ],
        }

    created = _http_json(
        f"{bench_url}/api/env/{env_id}/session",
        method="POST",
        payload=session_payload,
    )
    session_id = created["session_id"]
    start_path = created.get("start_path", task_def.start_path or "/")

    from .task_rendering import render_template
    instruction = (
        created.get("instruction")
        or render_template(
            task_def.instruction_template or task_def.instruction or "",
            created.get("resolved_targets", {}),
        )
    )

    if verbose:
        print(f"  Goal: {instruction[:120]}{'...' if len(instruction) > 120 else ''}")

    # ── 2. Launch browser-use browser ───────────────────────────────
    browser = BrowserSession(headless=headless)
    await browser.start()

    start_time = time.time()
    trajectory: list[dict] = []
    messages: list[dict] = []
    completed = False
    evaluation: dict = {"score": 0.0, "success": False, "reasoning": "Agent did not finish"}

    try:
        # Navigate to the SPA
        spa_url = (
            f"{bench_url}/env/{env_id}{start_path}"
            f"?session={urllib.parse.quote(session_id)}&agent_mode=1"
        )
        await browser.navigate_to(spa_url)
        await asyncio.sleep(2)  # let SPA hydrate

        # Build system prompt
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(goal=instruction)
        messages = [{"role": "system", "content": system_prompt}]

        # Create LLM client
        llm_client = create_client(provider, base_url, api_key)

        last_error = ""

        # ── 3. Agent loop ───────────────────────────────────────────
        for step in range(max_steps):
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                if verbose:
                    print(f"    Step {step + 1}: TIMEOUT ({elapsed:.0f}s)")
                break

            # Get browser state
            try:
                state = await browser.get_browser_state_summary(include_screenshot=False)
                dom_text = state.dom_state.llm_representation()
                selector_map = state.dom_state.selector_map
                browser.update_cached_selector_map(selector_map)
                current_url = state.url
            except Exception as exc:
                logger.warning("Failed to get browser state at step %d: %s", step + 1, exc)
                last_error = f"Failed to read page state: {exc}"
                # Build a minimal observation so the agent can attempt recovery
                dom_text = "(page not available)"
                selector_map = {}
                current_url = ""

            # Build observation message
            if step == 0:
                obs_content = f"## Current Page\nURL: {current_url}\n\n{dom_text}"
            else:
                parts = [f"## Current Page\nURL: {current_url}\n\n{dom_text}"]
                if last_error:
                    parts.append(f"\n## Last Action Error\n{last_error}")
                obs_content = "\n".join(parts)

            messages.append({"role": "user", "content": obs_content})

            # Apply observation masking to trim context
            masked = mask_observations(messages, window=10)

            # Call LLM
            try:
                content, _reasoning = llm_complete(
                    llm_client, model, masked,
                    temperature=temperature, provider=provider,
                    reasoning_effort=reasoning_effort,
                )
            except Exception as exc:
                logger.error("LLM call failed at step %d: %s", step + 1, exc)
                last_error = f"LLM error: {exc}"
                messages.append({"role": "assistant", "content": ""})
                continue

            messages.append({"role": "assistant", "content": content})

            # Parse agent output
            parsed = parse_agent_output(content)
            actions = parsed.get("action", [])
            thinking = parsed.get("thinking", "")
            memory = parsed.get("memory", "")

            if verbose:
                action_summary = json.dumps(actions[:1])[:80] if actions else "(no action)"
                print(f"    Step {step + 1}: {action_summary}")

            if not actions:
                last_error = "No actions produced"
                trajectory.append(build_trajectory_step(
                    step + 1, thinking, memory, [],
                    {}, current_url, "ERROR: no action", round(elapsed, 1),
                ))
                continue

            # ── Execute actions ──────────────────────────────────────
            last_error = ""
            action_status = ""

            for action in actions:
                try:
                    if "done" in action:
                        done_payload = action["done"]
                        action_status = "FINISH"
                        completed = True

                        # Evaluate via server
                        try:
                            # Grab benchmark state from browser JS context
                            page = await browser.get_current_page()
                            if page:
                                benchmark_state_str = await page.evaluate(
                                    "() => JSON.stringify(window.__benchmarkState || {})"
                                )
                                benchmark_state = json.loads(benchmark_state_str) if benchmark_state_str else {}
                            else:
                                benchmark_state = {}
                        except Exception:
                            benchmark_state = {}

                        eval_result = _http_json(
                            f"{bench_url}/api/env/{env_id}/evaluate",
                            method="POST",
                            payload={
                                "session_id": session_id,
                                "task_id": task_id,
                                "benchmark_state": benchmark_state,
                            },
                        )
                        evaluation = eval_result
                        break

                    elif "click" in action:
                        idx = action["click"]["index"]
                        node = await browser.get_dom_element_by_index(idx)
                        if node is None:
                            last_error = f"Element index {idx} not found"
                            continue
                        page = await browser.get_current_page()
                        if page:
                            element = await page.get_element(node.backend_node_id)
                            await element.click()
                        await asyncio.sleep(0.5)

                    elif "input_text" in action:
                        payload = action["input_text"]
                        idx = payload["index"]
                        text = payload.get("text", "")
                        node = await browser.get_dom_element_by_index(idx)
                        if node is None:
                            last_error = f"Element index {idx} not found"
                            continue
                        page = await browser.get_current_page()
                        if page:
                            element = await page.get_element(node.backend_node_id)
                            await element.fill(text)
                        await asyncio.sleep(0.3)

                    elif "select_option" in action:
                        payload = action["select_option"]
                        idx = payload["index"]
                        option = payload.get("option", "")
                        node = await browser.get_dom_element_by_index(idx)
                        if node is None:
                            last_error = f"Element index {idx} not found"
                            continue
                        page = await browser.get_current_page()
                        if page:
                            element = await page.get_element(node.backend_node_id)
                            await element.select_option(option)
                        await asyncio.sleep(0.3)

                    elif "scroll_down" in action:
                        amount = action["scroll_down"].get("amount", 300)
                        page = await browser.get_current_page()
                        if page:
                            mouse = await page.mouse
                            await mouse.scroll(delta_y=amount)
                        await asyncio.sleep(0.3)

                    elif "scroll_up" in action:
                        amount = action["scroll_up"].get("amount", 300)
                        page = await browser.get_current_page()
                        if page:
                            mouse = await page.mouse
                            await mouse.scroll(delta_y=-amount)
                        await asyncio.sleep(0.3)

                    elif "go_back" in action:
                        page = await browser.get_current_page()
                        if page:
                            await page.go_back()
                        await asyncio.sleep(0.5)

                    else:
                        last_error = f"Unknown action: {json.dumps(action)}"

                except Exception as exc:
                    last_error = f"Action error: {exc}"
                    logger.warning("Action error at step %d: %s", step + 1, exc)

            # Build element info dict for trajectory
            dom_elements: dict[int, dict] = {}
            for idx_key, node in selector_map.items():
                dom_elements[idx_key] = {
                    "tag_name": getattr(node, "node_name", ""),
                    "attributes": getattr(node, "attributes", {}),
                    "text": getattr(node, "node_value", "") or "",
                }

            step_elapsed = round(time.time() - start_time, 1)
            trajectory.append(build_trajectory_step(
                step + 1, thinking, memory, actions,
                dom_elements, current_url,
                action_status or (f"ERROR: {last_error}" if last_error else ""),
                step_elapsed,
            ))

            if completed:
                break

        # ── 4. If agent didn't call done, evaluate anyway ───────────
        if not completed:
            try:
                page = await browser.get_current_page()
                if page:
                    benchmark_state_str = await page.evaluate(
                        "() => JSON.stringify(window.__benchmarkState || {})"
                    )
                    benchmark_state = json.loads(benchmark_state_str) if benchmark_state_str else {}
                else:
                    benchmark_state = {}
            except Exception:
                benchmark_state = {}

            try:
                eval_result = _http_json(
                    f"{bench_url}/api/env/{env_id}/evaluate",
                    method="POST",
                    payload={
                        "session_id": session_id,
                        "task_id": task_id,
                        "benchmark_state": benchmark_state,
                    },
                )
                evaluation = eval_result
            except Exception as exc:
                logger.error("Post-loop evaluation failed: %s", exc)

    finally:
        # ── 5. Cleanup ──────────────────────────────────────────────
        try:
            await browser.stop()
        except Exception:
            pass

        # Destroy server session
        try:
            _http_json(
                f"{bench_url}/api/env/{env_id}/session/{urllib.parse.quote(session_id)}",
                method="DELETE",
            )
        except Exception:
            pass

    total_elapsed = round(time.time() - start_time, 1)

    if verbose:
        score = evaluation.get("score", evaluation.get("final_score", 0.0))
        icon = "PASS" if evaluation.get("success") else "FAIL"
        print(f"  [{icon}] score={score:.2f} ({len(trajectory)} steps, {total_elapsed:.0f}s)")

    return {
        "task_id": task_id,
        "goal": instruction,
        "steps": len(trajectory),
        "elapsed_seconds": total_elapsed,
        "completed": completed,
        "trajectory": trajectory,
        "evaluation": evaluation,
        "messages": messages,
    }


# ── 9. run_evaluation ──────────────────────────────────────────────

_DEFAULT_MAX_STEPS = 200
_DEFAULT_TIMEOUT = 3600

BASE_DIR = Path(__file__).parent
_MANIFEST = json.loads((BASE_DIR / "manifest.json").read_text())


async def run_evaluation(
    model: str,
    provider: str = "openai",
    base_url: str | None = None,
    api_key: str | None = None,
    task_filter: list[str] | None = None,
    environments_filter: list[str] | None = None,
    max_steps: int = _DEFAULT_MAX_STEPS,
    timeout_per_task: int = _DEFAULT_TIMEOUT,
    headless: bool = True,
    verbose: bool = True,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    server_host: str = "127.0.0.1",
    server_port: int = 8080,
    output_path: str = "results/webagentbench/results.json",
    seed: int | None = None,
    degradation: str | None = None,
) -> list[dict]:
    """Run evaluation across multiple tasks using the browser-use harness."""
    from .agent_eval import resolve_task_ids

    task_ids = resolve_task_ids(task_filter, environments_filter)

    # Resolve degradation config
    deg_config = None
    deg_path: Path | None = None
    if degradation:
        from .injector.config import DegradationConfig

        deg_path = Path(degradation)
        for candidate in [
            deg_path,
            BASE_DIR / degradation,
            BASE_DIR / "injector" / "variants" / degradation,
        ]:
            if candidate.exists():
                deg_path = candidate
                break
        if not deg_path.exists():
            print(f"ERROR: Degradation config not found: {degradation}", file=sys.stderr)
            return []
        deg_config = DegradationConfig.from_yaml(deg_path)
        if deg_config.base_task_id:
            task_ids = [t for t in task_ids if t == deg_config.base_task_id]

    if not task_ids:
        print("No tasks to evaluate.", file=sys.stderr)
        return []

    if verbose:
        print(f"Agent: {model} (via {provider})")
        print(f"Harness: browser-use")
        print(f"Tasks: {len(task_ids)}")
        if deg_config:
            print(f"Degradation: {deg_config.variant_id} ({deg_config.target_primitive})")
        print(f"Budget: steps={max_steps}, timeout={timeout_per_task}s")
        print(f"{'=' * 60}\n")

    from .tasks._registry import get_task as _get_task

    results: list[dict] = []
    for task_id in task_ids:
        task_def = _get_task(task_id)

        # Per-task budget from YAML when CLI uses defaults
        task_max_steps = max_steps
        task_timeout = timeout_per_task
        if max_steps == _DEFAULT_MAX_STEPS and timeout_per_task == _DEFAULT_TIMEOUT:
            if task_def.expected_steps:
                task_max_steps = int(task_def.expected_steps * 2.5)
            if task_def.time_limit_seconds:
                task_timeout = task_def.time_limit_seconds * 2

        if verbose:
            budget = f"steps<={task_max_steps}, timeout={task_timeout}s"
            print(f"[{task_id}] ({budget})")

        try:
            episode = await run_episode(
                task_id=task_id,
                model=model,
                provider=provider,
                base_url=base_url,
                api_key=api_key,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
                max_steps=task_max_steps,
                timeout_seconds=task_timeout,
                headless=headless,
                server_host=server_host,
                server_port=server_port,
                seed=seed or 42,
                degradation=degradation,
                degradation_config=deg_config,
                verbose=verbose,
            )

            episode_eval = episode["evaluation"]
            result: dict[str, Any] = {
                "task_id": task_id,
                "evaluation": episode_eval,
                "agent": {
                    "model": model,
                    "provider": provider,
                    "harness": "browser-use",
                    "steps": episode["steps"],
                    "elapsed_seconds": episode["elapsed_seconds"],
                    "completed": episode["completed"],
                    "trajectory": episode["trajectory"],
                    "messages": episode["messages"],
                },
            }
            if deg_config:
                result["degradation"] = {
                    "variant_id": deg_config.variant_id,
                    "target_primitive": deg_config.target_primitive,
                    "description": deg_config.description,
                }
            results.append(result)

            if verbose:
                print()

        except Exception as exc:
            logger.error("Error on task %s: %s", task_id, exc, exc_info=True)
            results.append({
                "task_id": task_id,
                "evaluation": {"score": 0.0, "success": False, "reasoning": f"Error: {exc}"},
                "agent": {
                    "model": model, "provider": provider, "harness": "browser-use",
                    "steps": 0, "elapsed_seconds": 0, "completed": False,
                    "trajectory": [], "messages": [],
                },
            })
            if verbose:
                print(f"  [ERROR] {exc}\n")

    _write_results(results, model, provider, output_path, degradation=deg_config)
    if verbose:
        _print_summary(results)
    return results


def _write_results(
    results: list[dict],
    model: str,
    provider: str,
    output_path: str,
    degradation: Any = None,
) -> None:
    total = len(results)
    if not total:
        return
    passed = sum(1 for r in results if r["evaluation"].get("success"))
    scores = [r["evaluation"].get("score", r["evaluation"].get("final_score", 0.0)) for r in results]
    times = [r.get("agent", {}).get("elapsed_seconds", 0) for r in results]
    steps = [r.get("agent", {}).get("steps", 0) for r in results]
    output: dict[str, Any] = {
        "benchmark": "WebAgentBench",
        "version": _MANIFEST["version"],
        "format": "browser-use",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": {"model": model, "provider": provider, "harness": "browser-use"},
        "results": results,
        "summary": {
            "total_tasks": total,
            "passed": passed,
            "failed": total - passed,
            "average_score": round(sum(scores) / total, 3),
            "average_steps": round(sum(steps) / total, 1),
            "average_elapsed_seconds": round(sum(times) / total, 1),
        },
    }
    if degradation:
        output["degradation"] = {
            "variant_id": degradation.variant_id,
            "target_primitive": degradation.target_primitive,
        }
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults written to {out_file}")


def _print_summary(results: list[dict]) -> None:
    total = len(results)
    passed = sum(1 for r in results if r["evaluation"].get("success"))
    scores = [r["evaluation"].get("score", r["evaluation"].get("final_score", 0.0)) for r in results]
    avg = sum(scores) / total if total else 0
    print(f"\n{'=' * 60}")
    print(f"SUMMARY: {passed}/{total} passed  |  avg score: {avg:+.3f}")
    print(f"{'=' * 60}")


# ── 10. CLI ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="WebAgentBench Evaluation (browser-use harness)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--provider", default="openai", choices=["vllm", "openai", "gemini"])
    parser.add_argument("--api-base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument(
        "--reasoning-effort", default=None,
        choices=["none", "minimal", "low", "medium", "high", "xhigh"],
    )
    parser.add_argument("--tasks", nargs="*")
    parser.add_argument("--environments", nargs="*")
    parser.add_argument("--degradation", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--max-steps", type=int, default=_DEFAULT_MAX_STEPS)
    parser.add_argument("--timeout", type=int, default=_DEFAULT_TIMEOUT)
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--no-headless", action="store_false", dest="headless")
    parser.add_argument("--server-host", default="127.0.0.1")
    parser.add_argument("--server-port", type=int, default=8080)
    parser.add_argument("--output", default="results/webagentbench/results.json")
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args()

    asyncio.run(run_evaluation(
        model=args.model,
        provider=args.provider,
        base_url=args.api_base_url,
        api_key=args.api_key,
        task_filter=args.tasks,
        environments_filter=args.environments,
        max_steps=args.max_steps,
        timeout_per_task=args.timeout,
        headless=args.headless,
        verbose=not args.quiet,
        temperature=args.temperature,
        reasoning_effort=args.reasoning_effort,
        server_host=args.server_host,
        server_port=args.server_port,
        output_path=args.output,
        seed=args.seed,
        degradation=args.degradation,
    ))


if __name__ == "__main__":
    main()
