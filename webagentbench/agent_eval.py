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
import re
import sys
import time
import logging
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

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent


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


def _strip_thinking_tags(text: str) -> str:
    """Strip <think>...</think> tags (Qwen3 / reasoning model pattern)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences from response."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_action(raw: str) -> dict:
    """Parse the LLM response into an action dict. Handles markdown fences and thinking tags."""
    cleaned = _strip_thinking_tags(raw)
    cleaned = _strip_markdown_fences(cleaned)

    # Try JSON parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from mixed text
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return {"action": "noop", "thought": f"Failed to parse: {raw[:200]}"}


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
    # GPT-5.* models require max_completion_tokens instead of max_tokens.
    if model.startswith("gpt-5"):
        kwargs["max_completion_tokens"] = 1024
    else:
        kwargs["max_tokens"] = 1024

    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort

    # Qwen3 endpoints on some OpenAI-compatible providers require
    # explicitly disabling internal thinking for non-streaming calls.
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


# =============================================================================
# Accessibility Tree Extraction
# =============================================================================

def get_accessibility_tree(page) -> str:
    """
    Extract a simplified accessibility tree from the page using Playwright.

    Returns a YAML text representation of accessible elements
    suitable for LLM consumption. Uses Playwright 1.49+ aria_snapshot() API.
    """
    try:
        snapshot = page.locator("body").aria_snapshot()
        return snapshot if snapshot else "(empty page)"
    except Exception as e:
        logger.warning("aria_snapshot failed: %s", e)
        return "(empty page)"


# =============================================================================
# Agent System Prompt
# =============================================================================

SYSTEM_PROMPT = """\
You are a web browsing agent. You interact with web pages by issuing actions.

## Observation
You receive the page's accessibility tree — a structured text representation of all visible and interactive elements on the page.

## Actions
Respond with a single JSON object containing:
- "thought": Brief reasoning about what to do next
- "action": One of the actions below
- Additional parameters as required by the action

Available actions:

| Action    | Parameters         | Description                         |
|-----------|--------------------|-------------------------------------|
| click     | selector           | Click an element (by text or role)  |
| fill      | selector, text     | Type text into an input field       |
| select    | selector, value    | Select a dropdown option            |
| check     | selector           | Check a checkbox                    |
| uncheck   | selector           | Uncheck a checkbox                  |
| press     | key                | Press a keyboard key (e.g., Enter)  |
| scroll    | direction          | Scroll the page (up/down)           |
| finish    |                    | Declare the task complete            |

The `selector` should be the accessible name (text label) of the element you want to interact with.
If the accessibility tree shows `button "Save"` or `textbox "Email"`, use just `Save` or `Email` as the selector.

## Rules
- Always respond with valid JSON only — no extra text outside the JSON.
- Use "thought" to explain your reasoning before acting.
- If the task appears complete, use the "finish" action.
- Be precise: match element names exactly as shown in the accessibility tree.
- Do NOT hallucinate elements that are not in the accessibility tree.
"""


# =============================================================================
# Browser Action Execution
# =============================================================================

_ROLE_PREFIXED_SELECTOR_RE = re.compile(
    r'^(button|link|menuitem|tab|checkbox|radio|textbox|spinbutton|searchbox|combobox)\s+"([^"]+)"$',
    re.IGNORECASE,
)


def _normalize_selector(selector: str) -> str:
    """Strip role prefixes like `button "Save"` to the accessible name only."""
    selector = (selector or "").strip()
    match = _ROLE_PREFIXED_SELECTOR_RE.match(selector)
    if match:
        return match.group(2).strip()
    return selector


def _capture_dom_checks(page, checks: list[dict]) -> dict[str, str]:
    """Capture DOM contents for manifest dom_check rules."""
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

def execute_action(page, action: dict) -> str:
    """
    Execute a parsed action on the Playwright page.

    Returns a status string describing what happened.
    """
    action_type = action.get("action", "noop")
    selector = _normalize_selector(action.get("selector", ""))
    text = action.get("text", "")
    value = action.get("value", "")
    key = action.get("key", "")
    direction = action.get("direction", "down")

    try:
        if action_type == "click":
            _click_element(page, selector)
            return f"Clicked: {selector}"

        elif action_type == "fill":
            _fill_element(page, selector, text)
            return f"Filled '{selector}' with '{text[:50]}'"

        elif action_type == "select":
            _select_element(page, selector, value)
            return f"Selected '{value}' in '{selector}'"

        elif action_type == "check":
            locator = page.get_by_role("checkbox", name=selector)
            if not locator.count():
                locator = page.get_by_label(selector)
            locator.first.check()
            return f"Checked: {selector}"

        elif action_type == "uncheck":
            locator = page.get_by_role("checkbox", name=selector)
            if not locator.count():
                locator = page.get_by_label(selector)
            locator.first.uncheck()
            return f"Unchecked: {selector}"

        elif action_type == "press":
            page.keyboard.press(key)
            return f"Pressed: {key}"

        elif action_type == "scroll":
            delta = -300 if direction == "up" else 300
            page.mouse.wheel(0, delta)
            return f"Scrolled {direction}"

        elif action_type == "finish":
            return "FINISH"

        elif action_type == "noop":
            return "No action taken"

        else:
            return f"Unknown action: {action_type}"

    except Exception as e:
        return f"Action failed ({action_type}): {e}"


def _click_element(page, selector: str):
    """Click an element by trying multiple Playwright selector strategies."""
    selector = _normalize_selector(selector)

    # Try role-based selectors first
    for role in ("button", "link", "menuitem", "tab", "checkbox", "radio"):
        locator = page.get_by_role(role, name=selector)
        if locator.count() > 0:
            locator.first.click()
            return

    # Try by label
    locator = page.get_by_label(selector)
    if locator.count() > 0:
        locator.first.click()
        return

    # Try by text
    locator = page.get_by_text(selector, exact=False)
    if locator.count() > 0:
        locator.first.click()
        return

    # Fallback: CSS selector
    page.click(f"text={selector}")


def _fill_element(page, selector: str, text: str):
    """Fill an input element by trying multiple strategies."""
    selector = _normalize_selector(selector)

    # Try by label
    locator = page.get_by_label(selector)
    if locator.count() > 0:
        locator.first.fill(text)
        return

    # Try by placeholder
    locator = page.get_by_placeholder(selector)
    if locator.count() > 0:
        locator.first.fill(text)
        return

    # Try by role
    for role in ("textbox", "spinbutton", "searchbox"):
        locator = page.get_by_role(role, name=selector)
        if locator.count() > 0:
            locator.first.fill(text)
            return

    # Fallback
    page.fill(f"[aria-label='{selector}']", text)


def _select_element(page, selector: str, value: str):
    """Select an option in a dropdown."""
    selector = _normalize_selector(selector)

    locator = page.get_by_label(selector)
    if locator.count() > 0:
        locator.first.select_option(label=value)
        return

    locator = page.get_by_role("combobox", name=selector)
    if locator.count() > 0:
        locator.first.select_option(label=value)
        return

    page.select_option(f"[aria-label='{selector}']", label=value)


# =============================================================================
# Agent Loop
# =============================================================================

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

    Args:
        page: Playwright page object (already navigated to the benchmark page).
        client: LLM client (OpenAI-compatible or Gemini).
        model: Model name.
        provider: LLM provider.
        instruction: Task instruction from the manifest.
        max_steps: Maximum number of agent steps.
        timeout_seconds: Hard timeout in seconds.
        verbose: Print step-by-step actions.
        temperature: LLM sampling temperature.

    Returns:
        Dict with trajectory, steps taken, and completion status.
    """
    start_time = time.time()
    trajectory = []
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Task: {instruction}\n\nThe page has loaded. Here is the current accessibility tree:\n\n{get_accessibility_tree(page)}"},
    ]

    for step in range(max_steps):
        elapsed = time.time() - start_time
        if elapsed > timeout_seconds:
            if verbose:
                print(f"    Step {step + 1}: TIMEOUT ({elapsed:.0f}s)")
            break

        # Get action from LLM
        raw_response = llm_complete(
            client,
            model,
            messages,
            temperature=temperature,
            provider=provider,
            reasoning_effort=reasoning_effort,
        )
        action = _parse_action(raw_response)
        thought = action.get("thought", "")

        if verbose:
            action_type = action.get("action", "?")
            selector = action.get("selector", "")
            print(f"    Step {step + 1}: {action_type}", end="")
            if selector:
                print(f" ({selector[:40]})", end="")
            print()
            if thought:
                print(f"      Thought: {thought[:80]}{'...' if len(thought) > 80 else ''}")

        # Execute action
        status = execute_action(page, action)
        trajectory.append({
            "step": step + 1,
            "thought": thought,
            "action": {k: v for k, v in action.items() if k != "thought"},
            "status": status,
            "elapsed_seconds": round(time.time() - start_time, 1),
        })

        if status == "FINISH":
            if verbose:
                print(f"    Agent declared task complete at step {step + 1}")
            break

        # Wait for page to settle after action
        page.wait_for_timeout(500)

        # Get updated accessibility tree
        new_tree = get_accessibility_tree(page)
        messages.append({"role": "assistant", "content": raw_response})
        messages.append({"role": "user", "content": f"Action result: {status}\n\nUpdated accessibility tree:\n\n{new_tree}"})

    return {
        "steps": len(trajectory),
        "trajectory": trajectory,
        "elapsed_seconds": round(time.time() - start_time, 1),
        "completed": any(t["status"] == "FINISH" for t in trajectory),
    }


# =============================================================================
# Main Evaluation Loop
# =============================================================================

def run_evaluation(
    model: str,
    provider: str = "vllm",
    base_url: str = "http://localhost:8000/v1",
    api_key: str = "dummy",
    pages_filter: list[str] | None = None,
    max_steps: int = 30,
    timeout_per_page: int = 180,
    headless: bool = True,
    verbose: bool = True,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    server_host: str = "127.0.0.1",
    server_port: int = 8080,
    output_path: str = "results.json",
) -> list[dict]:
    """
    Run the full WebAgentBench evaluation with an LLM agent.

    Args:
        model: Model name (e.g., "meta-llama/Llama-3.1-8B-Instruct").
        provider: LLM provider ("vllm", "openai", "gemini").
        base_url: API base URL for the LLM.
        api_key: API key.
        pages_filter: Optional list of page_ids to evaluate.
        max_steps: Max agent steps per page.
        timeout_per_page: Timeout per page in seconds.
        headless: Run browser in headless mode.
        verbose: Print progress.
        temperature: LLM sampling temperature (None = provider default).
        reasoning_effort: Reasoning effort for OpenAI models (low/medium/high/xhigh).
        server_host: WebAgentBench server host.
        server_port: WebAgentBench server port.
        output_path: Path to write results JSON.

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

    # Start WebAgentBench server
    bench_url = f"http://{server_host}:{server_port}"
    if verbose:
        print(f"Starting WebAgentBench server on {bench_url}...")
    server_proc = start_server(server_host, server_port)

    try:
        if not wait_for_server(server_host, server_port):
            print("ERROR: WebAgentBench server failed to start", file=sys.stderr)
            server_proc.terminate()
            sys.exit(1)
        if verbose:
            print(f"Server ready at {bench_url}")

        # Load manifest
        manifest = get_manifest(bench_url)
        pages = manifest["pages"]
        if pages_filter:
            pages = [p for p in pages if p["page_id"] in pages_filter]

        if not pages:
            print("No pages to evaluate.", file=sys.stderr)
            return []

        if verbose:
            print(f"\nAgent: {model} (via {provider})")
            print(f"Pages: {len(pages)}")
            print(f"Max steps per page: {max_steps}")
            print(f"Timeout per page: {timeout_per_page}s")
            print(f"{'='*60}\n")

        results = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)

            for page_def in pages:
                page_id = page_def["page_id"]
                instruction = page_def["instruction"]
                benchmark_state = {}

                if verbose:
                    print(f"[{page_id}] {page_def['title']}")
                    print(f"  Instruction: {instruction[:80]}...")

                # Create a fresh browser context per page (isolated cookies/state)
                context = browser.new_context()
                page = context.new_page()

                try:
                    page.goto(f"{bench_url}/pages/{page_id}")
                    page.wait_for_load_state("networkidle")

                    # Run agent loop
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

                    # Capture benchmark state
                    benchmark_state = page.evaluate(
                        "() => JSON.parse(JSON.stringify(window.__benchmarkState || {}))"
                    )
                    dom_checks = page_def.get("success_criteria", {}).get("dom_check", [])
                    if dom_checks:
                        benchmark_state["dom_checks"] = _capture_dom_checks(page, dom_checks)

                    # Evaluate via server
                    evaluation = evaluate_state(bench_url, page_id, benchmark_state)

                except Exception as e:
                    logger.error(f"Error on page {page_id}: {e}")
                    agent_result = {"steps": 0, "trajectory": [], "elapsed_seconds": 0, "completed": False}
                    evaluation = {"score": -1.0, "success": False, "reasoning": f"Error: {e}"}

                finally:
                    context.close()

                result = {
                    "page_id": page_id,
                    "title": page_def["title"],
                    "primitives": page_def["primary_primitives"],
                    "difficulty": page_def["difficulty"],
                    "benchmark_state": benchmark_state,
                    "evaluation": evaluation,
                    "agent": {
                        "model": model,
                        "provider": provider,
                        "steps": agent_result["steps"],
                        "elapsed_seconds": agent_result["elapsed_seconds"],
                        "completed": agent_result["completed"],
                        "trajectory": agent_result["trajectory"],
                    },
                }
                results.append(result)

                # Print inline result
                if verbose:
                    icon = "PASS" if evaluation.get("success") else "FAIL"
                    score = evaluation.get("score", -1.0)
                    print(f"  [{icon}] score={score:+.1f} ({agent_result['steps']} steps, {agent_result['elapsed_seconds']:.0f}s)")
                    print(f"  {evaluation.get('reasoning', '')}")
                    print()

            browser.close()

        # Write results
        _write_agent_results(results, model, provider, output_path)
        if verbose:
            print_summary(results)

        return results

    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except Exception:
            server_proc.kill()
            server_proc.wait()


def _write_agent_results(results: list[dict], model: str, provider: str, output_path: str):
    """Write agent evaluation results to a JSON file."""
    total = len(results)
    passed = sum(1 for r in results if r["evaluation"].get("success"))
    avg_score = sum(r["evaluation"].get("score", -1.0) for r in results) / total if total else 0

    prim_scores: dict[str, list[float]] = {}
    for r in results:
        for prim in r.get("primitives", []):
            prim_scores.setdefault(prim, []).append(r["evaluation"].get("score", -1.0))

    output = {
        "benchmark": "WebAgentBench",
        "version": "1.3.0",
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

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults written to {output_path}")


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
                        help="Specific page_ids to evaluate (default: all)")
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
    parser.add_argument("--output", type=str, default="results.json",
                        help="Output file (default: results.json)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Less output")

    args = parser.parse_args()

    # Resolve provider-specific defaults
    if args.api_base_url is None:
        if args.provider == "vllm":
            args.api_base_url = "http://localhost:8000/v1"
        elif args.provider == "openai":
            args.api_base_url = "https://api.openai.com/v1"

    if args.api_key is None:
        if args.provider == "vllm":
            args.api_key = "dummy"
        elif args.provider == "openai":
            import os
            args.api_key = os.environ.get("OPENAI_API_KEY", "")
            if not args.api_key:
                print("ERROR: Set OPENAI_API_KEY or pass --api-key", file=sys.stderr)
                sys.exit(1)
        elif args.provider == "gemini":
            import os
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
        max_steps=args.max_steps,
        timeout_per_page=args.timeout,
        headless=args.headless,
        verbose=not args.quiet,
        temperature=args.temperature,
        reasoning_effort=args.reasoning_effort,
        server_host=args.server_host,
        server_port=args.server_port,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
