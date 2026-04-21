"""Stock browser-use harness for WebAgentBench.

Uses upstream `browser_use.Agent` without customization — stock system prompt,
vision, thinking (AgentBrain), and action registry minus a few dangerous or
irrelevant actions. This complements the custom WAB harness
(`browseruse_eval.py`) and gives paper-grade comparability: the two harnesses
evaluate the same task set with different agent loops, so readers can separate
"model ability" from "harness choice".

Banned actions (via Controller(exclude_actions=...)):
  - navigate, search, switch, close   — URL/tab tricks the benchmark forbids
  - evaluate                          — arbitrary JS (would read server state)
  - read_file, write_file, replace_file, upload_file  — filesystem escape
  - save_as_pdf                       — irrelevant

Defense in depth: Browser(allowed_domains=["127.0.0.1","localhost"]) blocks any
cross-origin attempts at the browser level.

CLI:
    python -m webagentbench.stock_browseruse_eval \\
        --model gemini-3-flash-preview --provider gemini \\
        --tasks booking_cancel_upcoming booking_budget_comparison \\
        --output results/webagentbench/stock_bu.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).parent

# Load GEMINI_API_KEY / OPENAI_API_KEY / etc. from webagentbench/.env.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(BASE_DIR / ".env", override=False)
except Exception:
    pass

# Stock browser-use exposes ~25 actions. We remove the ones that would let the
# agent escape the benchmark's UI-only contract.
_BANNED_ACTIONS: list[str] = [
    "navigate",
    "search",
    "switch",
    "close",
    "evaluate",
    "read_file",
    "write_file",
    "replace_file",
    "upload_file",
    "save_as_pdf",
]

_DEFAULT_MAX_STEPS = 60
_DEFAULT_TIMEOUT = 600


# =============================================================================
# Backend communication
# =============================================================================


def _http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    body = None
    req_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, method=method, headers=req_headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _build_llm(
    provider: str,
    model: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
):
    """Return a browser-use LLM wrapper for the chosen provider.

    Supported providers:
      gemini              — Google Gemini (ChatGoogle). Env: GEMINI_API_KEY
      openai              — OpenAI chat completions. Env: OPENAI_API_KEY [+ OPENAI_API_BASE_URL]
      bedrock             — AWS Bedrock Converse API via boto3. Env: AWS_BEDROCK_API_KEY
                              (mapped to AWS_BEARER_TOKEN_BEDROCK) + AWS_BEDROCK_REGION.
                              Covers any Bedrock model (Claude / Nova / Llama / Titan...).
      anthropic_bedrock   — Claude via AnthropicBedrock SDK (same auth as bedrock).
      anthropic           — Direct Anthropic API. Env: ANTHROPIC_API_KEY
      openrouter          — OpenRouter (meta-provider). Env: OPENROUTER_API_KEY
      vllm                — Local vLLM endpoint. Env: WEBAGENTBENCH_API_BASE_URL + _API_KEY
    """
    common: dict[str, Any] = {}
    if temperature is not None:
        common["temperature"] = temperature
    if max_tokens is not None:
        common["max_tokens"] = max_tokens

    if provider == "gemini":
        from browser_use import ChatGoogle
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise ValueError("GEMINI_API_KEY not set (add to webagentbench/.env)")
        return ChatGoogle(model=model, api_key=key, **common)

    if provider == "openai":
        from browser_use.llm.openai.chat import ChatOpenAI as BUChatOpenAI
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise ValueError("OPENAI_API_KEY not set")
        base_url = os.environ.get("OPENAI_API_BASE_URL") or None
        return BUChatOpenAI(model=model, api_key=key, base_url=base_url, **common)

    if provider in ("bedrock", "anthropic_bedrock"):
        # Map WAB-style AWS_BEDROCK_API_KEY → boto3's AWS_BEARER_TOKEN_BEDROCK env var.
        key = os.environ.get("AWS_BEDROCK_API_KEY", "") or os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")
        if key:
            os.environ["AWS_BEARER_TOKEN_BEDROCK"] = key
        region = os.environ.get("AWS_BEDROCK_REGION", "us-east-1")
        # browser-use's ChatAWSBedrock hard-checks for AWS_ACCESS_KEY_ID +
        # AWS_SECRET_ACCESS_KEY and ignores AWS_BEARER_TOKEN_BEDROCK. Passing
        # an explicit boto3 Session bypasses that check — modern boto3 picks
        # up the bearer token automatically when the env var is set.
        import boto3
        sess = boto3.Session(region_name=region)
        if provider == "anthropic_bedrock":
            from browser_use.llm.aws import ChatAnthropicBedrock
            return ChatAnthropicBedrock(model=model, aws_region=region, session=sess, **common)
        from browser_use.llm.aws import ChatAWSBedrock
        return ChatAWSBedrock(model=model, aws_region=region, session=sess, **common)

    if provider == "anthropic":
        from browser_use.llm.anthropic.chat import ChatAnthropic
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return ChatAnthropic(model=model, api_key=key, **common)

    if provider == "openrouter":
        from browser_use.llm.openrouter.chat import ChatOpenRouter
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            raise ValueError("OPENROUTER_API_KEY not set")
        return ChatOpenRouter(model=model, api_key=key, **common)

    if provider == "vllm":
        from browser_use.llm.openai.chat import ChatOpenAI as BUChatOpenAI
        base_url = os.environ.get("WEBAGENTBENCH_API_BASE_URL", "http://localhost:8000/v1")
        key = os.environ.get("WEBAGENTBENCH_API_KEY", "dummy")
        return BUChatOpenAI(model=model, api_key=key, base_url=base_url, **common)

    raise ValueError(
        f"provider {provider!r} not supported. Valid: "
        "gemini, openai, bedrock, anthropic_bedrock, anthropic, openrouter, vllm."
    )


# =============================================================================
# Single-task runner
# =============================================================================


async def run_episode(
    task_id: str,
    *,
    model: str,
    provider: str = "gemini",
    server_host: str = "127.0.0.1",
    backend_port: int = 8080,
    frontend_port: int = 8084,
    max_steps: int = _DEFAULT_MAX_STEPS,
    timeout_seconds: int = _DEFAULT_TIMEOUT,
    headless: bool = True,
    verbose: bool = True,
    # --- Stock browser-use tunables ---
    temperature: float | None = None,
    max_tokens: int | None = None,
    use_vision: bool = True,
    use_thinking: bool = True,
    max_actions_per_step: int = 4,
    max_failures: int = 3,
    step_timeout: int = 120,
    extra_banned_actions: list[str] | None = None,
) -> dict:
    """Run one WebAgentBench task through the stock browser-use agent."""
    from browser_use import Agent, Browser, Controller
    from .tasks._registry import get_task as _get_task

    task_def = _get_task(task_id)
    env_id = task_def.env_id

    # 1. Create a fresh session via the backend API. The response gives us
    #    the session id + rendered instruction + start path.
    backend = f"http://{server_host}:{backend_port}"
    created = _http_json(
        f"{backend}/api/env/{env_id}/session",
        method="POST",
        payload={"task_id": task_id},
    )
    session_id = created["session_id"]
    instruction = created["instruction"]
    start_path = created.get("start_path", "/home")

    # 2. Build the launch URL the agent will land on.
    launch_url = (
        f"http://{server_host}:{frontend_port}/env/{env_id}{start_path}"
        f"?session={urllib.parse.quote(session_id)}&agent_mode=1"
    )

    if verbose:
        print(f"[{task_id}] session={session_id}")
        print(f"  URL: {launch_url}")
        print(f"  Goal: {instruction[:120]}{'...' if len(instruction) > 120 else ''}")

    # 3. Compose the task text. The harness pre-navigates the browser to the
    #    task URL before agent.run() (see step 7); `directly_open_url=False`
    #    keeps browser-use from trying to queue a banned `navigate` action.
    goal_text = (
        "You are already on the WebAgentBench booking site. Complete the "
        f"following task on the current page.\n\n"
        f"TASK:\n{instruction}\n\n"
        "RULES:\n"
        "- Interact only with elements visible on the page. Do not try to navigate "
        "to external URLs or open new tabs.\n"
        "- If an action fails or seems stuck, read the page carefully and try an "
        "alternative UI path.\n"
        "- Call done(success=true) when the task is fully complete."
    )

    # 4. Per-task temp dirs so concurrent runs don't clobber each other.
    tmp_root = Path(tempfile.mkdtemp(prefix=f"stock-bu-{task_id}-"))
    downloads_path = tmp_root / "downloads"
    user_data_dir = tmp_root / "user-data"
    traces_dir = tmp_root / "traces"
    for p in (downloads_path, user_data_dir, traces_dir):
        p.mkdir(parents=True, exist_ok=True)

    browser = Browser(
        headless=headless,
        viewport={"width": 1280, "height": 720},
        highlight_elements=False,
        allowed_domains=[server_host, "localhost"],
        user_data_dir=user_data_dir,
        downloads_path=downloads_path,
        traces_dir=traces_dir,
    )

    # 5. Restrict the action registry. This is the key integrity measure — the
    #    agent cannot call `navigate`, `evaluate`, `read_file`, etc.
    banned = list(_BANNED_ACTIONS)
    if extra_banned_actions:
        banned.extend(a for a in extra_banned_actions if a not in banned)
    controller = Controller(exclude_actions=banned)

    # 6. Stock configuration (tunable via kwargs).
    llm = _build_llm(provider, model, temperature=temperature, max_tokens=max_tokens)
    agent = Agent(
        task=goal_text,
        llm=llm,
        browser=browser,
        controller=controller,
        use_vision=use_vision,
        use_thinking=use_thinking,
        flash_mode=False,
        max_actions_per_step=max_actions_per_step,
        max_failures=max_failures,
        step_timeout=step_timeout,
        generate_gif=False,
        # Must be False — otherwise browser-use extracts the URL from the task
        # text and queues a `navigate` initial-action, which is banned.
        directly_open_url=False,
    )

    start_ts = time.time()
    completed = False
    # Pre-navigate to the task URL before handing control to the agent. The
    # Agent.run() internally starts the browser session if it isn't started,
    # so we open it explicitly here, navigate, then run.
    try:
        await browser.start()
        await browser.navigate_to(launch_url)
    except Exception as exc:
        logger.exception("Pre-navigation failed for %s: %s", task_id, exc)
        # Fall through to agent.run(); it will re-attempt startup and may
        # produce a clearer error in the resulting history.

    try:
        history = await asyncio.wait_for(
            agent.run(max_steps=max_steps),
            timeout=timeout_seconds,
        )
        completed = True
    except asyncio.TimeoutError:
        logger.error("Task %s timed out after %ds", task_id, timeout_seconds)
        history = getattr(agent, "history", None)
    except Exception as exc:
        logger.exception("Task %s raised: %s", task_id, exc)
        history = getattr(agent, "history", None)

    elapsed = round(time.time() - start_ts, 1)

    # 7. Ask the backend for the evaluation score. The endpoint is
    #    POST /api/env/<env>/evaluate with session_id in the body. Omitting
    #    task_id keeps us on the session's bound task, which require_evaluation_access
    #    permits without a controller secret.
    try:
        eval_resp = _http_json(
            f"{backend}/api/env/{env_id}/evaluate",
            method="POST",
            payload={"session_id": session_id},
        )
        score = float(eval_resp.get("score", 0.0))
        success = bool(eval_resp.get("success", False))
        reasoning = eval_resp.get("reasoning", "")
        checks = eval_resp.get("checks", [])
        negative_checks = eval_resp.get("negative_checks", [])
    except Exception as exc:
        logger.error("Evaluate endpoint failed for %s: %s", task_id, exc)
        score, success, reasoning = 0.0, False, f"evaluate failed: {exc}"
        checks, negative_checks = [], []

    # 8. Close browser. browser-use's Browser doesn't expose a public .close(),
    #    but the context manager / explicit kill handles it in practice.
    try:
        if hasattr(browser, "stop"):
            await browser.stop()
    except Exception:
        pass

    # 9. Shape the result to roughly match browseruse_eval.py's output so
    #    downstream aggregation scripts can read both.
    return {
        "task_id": task_id,
        "session_id": session_id,
        "evaluation": {
            "score": score,
            "success": success,
            "reasoning": reasoning,
            "checks": checks,
            "negative_checks": negative_checks,
        },
        "agent": {
            "model": model,
            "provider": provider,
            "harness": "stock-browser-use",
            "elapsed_seconds": elapsed,
            "completed": completed,
            "steps": len(history.model_dump()["history"]) if (history and hasattr(history, "model_dump")) else 0,
        },
    }


# =============================================================================
# Multi-task runner
# =============================================================================


async def run_evaluation(
    *,
    model: str,
    provider: str = "gemini",
    task_filter: list[str] | None = None,
    environments_filter: list[str] | None = None,
    max_steps: int = _DEFAULT_MAX_STEPS,
    timeout_per_task: int = _DEFAULT_TIMEOUT,
    headless: bool = True,
    server_host: str = "127.0.0.1",
    backend_port: int = 8080,
    frontend_port: int = 8084,
    output_path: str = "results/webagentbench/stock_bu_results.json",
    verbose: bool = True,
    # --- Stock browser-use tunables (threaded to run_episode) ---
    temperature: float | None = None,
    max_tokens: int | None = None,
    use_vision: bool = True,
    use_thinking: bool = True,
    max_actions_per_step: int = 4,
    max_failures: int = 3,
    step_timeout: int = 120,
    extra_banned_actions: list[str] | None = None,
) -> list[dict]:
    from .agent_eval import resolve_task_ids

    task_ids = resolve_task_ids(task_filter, environments_filter)
    if not task_ids:
        print("No tasks to evaluate.", file=sys.stderr)
        return []

    if verbose:
        print(f"Agent: {model} (via {provider})")
        print(f"Harness: stock browser-use")
        print(f"Tasks: {len(task_ids)}")
        print(f"Budget: steps={max_steps}, timeout={timeout_per_task}s")
        print(f"Banned actions: {', '.join(_BANNED_ACTIONS)}")
        print("=" * 60)

    results: list[dict] = []
    for tid in task_ids:
        try:
            res = await run_episode(
                tid,
                model=model,
                provider=provider,
                server_host=server_host,
                backend_port=backend_port,
                frontend_port=frontend_port,
                max_steps=max_steps,
                timeout_seconds=timeout_per_task,
                headless=headless,
                verbose=verbose,
                temperature=temperature,
                max_tokens=max_tokens,
                use_vision=use_vision,
                use_thinking=use_thinking,
                max_actions_per_step=max_actions_per_step,
                max_failures=max_failures,
                step_timeout=step_timeout,
                extra_banned_actions=extra_banned_actions,
            )
        except Exception as exc:
            logger.error("Fatal error on %s: %s", tid, exc, exc_info=True)
            res = {
                "task_id": tid,
                "evaluation": {"score": 0.0, "success": False, "reasoning": f"fatal: {exc}"},
                "agent": {"model": model, "provider": provider, "harness": "stock-browser-use", "steps": 0},
            }
        results.append(res)
        ev = res["evaluation"]
        if verbose:
            status = "PASS" if ev["success"] else "FAIL"
            print(f"  [{status}] {tid} score={ev['score']:.2f} ({res['agent'].get('elapsed_seconds', 0)}s)")

    # Write aggregated results
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump({
            "format": "stock-browser-use",
            "agent": {"model": model, "provider": provider, "harness": "stock-browser-use"},
            "banned_actions": _BANNED_ACTIONS,
            "results": results,
        }, f, indent=2)

    if verbose:
        n = len(results)
        p = sum(1 for r in results if r["evaluation"].get("success"))
        avg = sum(r["evaluation"].get("score", 0) for r in results) / max(n, 1)
        print("=" * 60)
        print(f"SUMMARY: {p}/{n} passed | avg score: {avg:.3f}")
        print(f"Results written to: {out}")

    return results


# =============================================================================
# CLI
# =============================================================================


def main():
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(
        description="WebAgentBench evaluation via stock browser-use Agent",
    )
    p.add_argument("--model", required=True, help="e.g. gemini-3-flash-preview")
    p.add_argument("--provider", default="gemini",
                   choices=["gemini", "openai", "bedrock", "anthropic_bedrock",
                            "anthropic", "openrouter", "vllm"])
    p.add_argument("--tasks", nargs="*", help="task IDs to run (default: all)")
    p.add_argument("--environments", nargs="*", help="env filter (e.g. booking)")
    p.add_argument("--max-steps", type=int, default=_DEFAULT_MAX_STEPS)
    p.add_argument("--timeout", type=int, default=_DEFAULT_TIMEOUT)
    p.add_argument("--headless", action="store_true", default=True)
    p.add_argument("--no-headless", action="store_false", dest="headless")
    p.add_argument("--server-host", default="127.0.0.1")
    p.add_argument("--backend-port", type=int, default=8080)
    p.add_argument("--frontend-port", type=int, default=8084)
    p.add_argument("--output", default="results/webagentbench/stock_bu_results.json")
    p.add_argument("--quiet", "-q", action="store_true")

    # Stock-browser-use tunables
    p.add_argument("--temperature", type=float, default=None)
    p.add_argument("--max-tokens", type=int, default=None)
    p.add_argument("--no-vision", dest="use_vision", action="store_false", default=True,
                   help="disable screenshots (DOM-only, cheaper)")
    p.add_argument("--no-thinking", dest="use_thinking", action="store_false", default=True,
                   help="disable AgentBrain planner step")
    p.add_argument("--max-actions-per-step", type=int, default=4)
    p.add_argument("--max-failures", type=int, default=3)
    p.add_argument("--step-timeout", type=int, default=120)
    p.add_argument("--ban-action", action="append", default=None,
                   metavar="NAME",
                   help="ban an additional action beyond the default list (repeatable)")

    args = p.parse_args()

    asyncio.run(run_evaluation(
        model=args.model,
        provider=args.provider,
        task_filter=args.tasks,
        environments_filter=args.environments,
        max_steps=args.max_steps,
        timeout_per_task=args.timeout,
        headless=args.headless,
        server_host=args.server_host,
        backend_port=args.backend_port,
        frontend_port=args.frontend_port,
        output_path=args.output,
        verbose=not args.quiet,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        use_vision=args.use_vision,
        use_thinking=args.use_thinking,
        max_actions_per_step=args.max_actions_per_step,
        max_failures=args.max_failures,
        step_timeout=args.step_timeout,
        extra_banned_actions=args.ban_action,
    ))


if __name__ == "__main__":
    main()
