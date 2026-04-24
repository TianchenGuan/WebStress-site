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
        --output-dir webagentbench/results/gemini_booking
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
# Bedrock Converse: toolChoice forcing (for third-party models)
# =============================================================================
#
# browser-use's stock ChatAWSBedrock never sets Converse's `toolChoice`, so
# models like Kimi / Qwen sometimes return plain-text reasoning instead of a
# structured tool_use block once context grows — causing "Expected structured
# output but no tool use found". This subclass injects toolChoice={'any': {}}
# into the Converse body. If the model provider refuses that field (some
# vendors accept only `auto`), we fall back to the unforced path so we never
# regress below upstream behavior.


def _make_bedrock_forced_class():
    """Lazy import so users without boto3 don't pay the import cost."""
    from dataclasses import dataclass
    from browser_use.llm.aws import ChatAWSBedrock
    from browser_use.llm.aws.serializer import AWSBedrockMessageSerializer
    from browser_use.llm.exceptions import ModelProviderError, ModelRateLimitError
    from browser_use.llm.views import ChatInvokeCompletion

    @dataclass
    class ChatAWSBedrockForced(ChatAWSBedrock):
        """ChatAWSBedrock + Converse `toolChoice: {any: {}}` when output_format given.

        The `toolChoice` field tells Bedrock's Converse API the model MUST call
        one of the provided tools (vs. just "may call them"). This plugs the
        hole that lets Kimi/Qwen return plain text at long context.
        """

        async def ainvoke(self, messages, output_format=None, **kwargs):
            # Non-structured path is unchanged — no tools, no toolChoice needed.
            if output_format is None:
                return await super().ainvoke(messages, output_format=None, **kwargs)

            try:
                from botocore.exceptions import ClientError
            except ImportError as e:
                raise ImportError("boto3/botocore required for Bedrock") from e

            bedrock_messages, system_message = AWSBedrockMessageSerializer.serialize_messages(messages)
            tools = self._format_tools_for_request(output_format)

            def _build_body(force_tool: bool) -> dict:
                body: dict[str, Any] = {}
                if system_message:
                    body["system"] = system_message
                inf = self._get_inference_config()
                if inf:
                    body["inferenceConfig"] = inf
                tool_config: dict[str, Any] = {"tools": tools}
                if force_tool:
                    tool_config["toolChoice"] = {"any": {}}
                body["toolConfig"] = tool_config
                if self.request_params:
                    body.update(self.request_params)
                return {k: v for k, v in body.items() if v is not None}

            client = self._get_client()

            # First attempt: forced. Fall back to unforced on ValidationException
            # caused by toolChoice rejection (vendor doesn't support it).
            for force_tool in (True, False):
                body = _build_body(force_tool=force_tool)
                try:
                    response = client.converse(modelId=self.model, messages=bedrock_messages, **body)
                    break
                except ClientError as e:
                    err = e.response.get("Error", {})
                    code = err.get("Code", "")
                    msg = err.get("Message", str(e))
                    if code in ("ThrottlingException", "TooManyRequestsException"):
                        raise ModelRateLimitError(message=msg, model=self.name) from e
                    is_toolchoice_reject = (
                        code == "ValidationException"
                        and ("toolChoice" in msg or "tool_choice" in msg or "toolConfig" in msg)
                    )
                    if force_tool and is_toolchoice_reject:
                        logger.warning(
                            "Bedrock model %r rejected toolChoice=any; retrying without force. (%s)",
                            self.model, msg,
                        )
                        continue
                    raise ModelProviderError(message=msg, model=self.name) from e
            else:
                raise ModelProviderError(message="converse failed after fallback", model=self.name)

            usage = self._get_usage(response)
            message = response.get("output", {}).get("message", {})
            content = message.get("content", [])

            for item in content:
                if "toolUse" in item:
                    tool_input = item["toolUse"].get("input", {})
                    try:
                        return ChatInvokeCompletion(
                            completion=output_format.model_validate(tool_input),
                            usage=usage,
                        )
                    except Exception as e:
                        if isinstance(tool_input, str):
                            try:
                                data = json.loads(tool_input)
                                return ChatInvokeCompletion(
                                    completion=output_format.model_validate(data),
                                    usage=usage,
                                )
                            except json.JSONDecodeError:
                                pass
                        raise ModelProviderError(
                            message=f"Failed to validate structured output: {e}",
                            model=self.name,
                        ) from e

            raise ModelProviderError(
                message="Expected structured output but no tool use found in response",
                model=self.name,
            )

    return ChatAWSBedrockForced


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
        # Use the forced-toolChoice subclass so Kimi/Qwen can't silently
        # return plain text instead of a structured tool_use block.
        ChatAWSBedrockForced = _make_bedrock_forced_class()
        return ChatAWSBedrockForced(model=model, aws_region=region, session=sess, **common)

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
        # OpenRouter exposes many Claude / Qwen / etc. models through multiple
        # upstream providers (Anthropic direct, AWS Bedrock, Google Vertex).
        # AWS Bedrock's OpenAI-compatible structured-output endpoint rejects
        # JSON schemas with `{"type": "integer", "minimum": N}` — which
        # browser-use emits for element-index fields. Tell OpenRouter to skip
        # the Bedrock upstream so requests land on Anthropic direct / Vertex
        # where the schema is accepted. See:
        # https://openrouter.ai/docs/features/provider-routing#ignoring-providers
        ignore_env = os.environ.get("WEBAGENTBENCH_OPENROUTER_IGNORE_PROVIDERS", "Amazon Bedrock")
        ignore_list = [p.strip() for p in ignore_env.split(",") if p.strip()]
        extra_body: dict[str, Any] = {}
        if ignore_list:
            extra_body["provider"] = {"ignore": ignore_list}
        return ChatOpenRouter(
            model=model,
            api_key=key,
            extra_body=extra_body or None,
            **common,
        )

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
# Trajectory construction (ports browseruse_eval.py's format so the same
# visualize.py + demo-site replay works for both harnesses)
# =============================================================================


def _history_to_trajectory(
    history,
    *,
    include_screenshots: bool,
    screenshots_dir: "Path | None" = None,
) -> list[dict]:
    """Convert a browser_use.AgentHistoryList into the WAB trajectory format.

    Step shape matches `browseruse_eval.build_trajectory_step`'s output, so
    `webagentbench.visualize` can render trajectories from either harness.

    Screenshot handling (stock-harness-only; custom harness doesn't set this):
      - If `include_screenshots` is False: `screenshot` field is omitted.
      - If `screenshots_dir` is given and the directory exists: each step's
        PNG is written as `<screenshots_dir>/step{N:02d}.png` and the step's
        `screenshot` field is set to the relative path "screenshots/step{N:02d}.png"
        (relative to the per-task trajectory.json that will reference it).
      - If `screenshots_dir` is None: the `screenshot` field holds a base64
        data URI inline (legacy single-file fallback).
    """
    from pathlib import Path
    import base64
    from webagentbench.browseruse_eval import build_trajectory_step

    if history is None or not hasattr(history, "history"):
        return []

    screenshots: list[str | None]
    try:
        screenshots = list(history.screenshots()) if include_screenshots else []
    except Exception as exc:  # pragma: no cover — defensive against upstream breakage
        logger.warning("history.screenshots() failed: %s", exc)
        screenshots = []

    if include_screenshots and screenshots_dir is not None:
        Path(screenshots_dir).mkdir(parents=True, exist_ok=True)

    trajectory: list[dict] = []
    for i, item in enumerate(history.history):
        mo = getattr(item, "model_output", None)
        state = getattr(item, "state", None)
        if mo is None:
            continue

        thinking = (getattr(mo, "thinking", None) or "") or (
            getattr(mo, "evaluation_previous_goal", None) or ""
        )
        memory = getattr(mo, "memory", None) or ""

        actions_raw = getattr(mo, "action", None) or []
        actions = []
        for a in actions_raw:
            try:
                actions.append(a.model_dump(exclude_unset=True, exclude_none=True))
            except Exception:
                # ActionModel variants sometimes fail exclude_unset; fall back.
                actions.append(a.model_dump(exclude_none=True))

        # interacted_element is list-parallel-to-actions. Map it to a
        # {index: elem_info} dict keyed by the action's own target index so
        # build_trajectory_step's target lookup works.
        dom_elements: dict[int, dict] = {}
        interacted = getattr(state, "interacted_element", None) or []
        for act_idx, elem in enumerate(interacted):
            if elem is None:
                continue
            action_target_idx = None
            if act_idx < len(actions):
                for key in (
                    "click", "input_text", "select_option",
                    "scroll_down", "scroll_up", "scroll_left", "scroll_right",
                ):
                    if key in actions[act_idx]:
                        action_target_idx = actions[act_idx][key].get("index")
                        break
            if action_target_idx is None:
                continue
            dom_elements[action_target_idx] = {
                "tag_name": getattr(elem, "node_name", "") or "",
                "attributes": getattr(elem, "attributes", None) or {},
                "text": getattr(elem, "node_value", "") or "",
            }

        url = getattr(state, "url", "") or ""

        # Status: "success" unless any ActionResult in this step carried an error.
        status = "success"
        for r in getattr(item, "result", None) or []:
            if getattr(r, "error", None):
                status = f"ERROR: {r.error}"
                break

        metadata = getattr(item, "metadata", None)
        elapsed = 0.0
        if metadata is not None:
            elapsed = float(
                getattr(metadata, "duration_seconds", None)
                or getattr(metadata, "elapsed", None)
                or 0.0
            )

        step = build_trajectory_step(
            step_num=i + 1,
            thinking=thinking,
            memory=memory,
            actions=actions,
            dom_elements=dom_elements,
            url=url,
            status=status,
            elapsed=round(elapsed, 1),
        )
        if include_screenshots and i < len(screenshots) and screenshots[i]:
            b64 = screenshots[i]
            # Strip any incoming data: prefix to recover bare base64 bytes.
            if b64.startswith("data:"):
                b64 = b64.split(",", 1)[1]
            if screenshots_dir is not None:
                # Externalize: write PNG file, reference by relative path.
                png_path = Path(screenshots_dir) / f"step{i + 1:02d}.png"
                try:
                    png_path.write_bytes(base64.b64decode(b64))
                    step["screenshot"] = f"screenshots/{png_path.name}"
                except Exception as exc:
                    logger.warning("failed to write %s: %s", png_path, exc)
                    step["screenshot"] = f"data:image/png;base64,{b64}"
            else:
                # No dir provided → fallback inline (legacy / programmatic use).
                step["screenshot"] = f"data:image/png;base64,{b64}"
        trajectory.append(step)

    return trajectory


# =============================================================================
# Single-task runner
# =============================================================================


async def run_episode(
    task_id: str,
    *,
    model: str,
    provider: str = "gemini",
    variant_filename: str | None = None,
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
    # --- Trajectory output (on by default — same schema as browseruse_eval, plus `screenshot`) ---
    record_trajectory: bool = True,
    trajectory_screenshots: bool = True,
    # If set, PNG screenshots are written here (as step{N:02d}.png) and the
    # trajectory JSON references them by relative path; a self-contained
    # trajectory.json is also written alongside the screenshots/ directory.
    # If None, screenshots are embedded inline as base64 data URIs (legacy).
    trajectory_dir: "Path | None" = None,
) -> dict:
    """Run one WebAgentBench task through the stock browser-use agent."""
    from browser_use import Agent, Browser, Controller
    from .tasks._registry import get_task as _get_task

    task_def = _get_task(task_id)
    env_id = task_def.env_id

    # 1. Create a fresh session via the backend API. The response gives us
    #    the session id + rendered instruction + start path. Optionally apply
    #    a degradation variant by passing its filename (backend resolves it
    #    against webagentbench/injector/variants/).
    backend = f"http://{server_host}:{backend_port}"
    session_payload: dict[str, Any] = {"task_id": task_id}
    if variant_filename:
        session_payload["variant_filename"] = variant_filename
    created = _http_json(
        f"{backend}/api/env/{env_id}/session",
        method="POST",
        payload=session_payload,
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
        # Disable Chrome's sandbox. Safe here because allowed_domains already
        # confines navigation to our local WAB backend, and the renderer only
        # ever loads seeded benchmark pages. This also avoids the Ubuntu 24.04
        # regression where AppArmor's `unprivileged_userns` restriction breaks
        # Chrome's zygote → Chromium launches but the CDP port never opens →
        # browser-use times out with `BrowserStartEvent timed out after 30s`.
        # Equivalent to passing `--no-sandbox`; equivalent to setting the
        # `IN_DOCKER=true` env var that browser-use watches for.
        chromium_sandbox=False,
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

    # 9. Build trajectory in the same schema as browseruse_eval.py so
    #    webagentbench.visualize can render runs from either harness. When a
    #    `trajectory_dir` is provided, PNG screenshots are externalized to
    #    `<trajectory_dir>/screenshots/` and the step's `screenshot` field
    #    becomes a relative path ("screenshots/stepNN.png") instead of a
    #    base64 data URI. A self-contained per-task trajectory.json is also
    #    written alongside the screenshots/ directory so each task folder
    #    can be inspected or shipped independently.
    trajectory: list[dict] = []
    screenshots_dir = None
    if record_trajectory and trajectory_dir is not None:
        trajectory_dir = Path(trajectory_dir)
        trajectory_dir.mkdir(parents=True, exist_ok=True)
        if trajectory_screenshots:
            screenshots_dir = trajectory_dir / "screenshots"
    if record_trajectory:
        try:
            trajectory = _history_to_trajectory(
                history,
                include_screenshots=trajectory_screenshots,
                screenshots_dir=screenshots_dir,
            )
        except Exception as exc:
            logger.warning("trajectory build failed for %s: %s", task_id, exc)

    # 10. Shape the result to match browseruse_eval.py's output so downstream
    #     aggregation scripts, visualize.py, and replay tooling work uniformly.
    n_steps = (
        len(history.model_dump()["history"])
        if (history and hasattr(history, "model_dump"))
        else 0
    )
    agent_block: dict[str, Any] = {
        "model": model,
        "provider": provider,
        "harness": "stock-browser-use",
        "elapsed_seconds": elapsed,
        "completed": completed,
        "steps": n_steps,
    }
    if record_trajectory:
        agent_block["trajectory"] = trajectory

    result = {
        "task_id": task_id,
        "session_id": session_id,
        "evaluation": {
            "score": score,
            "success": success,
            "reasoning": reasoning,
            "checks": checks,
            "negative_checks": negative_checks,
        },
        "agent": agent_block,
    }

    # 11. Write a self-contained per-task trajectory.json when a dir was given.
    #     Summary (many-task) and run_manifest files are written by the caller
    #     (run_picks.py or the CLI runner) so this function stays per-task.
    if record_trajectory and trajectory_dir is not None:
        traj_file = trajectory_dir / "trajectory.json"
        try:
            traj_file.write_text(json.dumps(result, indent=2, default=str))
        except Exception as exc:
            logger.warning("failed to write %s: %s", traj_file, exc)

    return result


# =============================================================================
# Multi-task runner
# =============================================================================


def _task_slug(task_id: str, variant_filename: str | None = None, cond: str | None = None) -> str:
    """Return a filesystem-safe subdirectory name for a task run.

    Format:
      "<task_id>__<cond>"  when condition is known (clean / intervention)
      "<task_id>"          otherwise
    """
    if cond:
        return f"{task_id}__{cond}"
    if variant_filename:
        return f"{task_id}__intervention"
    return task_id


def _summary_entry(result: dict, trajectory_path: str | None) -> dict:
    """Strip the full trajectory from a result and add a trajectory_path pointer.

    The summary is a one-stop file for grid analysis (score, pass, elapsed,
    steps) without carrying the per-step data. Users drill into a specific
    task via `<output-dir>/<trajectory_path>`.
    """
    agent = dict(result.get("agent", {}))
    agent.pop("trajectory", None)  # full trajectory lives in per-task file
    entry = {
        "task_id": result.get("task_id"),
        "session_id": result.get("session_id"),
        "evaluation": result.get("evaluation", {}),
        "agent": agent,
    }
    if trajectory_path is not None:
        entry["trajectory_path"] = trajectory_path
    for k in ("variant_filename", "pick_metadata"):
        if k in result:
            entry[k] = result[k]
    return entry


def write_run_artifacts(
    output_dir: "str | Path",
    *,
    model: str,
    provider: str,
    results: list[dict],
    trajectory_paths: list[str | None],
    wall_seconds: float,
    started_at: str,
    ended_at: str,
    extra_manifest: dict | None = None,
) -> Path:
    """Write summary.json + run_manifest.json for a completed run.

    Each per-task trajectory.json is expected to have already been written
    by run_episode() (via its `trajectory_dir` parameter). This function
    just produces the top-level aggregation pointing at them.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    passed = sum(1 for r in results if r.get("evaluation", {}).get("success"))
    avg = sum(r.get("evaluation", {}).get("score", 0.0) for r in results) / max(1, len(results))

    summary = {
        "model": model,
        "provider": provider,
        "harness": "stock-browser-use",
        "banned_actions": _BANNED_ACTIONS,
        "n": len(results),
        "passed": passed,
        "avg_score": avg,
        "wall_seconds": wall_seconds,
        "started_at": started_at,
        "ended_at": ended_at,
        "results": [
            _summary_entry(r, tp) for r, tp in zip(results, trajectory_paths)
        ],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))

    manifest = {
        "model": model,
        "provider": provider,
        "harness": "stock-browser-use",
        "n_tasks": len(results),
        "started_at": started_at,
        "ended_at": ended_at,
        "wall_seconds": wall_seconds,
    }
    if extra_manifest:
        manifest.update(extra_manifest)
    (out / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    return out


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
    output_dir: str = "webagentbench/results/stock_bu_run",
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
    record_trajectory: bool = True,
    trajectory_screenshots: bool = True,
) -> list[dict]:
    from .agent_eval import resolve_task_ids
    from datetime import datetime, timezone

    task_ids = resolve_task_ids(task_filter, environments_filter)
    if not task_ids:
        print("No tasks to evaluate.", file=sys.stderr)
        return []

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks_dir = out_dir / "tasks"
    tasks_dir.mkdir(exist_ok=True)

    if verbose:
        print(f"Agent:    {model} (via {provider})")
        print(f"Harness:  stock browser-use")
        print(f"Tasks:    {len(task_ids)}")
        print(f"Budget:   steps={max_steps}, timeout={timeout_per_task}s")
        print(f"Banned:   {', '.join(_BANNED_ACTIONS)}")
        print(f"Writing:  {out_dir}/")
        print("=" * 60)

    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.time()

    results: list[dict] = []
    trajectory_paths: list[str | None] = []
    for tid in task_ids:
        slug = _task_slug(tid)
        task_dir = tasks_dir / slug
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
                record_trajectory=record_trajectory,
                trajectory_screenshots=trajectory_screenshots,
                trajectory_dir=task_dir if record_trajectory else None,
            )
            trajectory_paths.append(f"tasks/{slug}/trajectory.json" if record_trajectory else None)
        except Exception as exc:
            logger.error("Fatal error on %s: %s", tid, exc, exc_info=True)
            res = {
                "task_id": tid,
                "evaluation": {"score": 0.0, "success": False, "reasoning": f"fatal: {exc}"},
                "agent": {"model": model, "provider": provider, "harness": "stock-browser-use", "steps": 0},
            }
            trajectory_paths.append(None)
        results.append(res)
        ev = res["evaluation"]
        if verbose:
            status = "PASS" if ev["success"] else "FAIL"
            print(f"  [{status}] {tid} score={ev['score']:.2f} ({res['agent'].get('elapsed_seconds', 0)}s)")

    wall = time.time() - t0
    ended_at = datetime.now(timezone.utc).isoformat()

    write_run_artifacts(
        out_dir,
        model=model,
        provider=provider,
        results=results,
        trajectory_paths=trajectory_paths,
        wall_seconds=wall,
        started_at=started_at,
        ended_at=ended_at,
        extra_manifest={"task_filter": task_filter, "environments_filter": environments_filter},
    )

    if verbose:
        n = len(results)
        p = sum(1 for r in results if r["evaluation"].get("success"))
        avg = sum(r["evaluation"].get("score", 0) for r in results) / max(n, 1)
        print("=" * 60)
        print(f"SUMMARY: {p}/{n} passed | avg score: {avg:.3f}")
        print(f"Summary: {out_dir}/summary.json")

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
    p.add_argument(
        "--output-dir",
        default="webagentbench/results/stock_bu_run",
        help="Directory for run artifacts: summary.json, run_manifest.json, "
             "tasks/<task_id>/trajectory.json, tasks/<task_id>/screenshots/*.png "
             "(default: webagentbench/results/stock_bu_run)",
    )
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
    p.add_argument("--no-trajectory", dest="record_trajectory",
                   action="store_false", default=True,
                   help="don't embed the per-step trajectory in the output JSON")
    p.add_argument("--no-trajectory-screenshots",
                   dest="trajectory_screenshots",
                   action="store_false", default=True,
                   help="record the trajectory but omit base64 PNG screenshots "
                        "(trades ~10MB/task of size for no visual replay)")

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
        output_dir=args.output_dir,
        verbose=not args.quiet,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        use_vision=args.use_vision,
        use_thinking=args.use_thinking,
        max_actions_per_step=args.max_actions_per_step,
        max_failures=args.max_failures,
        step_timeout=args.step_timeout,
        extra_banned_actions=args.ban_action,
        record_trajectory=args.record_trajectory,
        trajectory_screenshots=args.trajectory_screenshots,
    ))


if __name__ == "__main__":
    main()
