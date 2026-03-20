"""
WebAgentBench Agent Evaluation — LLM-driven browser agent benchmark runner.

Connects an LLM agent (e.g., Llama-3.1-8B via vLLM) to the standalone
WebAgentBench pages through Playwright. The agent observes the page
accessibility tree, decides actions, and interacts with real HTML pages.

Usage:
    # Llama-3.1-8B via vLLM (requires running vLLM server on port 8000):
    python -m webagentbench.agent_eval \
        --model meta-llama/Llama-3.1-8B-Instruct \
        --provider vllm

    # OpenAI model:
    python -m webagentbench.agent_eval \
        --model gpt-4o \
        --provider openai

    # OpenAI reasoning (gpt-5*):
    python -m webagentbench.agent_eval \
        --model gpt-5.2 \
        --provider openai \
        --reasoning-effort high

    # Gemini model:
    python -m webagentbench.agent_eval \
        --model gemini-1.5-pro \
        --provider gemini

    # Specific pages only:
    python -m webagentbench.agent_eval \
        --model meta-llama/Llama-3.1-8B-Instruct \
        --provider vllm \
        --pages dark_checkout wizard_form

    # With visible browser:
    python -m webagentbench.agent_eval \
        --model meta-llama/Llama-3.1-8B-Instruct \
        --provider vllm \
        --no-headless
"""

import argparse
import json
import os
import sys
import time
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .runner import (
    start_server,
    wait_for_server,
    evaluate_state,
    get_manifest,
    print_summary,
    write_results,
)

from shared.format import SYSTEM_PROMPT, parse_action, build_initial_message, build_step_message
from shared.playwright_adapter import page_to_indexed_tree, execute_unified_action, _resolve

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent


# =============================================================================
# Context Window Management
# =============================================================================

# Maximum input tokens for the model.  Qwen's hard limit is 30 720;
# we leave room for the 4 096-token completion budget.
MAX_INPUT_TOKENS = 26_000


def _estimate_tokens(text: str) -> int:
    """Rough token estimate. Accessibility trees have many short tokens
    (brackets, numbers, quotes), so ~2.5 chars/token is conservative."""
    return int(len(text) / 2.5)


def _compact_tree(content: str, target_chars: int) -> str:
    """Shrink an accessibility tree by stripping non-interactive lines.

    Keeps all lines with [N] refs (interactive/meaningful elements) and
    drops pure-text lines, decorative separators, and url hints first.
    If still too large, truncates from the bottom.
    """
    if len(content) <= target_chars:
        return content
    split = content.find("\n\n")
    if split == -1:
        return content[:target_chars] + "\n[-- tree compacted --]"
    header = content[:split]
    tree = content[split + 2:]

    # Phase 1: drop /url lines and text-only lines without refs
    kept: list[str] = []
    for line in tree.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("[") and "]" in stripped:
            kept.append(line)  # has a ref number — keep
        elif "/url:" in stripped:
            continue  # drop url hints
        elif stripped.startswith("text ") and not stripped.startswith("text \""):
            continue  # drop bare text nodes
        else:
            kept.append(line)
    compacted = "\n".join(kept)

    # Phase 2: if still too large, hard-truncate at line boundary
    budget = target_chars - len(header) - 80
    if budget > 0 and len(compacted) > budget:
        compacted = compacted[:budget]
        last_nl = compacted.rfind("\n")
        if last_nl > 0:
            compacted = compacted[:last_nl]
        compacted += "\n[-- more elements omitted for context length --]"

    return header + "\n\n" + compacted


def _summarize_history(
    messages_to_summarize: list[dict],
    client,
    model: str,
    provider: str,
) -> str:
    """Use the LLM to compress older conversation turns into a brief summary."""
    turns_text = []
    for msg in messages_to_summarize:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        # Only keep the action/result lines, not the full trees
        if role == "assistant":
            turns_text.append(f"Agent: {content[:300]}")
        elif role == "user":
            # Extract just the Result: line, skip the tree
            result_line = content.split("\n\n")[0] if "\n\n" in content else content[:200]
            turns_text.append(f"Result: {result_line[:200]}")
    history_block = "\n".join(turns_text)

    summary_prompt = (
        "Summarize the following agent interaction history into a brief bullet-point "
        "list of what was accomplished. Focus on: which elements were interacted with, "
        "what actions were taken (clicks, form fills, navigation, submissions), and what "
        "progress was made toward the task. Keep it under 200 words.\n\n"
        f"{history_block}"
    )
    try:
        summary = llm_complete(
            client, model,
            [{"role": "user", "content": summary_prompt}],
            temperature=0.0,
            provider=provider,
        )
        return summary.strip()
    except Exception:
        # If summarization fails, fall back to a simple count
        return f"[{len(messages_to_summarize)} earlier interaction steps were completed]"


def _trim_messages(
    messages: list[dict],
    max_input_tokens: int | None = None,
    client=None,
    model: str = "",
    provider: str = "openai",
) -> list[dict]:
    """Trim conversation history to fit within the model's context window.

    Three-layer strategy:
    1. Compact oversized accessibility trees (drop non-interactive elements).
    2. If history is long and an LLM client is available, summarize older
       turns into a progress note so the agent retains semantic memory.
    3. As a last resort, drop older turns with a simple marker.
    """
    import copy

    if max_input_tokens is None:
        max_input_tokens = MAX_INPUT_TOKENS

    # Layer 1: compact any oversized user messages
    # Use 2.0 chars/token as a safe ceiling for structured tree content
    target_chars = int(max_input_tokens * 2.0)
    result = []
    for msg in messages:
        if msg.get("role") == "user" and len(msg.get("content", "")) > target_chars:
            msg = copy.copy(msg)
            msg["content"] = _compact_tree(msg["content"], target_chars)
        result.append(msg)
    messages = result

    total = sum(_estimate_tokens(m.get("content", "")) for m in messages)
    if total <= max_input_tokens:
        return messages

    if len(messages) <= 3:
        return messages

    # Always keep: system (0) and initial user message (1)
    head = messages[:2]
    head_tokens = sum(_estimate_tokens(m.get("content", "")) for m in head)
    budget = max_input_tokens - head_tokens - 200  # margin for summary/marker

    # Determine how many recent turns fit
    tail: list[dict] = []
    tail_tokens = 0
    for msg in reversed(messages[2:]):
        msg_tokens = _estimate_tokens(msg.get("content", ""))
        if tail_tokens + msg_tokens > budget:
            break
        tail.insert(0, msg)
        tail_tokens += msg_tokens

    if len(tail) == len(messages) - 2:
        return messages  # Nothing trimmed

    dropped = messages[2: len(messages) - len(tail)]

    # Layer 2: summarize dropped turns via LLM if client available
    if client is not None and len(dropped) >= 4:
        summary_text = _summarize_history(dropped, client, model, provider)
        marker = {
            "role": "user",
            "content": (
                f"[Summary of steps 1-{len(dropped) // 2}]\n{summary_text}\n"
                "[End of summary. Continue from current observation below.]"
            ),
        }
    else:
        # Layer 3: simple marker fallback
        marker = {
            "role": "user",
            "content": f"[{len(dropped)} earlier interaction steps omitted for context length]",
        }

    return head + [marker] + tail


# =============================================================================
# LLM Client (lightweight, no LLMOS dependency)
# =============================================================================

def _create_openai_client(base_url: str, api_key: str):
    """Create an OpenAI-compatible client (works for vLLM too)."""
    from openai import OpenAI
    return OpenAI(base_url=base_url, api_key=api_key)

def _create_gemini_client(api_key: str):
    """Create a Gemini client using google-genai."""
    from google import genai
    return genai.Client(api_key=api_key)

def _convert_to_gemini_format(messages: list[dict]) -> list[dict]:
    """Convert OpenAI-style messages to Gemini format."""
    converted = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "assistant":
            role = "model"
        converted.append({"role": role, "content": content})
    return converted


def _llm_complete_openai(
    client,
    model: str,
    messages: list[dict],
    temperature: float | None,
    reasoning_effort: str | None,
) -> str:
    """Send a chat completion request and return the text response."""
    kwargs: dict[str, object] = {
        "model": model,
        "messages": messages,
    }
    if temperature is not None:
        # GPT-5.* only supports the default temperature (=1); omit otherwise.
        if model.startswith("gpt-5") and temperature != 1:
            pass
        else:
            kwargs["temperature"] = temperature
    # Thinking models (Qwen3, etc.) need more tokens for <think>...</think> + action JSON.
    # 1024 is too small — thinking often consumes the budget before the action is emitted.
    max_tok = 4096
    if model.startswith("gpt-5"):
        kwargs["max_completion_tokens"] = max_tok
    else:
        kwargs["max_tokens"] = max_tok

    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort

    # Some OpenAI-compatible Qwen3 endpoints reject non-streaming calls unless
    # internal thinking is disabled explicitly.
    if model.startswith("qwen3"):
        kwargs["extra_body"] = {"enable_thinking": False}

    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


def _llm_complete_gemini(
    client,
    model: str,
    messages: list[dict],
    temperature: float | None,
) -> str:
    """Send a Gemini generate_content request and return the text response."""
    from google.genai import types

    gemini_messages = _convert_to_gemini_format(messages)
    system_instruction = None
    contents = []

    for msg in gemini_messages:
        if msg["role"] == "system":
            system_instruction = msg["content"]
        else:
            contents.append(
                types.Content(
                    role="user" if msg["role"] == "user" else "model",
                    parts=[types.Part(text=msg["content"])],
                )
            )

    config_kwargs = {"system_instruction": system_instruction}
    if temperature is not None:
        config_kwargs["temperature"] = temperature
    generation_config = types.GenerateContentConfig(**config_kwargs)

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=generation_config,
    )
    return response.text or ""


def llm_complete(
    client,
    model: str,
    messages: list[dict],
    temperature: float | None = None,
    provider: str = "openai",
    reasoning_effort: str | None = None,
) -> str:
    """Send a completion request and return the text response."""
    if provider == "gemini":
        return _llm_complete_gemini(client, model, messages, temperature)
    return _llm_complete_openai(client, model, messages, temperature, reasoning_effort)


def _http_json(url: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    """Issue a JSON HTTP request and return the decoded response body."""
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request) as response:
        response_body = response.read().decode("utf-8")
        return json.loads(response_body) if response_body else {}


def _capture_benchmark_state(page, dom_checks: list[dict] | None = None) -> dict:
    """Capture the benchmark harness state from the browser."""
    benchmark_state = page.evaluate(
        "() => JSON.parse(JSON.stringify(window.__benchmarkState || {}))"
    )
    if dom_checks:
        benchmark_state["dom_checks"] = _capture_dom_checks(page, dom_checks)
    return benchmark_state


def _render_template(value, targets: dict):
    """Recursively substitute {target.foo} placeholders in nested structures."""
    if isinstance(value, str):
        rendered = value
        for key, replacement in targets.items():
            rendered = rendered.replace(f"{{target.{key}}}", str(replacement))
        return rendered
    if isinstance(value, list):
        return [_render_template(item, targets) for item in value]
    if isinstance(value, dict):
        return {key: _render_template(item, targets) for key, item in value.items()}
    return value


def resolve_tasks(
    manifest: dict,
    *,
    pages_filter: list[str] | None = None,
    task_filter: list[str] | None = None,
    environments_filter: list[str] | None = None,
    include_all: bool = False,
) -> list[tuple[str, dict]]:
    """Resolve CLI filters into a stable, de-duplicated task list."""
    page_index = {page["page_id"]: page for page in manifest.get("pages", [])}
    env_index = {env["env_id"]: env for env in manifest.get("environments", [])}
    task_index: dict[str, tuple[dict, dict]] = {}

    for env in manifest.get("environments", []):
        for task in env.get("tasks", []):
            task_id = task["task_id"]
            if task_id in task_index:
                raise ValueError(f"Duplicate task_id in manifest environments: {task_id}")
            task_index[task_id] = (env, task)

    selected: list[tuple[str, dict]] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, identifier: str, payload: dict) -> None:
        key = (kind, identifier)
        if key not in seen:
            seen.add(key)
            selected.append((kind, payload))

    if include_all:
        for page in manifest.get("pages", []):
            add("page", page["page_id"], page)
        for env in manifest.get("environments", []):
            env_meta = {k: v for k, v in env.items() if k != "tasks"}
            for task in env.get("tasks", []):
                add("env_task", task["task_id"], {**task, "env": env_meta})

    for page_id in pages_filter or []:
        page = page_index.get(page_id)
        if page is None:
            raise ValueError(f"Unknown page_id: {page_id}")
        add("page", page_id, page)

    for task_id in task_filter or []:
        pair = task_index.get(task_id)
        if pair is None:
            raise ValueError(f"Unknown environment task_id: {task_id}")
        env, task = pair
        env_meta = {k: v for k, v in env.items() if k != "tasks"}
        add("env_task", task_id, {**task, "env": env_meta})

    for env_id in environments_filter or []:
        env = env_index.get(env_id)
        if env is None:
            raise ValueError(f"Unknown environment id: {env_id}")
        env_meta = {k: v for k, v in env.items() if k != "tasks"}
        for task in env.get("tasks", []):
            add("env_task", task["task_id"], {**task, "env": env_meta})

    if not selected:
        for page in manifest.get("pages", []):
            add("page", page["page_id"], page)

    return selected


# =============================================================================
# Agent Loop
# =============================================================================


def _extract_targets(action: dict, ref_map: dict, page) -> dict:
    """Extract locator info for the refs used in an action, for replay."""
    def _safe_selector(locator):
        js = r"""
        (el) => {
            const esc = (s) => (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/[^a-zA-Z0-9_-]/g, "\\\\$&");
            const cls = (node) => {
                if (!node) return "";
                let classes = [];
                if (node.classList && node.classList.length) {
                    classes = Array.from(node.classList).filter(Boolean).slice(0, 3);
                } else if (node.className) {
                    classes = String(node.className).split(/\\s+/).filter(Boolean).slice(0, 3);
                }
                return classes.length ? "." + classes.map(esc).join(".") : "";
            };
            function cssPath(node) {
                if (!node || node.nodeType !== 1) return null;
                if (node.id) return "#" + esc(node.id);
                const parts = [];
                let cur = node;
                while (cur && cur.nodeType === 1 && cur.tagName.toLowerCase() !== "html") {
                    let sel = cur.tagName.toLowerCase() + cls(cur);
                    const parent = cur.parentElement;
                    if (parent) {
                        const siblings = Array.from(parent.children).filter(c => c.tagName === cur.tagName);
                        if (siblings.length > 1) {
                            sel += `:nth-of-type(${siblings.indexOf(cur) + 1})`;
                        }
                    }
                    parts.unshift(sel);
                    if (parts.length >= 5) break;
                    cur = parent;
                }
                return parts.join(" > ");
            }
            return cssPath(el);
        }
        """
        return locator.evaluate(js)

    targets = {}
    for key in ("ref", "from_ref", "to_ref"):
        ref = action.get(key)
        if ref is not None and ref in ref_map:
            info = ref_map[ref]
            payload = {"role": info.role, "name": info.name, "nth": info.nth}
            try:
                locator = _resolve(page, info)
                bbox = locator.bounding_box()
                if bbox:
                    payload["bbox"] = bbox
                selector = _safe_selector(locator)
                if selector:
                    payload["selector"] = selector
            except Exception:
                pass
            targets[key] = payload
    return targets


def _capture_dom_checks(page, checks: list[dict]) -> dict[str, str]:
    """Capture manifest-defined DOM evidence after the agent finishes."""
    captured: dict[str, str] = {}
    for check in checks:
        selector = check.get("selector")
        if not selector:
            continue
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            text = locator.text_content()
            if text is None:
                text = locator.input_value()
            if text is None:
                text = locator.get_attribute("value")
            if text is not None:
                captured[selector] = text
        except Exception:
            continue
    return captured


def run_agent_on_page(
    page,
    client,
    model: str,
    provider: str,
    instruction: str,
    reasoning_effort: str | None = None,
    max_steps: int = 30,
    timeout_seconds: int = 180,
    verbose: bool = True,
    temperature: float | None = None,
) -> dict:
    """
    Run the LLM agent on a single page until completion or timeout.

    Uses the unified indexed accessibility tree format from shared.format.
    """
    start_time = time.time()
    trajectory = []

    tree_text, ref_map = page_to_indexed_tree(page)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_initial_message(instruction, tree_text)},
    ]

    for step in range(max_steps):
        elapsed = time.time() - start_time
        if elapsed > timeout_seconds:
            if verbose:
                print(f"    Step {step + 1}: TIMEOUT ({elapsed:.0f}s)")
            break

        # Trim conversation history to fit within model context window.
        # Pass client so _trim_messages can use LLM summarization when needed.
        trimmed = _trim_messages(
            messages, client=client, model=model, provider=provider,
        )
        try:
            raw_response = llm_complete(
                client, model, trimmed,
                temperature=temperature, provider=provider,
                reasoning_effort=reasoning_effort,
            )
        except Exception as llm_err:
            err_str = str(llm_err)
            if "input length" in err_str or "30720" in err_str or "context_length" in err_str:
                # Overflow — aggressively compact and retry once
                if verbose:
                    print(f"    Step {step + 1}: context overflow, compacting and retrying...")
                trimmed = _trim_messages(
                    messages, max_input_tokens=MAX_INPUT_TOKENS - 4000,
                    client=client, model=model, provider=provider,
                )
                raw_response = llm_complete(
                    client, model, trimmed,
                    temperature=temperature, provider=provider,
                    reasoning_effort=reasoning_effort,
                )
            else:
                raise
        action = parse_action(raw_response)
        thought = action.get("thought", "")

        if verbose:
            action_name = action.get("action", "?")
            ref = action.get("ref", "")
            print(f"    Step {step + 1}: {action_name}", end="")
            if ref:
                print(f" (ref={ref})", end="")
            print()
            if thought:
                print(f"      Thought: {thought[:80]}{'...' if len(thought) > 80 else ''}")

        # Snapshot locator info for the refs used in this action, for replay
        targets = _extract_targets(action, ref_map, page)

        try:
            status = execute_unified_action(page, action, ref_map)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            status = f"ERROR: {err}"
            if verbose:
                print(f"      Action error: {err}")
        trajectory.append({
            "step": step + 1,
            "thought": thought,
            "action": {k: v for k, v in action.items() if k != "thought"},
            "targets": targets,
            "status": status,
            "elapsed_seconds": round(time.time() - start_time, 1),
        })
        messages.append({"role": "assistant", "content": raw_response})

        if status == "FINISH":
            if verbose:
                print(f"    Agent declared task complete at step {step + 1}")
            break

        page.wait_for_timeout(500)

        tree_text, ref_map = page_to_indexed_tree(page)
        messages.append({"role": "user", "content": build_step_message(status, tree_text)})

    return {
        "steps": len(trajectory),
        "trajectory": trajectory,
        "elapsed_seconds": round(time.time() - start_time, 1),
        "completed": any(t["status"] == "FINISH" for t in trajectory),
        "messages": messages,  # Full conversation for training export
    }


# =============================================================================
# Main Evaluation Loop
# =============================================================================

def _run_legacy_page_task(
    *,
    browser,
    bench_url: str,
    page_def: dict,
    client,
    model: str,
    provider: str,
    max_steps: int,
    timeout_per_page: int,
    reasoning_effort: str | None,
    verbose: bool,
    temperature: float | None,
) -> dict:
    """Execute one legacy single-page benchmark task."""
    page_id = page_def["page_id"]
    instruction = page_def["instruction"]
    benchmark_state: dict = {}

    if verbose:
        print(f"[{page_id}] {page_def['title']}")
        print(f"  Instruction: {instruction[:100]}{'...' if len(instruction) > 100 else ''}")

    context = browser.new_context()
    page = context.new_page()

    try:
        page.goto(f"{bench_url}/pages/{page_id}")
        page.wait_for_load_state("networkidle")

        agent_result = run_agent_on_page(
            page=page,
            client=client,
            model=model,
            provider=provider,
            instruction=instruction,
            reasoning_effort=reasoning_effort,
            max_steps=max_steps,
            timeout_seconds=timeout_per_page,
            verbose=verbose,
            temperature=temperature,
        )

        benchmark_state = _capture_benchmark_state(
            page,
            page_def.get("success_criteria", {}).get("dom_check", []),
        )
        evaluation = evaluate_state(bench_url, page_id, benchmark_state)
    except Exception as exc:
        logger.error("Error on page %s: %s", page_id, exc)
        agent_result = {
            "steps": 0,
            "trajectory": [],
            "elapsed_seconds": 0,
            "completed": False,
            "messages": [],
        }
        evaluation = {"score": -1.0, "success": False, "reasoning": f"Error: {exc}"}
    finally:
        context.close()

    if verbose:
        icon = "PASS" if evaluation.get("success") else "FAIL"
        score = evaluation.get("score", -1.0)
        print(
            f"  [{icon}] score={score:+.1f} "
            f"({agent_result['steps']} steps, {agent_result['elapsed_seconds']:.0f}s)"
        )
        print(f"  {evaluation.get('reasoning', '')}")
        print()

    return {
        "page_id": page_id,
        "task_id": page_id,
        "task_type": "page",
        "title": page_def["title"],
        "instruction": instruction,
        "primitives": page_def["primary_primitives"],
        "difficulty": page_def["difficulty"],
        "benchmark_state": benchmark_state,
        "evaluation": evaluation,
        "replay": {"kind": "page", "url": f"/pages/{page_id}"},
        "agent": {
            "model": model,
            "provider": provider,
            "steps": agent_result["steps"],
            "elapsed_seconds": agent_result["elapsed_seconds"],
            "completed": agent_result["completed"],
            "trajectory": agent_result["trajectory"],
            "messages": agent_result.get("messages"),
        },
    }


def _run_env_task(
    *,
    browser,
    bench_url: str,
    task_def: dict,
    client,
    model: str,
    provider: str,
    max_steps: int,
    timeout_per_page: int,
    reasoning_effort: str | None,
    verbose: bool,
    temperature: float | None,
    seed: int | None,
) -> dict:
    """Execute one advanced environment task against the FastAPI backend."""
    env = task_def["env"]
    env_id = env["env_id"]
    task_id = task_def["task_id"]
    base_url = env["base_url"]
    session_id: str | None = None
    benchmark_state: dict = {}
    context = None
    created: dict = {}
    page_title = task_def.get("title", task_id)
    instruction = task_def.get("instruction_template", "")

    try:
        session_payload = {"task_id": task_id}
        if seed is not None:
            session_payload["seed"] = seed

        created = _http_json(
            f"{bench_url}/api/env/{env_id}/session",
            method="POST",
            payload=session_payload,
        )
        session_id = created["session_id"]
        start_path = created.get("start_path", task_def.get("start_path", "/"))
        resolved_targets = created.get("resolved_targets", {})
        rendered_task = _render_template(task_def, resolved_targets)
        instruction = rendered_task.get("instruction") or rendered_task.get("instruction_template", "")
        page_title = rendered_task.get("title", task_id)
        effective_timeout = max(timeout_per_page, int(task_def.get("time_limit_seconds", timeout_per_page)))
        recommended_steps = 50 if task_def.get("difficulty") == "hard" else 35
        effective_steps = max(max_steps, int(task_def.get("max_steps", recommended_steps)))

        if verbose:
            print(f"[{env_id}:{task_id}] {page_title}")
            print(f"  Instruction: {instruction[:120]}{'...' if len(instruction) > 120 else ''}")

        context = browser.new_context()
        page = context.new_page()
        session_url = (
            f"{bench_url}{base_url}{start_path}?session={urllib.parse.quote(session_id)}"
            if start_path.startswith("/")
            else f"{bench_url}{base_url}/{start_path}?session={urllib.parse.quote(session_id)}"
        )

        page.goto(session_url)
        page.wait_for_load_state("networkidle")

        agent_result = run_agent_on_page(
            page=page,
            client=client,
            model=model,
            provider=provider,
            instruction=instruction,
            reasoning_effort=reasoning_effort,
            max_steps=effective_steps,
            timeout_seconds=effective_timeout,
            verbose=verbose,
            temperature=temperature,
        )

        benchmark_state = _capture_benchmark_state(
            page,
            rendered_task.get("success_criteria", {}).get("dom_check", []),
        )
        evaluation = _http_json(
            f"{bench_url}/api/env/{env_id}/evaluate",
            method="POST",
            payload={
                "session_id": session_id,
                "task_id": task_id,
                "benchmark_state": benchmark_state,
                "trajectory": agent_result["trajectory"],
            },
        )
    except Exception as exc:
        logger.error("Error on environment task %s:%s: %s", env_id, task_id, exc)
        agent_result = {
            "steps": 0,
            "trajectory": [],
            "elapsed_seconds": 0,
            "completed": False,
            "messages": [],
        }
        evaluation = {"score": -1.0, "success": False, "reasoning": f"Error: {exc}"}
    finally:
        if context is not None:
            context.close()
        if session_id is not None:
            try:
                _http_json(
                    f"{bench_url}/api/env/{env_id}/session/{urllib.parse.quote(session_id)}",
                    method="DELETE",
                )
            except Exception as cleanup_exc:
                logger.warning(
                    "Failed to destroy session %s for %s:%s: %s",
                    session_id,
                    env_id,
                    task_id,
                    cleanup_exc,
                )

    if verbose:
        icon = "PASS" if evaluation.get("success") else "FAIL"
        score = evaluation.get("score", evaluation.get("final_score", -1.0))
        print(
            f"  [{icon}] score={score:+.2f} "
            f"({agent_result['steps']} steps, {agent_result['elapsed_seconds']:.0f}s)"
        )
        print(f"  {evaluation.get('reasoning', '')}")
        print()

    return {
        "page_id": task_id,
        "task_id": task_id,
        "env_id": env_id,
        "task_type": "env",
        "seed": created.get("seed", seed),
        "title": page_title,
        "instruction": instruction,
        "primitives": task_def.get("primary_primitives", []),
        "difficulty": task_def.get("difficulty", "unknown"),
        "benchmark_state": benchmark_state,
        "evaluation": evaluation,
        "base_url": base_url,
        "replay": {
            "kind": "env",
            "env_id": env_id,
            "task_id": task_id,
            "seed": created.get("seed", seed),
            "base_url": base_url,
            "start_path": start_path,
        },
        "agent": {
            "model": model,
            "provider": provider,
            "steps": agent_result["steps"],
            "elapsed_seconds": agent_result["elapsed_seconds"],
            "completed": agent_result["completed"],
            "trajectory": agent_result["trajectory"],
            "messages": agent_result.get("messages"),
        },
    }


def run_evaluation(
    model: str,
    provider: str = "vllm",
    base_url: str = "http://localhost:8000/v1",
    api_key: str = "dummy",
    pages_filter: list[str] | None = None,
    task_filter: list[str] | None = None,
    environments_filter: list[str] | None = None,
    include_all: bool = False,
    max_steps: int = 30,
    timeout_per_page: int = 180,
    headless: bool = True,
    verbose: bool = True,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    server_host: str = "127.0.0.1",
    server_port: int = 8080,
    output_path: str = "results/webagentbench/results.json",
    seed: int | None = None,
) -> list[dict]:
    """
    Run the full WebAgentBench evaluation with an LLM agent.

    Args:
        model: Model name (e.g., "meta-llama/Llama-3.1-8B-Instruct").
        provider: LLM provider ("vllm", "openai", "gemini").
        base_url: API base URL for the LLM.
        api_key: API key.
        pages_filter: Optional list of legacy page_ids to evaluate.
        task_filter: Optional list of advanced environment task_ids to evaluate.
        environments_filter: Optional list of advanced environment ids to evaluate.
        include_all: Run both legacy pages and all advanced environment tasks.
        max_steps: Max agent steps per page.
        timeout_per_page: Timeout per page in seconds.
        headless: Run browser in headless mode.
        verbose: Print progress.
        temperature: LLM sampling temperature (None = provider default).
        reasoning_effort: Reasoning effort for OpenAI models (low/medium/high/xhigh).
        server_host: WebAgentBench server host.
        server_port: WebAgentBench server port.
        output_path: Path to write results JSON.
        seed: Optional deterministic seed for advanced environment sessions.

    Returns:
        List of per-page result dicts.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed. Run: uv pip install playwright && playwright install chromium",
              file=sys.stderr)
        sys.exit(1)

    # Create LLM client
    if provider == "gemini":
        client = _create_gemini_client(api_key)
    else:
        client = _create_openai_client(base_url, api_key)

    bench_url = f"http://{server_host}:{server_port}"
    server_proc = None
    using_existing_server = wait_for_server(server_host, server_port, timeout=2)

    if using_existing_server:
        if verbose:
            print(f"Using existing WebAgentBench server at {bench_url}")
    else:
        if verbose:
            print(f"Starting WebAgentBench server on {bench_url}...")
        server_proc = start_server(server_host, server_port)

    try:
        if not wait_for_server(server_host, server_port):
            print("ERROR: WebAgentBench server failed to start", file=sys.stderr)
            if server_proc is not None:
                server_proc.terminate()
            sys.exit(1)
        if verbose:
            print(f"Server ready at {bench_url}")

        # Load manifest
        manifest = get_manifest(bench_url)
        try:
            selected_tasks = resolve_tasks(
                manifest,
                pages_filter=pages_filter,
                task_filter=task_filter,
                environments_filter=environments_filter,
                include_all=include_all,
            )
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return []

        if not selected_tasks:
            print("No tasks to evaluate.", file=sys.stderr)
            return []

        if verbose:
            print(f"\nAgent: {model} (via {provider})")
            legacy_count = sum(1 for kind, _ in selected_tasks if kind == "page")
            env_count = sum(1 for kind, _ in selected_tasks if kind == "env_task")
            print(f"Tasks: {len(selected_tasks)} total ({legacy_count} legacy pages, {env_count} env tasks)")
            print(f"Max steps per page: {max_steps}")
            print(f"Timeout per page: {timeout_per_page}s")
            print(f"{'='*60}\n")

        results = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)

            for task_type, task_def in selected_tasks:
                if task_type == "page":
                    result = _run_legacy_page_task(
                        browser=browser,
                        bench_url=bench_url,
                        page_def=task_def,
                        client=client,
                        model=model,
                        provider=provider,
                        max_steps=max_steps,
                        timeout_per_page=timeout_per_page,
                        reasoning_effort=reasoning_effort,
                        verbose=verbose,
                        temperature=temperature,
                    )
                elif task_type == "env_task":
                    result = _run_env_task(
                        browser=browser,
                        bench_url=bench_url,
                        task_def=task_def,
                        client=client,
                        model=model,
                        provider=provider,
                        max_steps=max_steps,
                        timeout_per_page=timeout_per_page,
                        reasoning_effort=reasoning_effort,
                        verbose=verbose,
                        temperature=temperature,
                        seed=seed,
                    )
                else:
                    raise ValueError(f"Unsupported task type: {task_type}")
                results.append(result)

            browser.close()

        # Write results
        _write_agent_results(results, model, provider, output_path, bench_url, manifest=manifest)
        if verbose:
            print_summary(results)

        return results

    finally:
        if server_proc is not None:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except Exception:
                server_proc.kill()
                server_proc.wait()


def _write_agent_results(
    results: list[dict],
    model: str,
    provider: str,
    output_path: str,
    server_url: str | None = None,
    *,
    manifest: dict | None = None,
):
    """Write agent evaluation results to a JSON file and emit HTML visualization."""
    total = len(results)
    passed = sum(1 for r in results if r["evaluation"].get("success"))
    avg_score = (
        sum(r["evaluation"].get("score", r["evaluation"].get("final_score", -1.0)) for r in results) / total
        if total
        else 0
    )

    prim_scores: dict[str, list[float]] = {}
    for r in results:
        score = r["evaluation"].get("score", r["evaluation"].get("final_score", -1.0))
        for prim in r.get("primitives", []):
            prim_scores.setdefault(prim, []).append(score)

    output_version = "1.0.0"
    page_meta: dict[str, dict] = {}

    if manifest is None:
        manifest_path = BASE_DIR / "manifest.json"
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except Exception:
            manifest = None

    if manifest:
        output_version = manifest.get("version", output_version)
        for page in manifest.get("pages", []):
            page_meta[page["page_id"]] = page
        for env in manifest.get("environments", []):
            env_meta = {k: v for k, v in env.items() if k != "tasks"}
            for task in env.get("tasks", []):
                page_meta[task["task_id"]] = {**env_meta, **task}

    for result in results:
        page_meta[result["page_id"]] = {
            **page_meta.get(result["page_id"], {}),
            "page_id": result.get("page_id"),
            "task_id": result.get("task_id"),
            "task_type": result.get("task_type", "page"),
            "title": result.get("title"),
            "instruction": result.get("instruction"),
            "difficulty": result.get("difficulty"),
            "env_id": result.get("env_id"),
            "base_url": result.get("base_url") or result.get("replay", {}).get("base_url"),
            "start_path": result.get("replay", {}).get("start_path"),
            "replay": result.get("replay"),
        }

    output = {
        "benchmark": "WebAgentBench",
        "version": output_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": {
            "model": model,
            "provider": provider,
        },
        "results": results,
        "summary": {
            "total_pages": total,
            "passed": passed,
            "failed": total - passed,
            "average_score": round(avg_score, 3),
            "primitive_scores": {
                p: round(sum(s) / len(s), 3) for p, s in sorted(prim_scores.items())
            },
        },
    }

    # Attach page metadata for richer visualization (instruction, primitives, etc.)
    output["page_meta"] = page_meta

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults written to {output_file}")

    # Auto-generate visualization HTML (best-effort)
    try:
        from .visualize import generate_html
        out_path = output_file
        viz_name = str(out_path.with_suffix("").name) + "_viz.html"
        html_content = generate_html(output, server_url or "http://127.0.0.1:8080")

        # Write into /static for same-origin playback
        static_dir = BASE_DIR / "static"
        static_dir.mkdir(parents=True, exist_ok=True)
        static_out = static_dir / viz_name
        with open(static_out, "w") as f:
            f.write(html_content)

        print(f"Visualization written to {static_out}")
        if server_url:
            print(f"Visualization served at {server_url.rstrip('/')}/static/{static_out.name}")
    except Exception as e:
        print(f"Warning: failed to generate visualization HTML: {e}")


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="WebAgentBench Agent Evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Agent / model
    parser.add_argument("--model", type=str, required=True,
                        help="Model name (e.g., meta-llama/Llama-3.1-8B-Instruct, gpt-4o)")
    parser.add_argument("--provider", type=str, default="vllm",
                        choices=["vllm", "openai", "gemini"],
                        help="LLM provider (default: vllm)")
    parser.add_argument("--api-base-url", type=str, default=None,
                        help="API base URL (default: provider-dependent)")
    parser.add_argument("--api-key", type=str, default=None,
                        help="API key (default: provider-dependent)")
    parser.add_argument("--temperature", type=float, default=None,
                        help="LLM sampling temperature (default: provider default)")
    parser.add_argument("--reasoning-effort", type=str, default=None,
                        choices=["none", "minimal", "low", "medium", "high", "xhigh"],
                        help="OpenAI reasoning effort (gpt-5*)")

    # Benchmark
    parser.add_argument("--pages", nargs="*",
                        help="Specific legacy page_ids to evaluate")
    parser.add_argument("--tasks", nargs="*",
                        help="Specific advanced environment task_ids to evaluate")
    parser.add_argument("--environments", nargs="*",
                        help="Run all tasks from the listed advanced environments")
    parser.add_argument("--all", action="store_true",
                        help="Run all legacy pages and all advanced environment tasks")
    parser.add_argument("--seed", type=int, default=None,
                        help="Deterministic seed for advanced environment sessions")
    parser.add_argument("--max-steps", type=int, default=30,
                        help="Max agent steps per page (default: 30)")
    parser.add_argument("--timeout", type=int, default=180,
                        help="Timeout per page in seconds (default: 180)")

    # Browser
    parser.add_argument("--headless", action="store_true", default=True,
                        help="Run browser in headless mode (default)")
    parser.add_argument("--no-headless", action="store_false", dest="headless",
                        help="Run browser with visible window")

    # Server
    parser.add_argument("--server-host", type=str, default="127.0.0.1",
                        help="WebAgentBench server host (default: 127.0.0.1)")
    parser.add_argument("--server-port", type=int, default=8080,
                        help="WebAgentBench server port (default: 8080)")

    # Output
    parser.add_argument("--output", type=str, default="results/webagentbench/results.json",
                        help="Output file (default: results/webagentbench/results.json)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Less output")

    args = parser.parse_args()

    # Resolve provider-specific defaults
    if args.api_base_url is None:
        if args.provider == "vllm":
            args.api_base_url = (
                os.environ.get("WEBAGENTBENCH_API_BASE_URL")
                or "http://localhost:8000/v1"
            )
        elif args.provider == "openai":
            args.api_base_url = os.environ.get("OPENAI_API_BASE_URL") or "https://api.openai.com/v1"

    if args.api_key is None:
        if args.provider == "vllm":
            args.api_key = os.environ.get("WEBAGENTBENCH_API_KEY") or "dummy"
        elif args.provider == "openai":
            args.api_key = os.environ.get("OPENAI_API_KEY", "")
            if not args.api_key:
                print("ERROR: Set OPENAI_API_KEY or pass --api-key", file=sys.stderr)
                sys.exit(1)
        elif args.provider == "gemini":
            args.api_key = os.environ.get("GEMINI_API_KEY", "")
            if not args.api_key:
                print("ERROR: Set GEMINI_API_KEY or pass --api-key", file=sys.stderr)
                sys.exit(1)

    run_evaluation(
        model=args.model,
        provider=args.provider,
        base_url=args.api_base_url,
        api_key=args.api_key,
        pages_filter=args.pages,
        task_filter=args.tasks,
        environments_filter=args.environments,
        include_all=args.all,
        max_steps=args.max_steps,
        timeout_per_page=args.timeout,
        headless=args.headless,
        verbose=not args.quiet,
        temperature=args.temperature,
        reasoning_effort=args.reasoning_effort,
        server_host=args.server_host,
        server_port=args.server_port,
        output_path=args.output,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
