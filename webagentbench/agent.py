"""LLM agent for BrowserGym environments.

Receives BrowserGym observation dicts, outputs BrowserGym action strings
(Python function calls like ``click('a51')``, ``fill('b22', 'hello')``).

Compatible with any BrowserGym environment (WebArena, WorkArena, WebAgentBench).

Usage:
    from webagentbench.agent import LLMAgent
    from webagentbench.browsergym_env import make_env

    env = make_env("gmail_board_briefing_prep")
    agent = LLMAgent(model="gpt-4o", provider="openai")

    obs, info = env.reset()
    agent.reset(obs)
    while True:
        action = agent.act(obs)
        obs, reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            break
    env.close()
"""

from __future__ import annotations

import ast
import copy
import json
import logging
import os
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

MAX_INPUT_TOKENS = 26_000

_STRING_ARG_POSITIONS: dict[str, set[int]] = {
    "click": {0},
    "fill": {0, 1},
    "select_option": {0, 1},
    "hover": {0},
    "press": {0, 1},
    "dblclick": {0},
    "drag_and_drop": {0, 1},
    "clear": {0},
    "focus": {0},
    "send_msg_to_user": {0},
    "report_infeasible": {0},
    "upload_file": {0, 1},
}


# =============================================================================
# System prompt for BrowserGym action format
# =============================================================================

SYSTEM_PROMPT = """\
You are a web agent. You interact with web pages to complete tasks.

## Observation
Each step you receive an accessibility tree (AXTree) of the current page. Elements are marked with string IDs called `bid`:
- `[bid] role "name"` — interactive or meaningful elements
- Indentation shows nesting
- Attributes: value="...", checked, unchecked, disabled, focused, selected
- `[OVERLAY]` marks dialogs blocking the page — handle these first

## Actions
Respond with a single Python function call. Available actions:

click('a51')                      — Click element
fill('b22', 'hello world')        — Fill text field
select_option('c3', 'California') — Select dropdown option
hover('d7')                       — Hover over element
press('48', 'Enter')              — Press key (e.g. 'Enter', 'Backspace')
scroll(0, 300)                    — Scroll (pixels, positive=down/right)
dblclick('12')                    — Double-click element
drag_and_drop('a1', 'b2')         — Drag and drop
clear('b22')                      — Clear text field
focus('b22')                      — Focus element
send_msg_to_user('done')          — Report your answer/completion
report_infeasible('reason')       — Report task is impossible
noop(1000)                        — Wait (default 1000ms)

## Rules
1. Output EXACTLY ONE function call per step. No extra text, no markdown.
2. Use bid values from the CURRENT observation only. Never reuse old bids.
3. Any action argument that refers to a bid must be a quoted string, e.g. click('75'), not click(75).
4. Handle overlays/dialogs before interacting with background elements.
5. Before calling send_msg_to_user, verify the task is actually complete.
6. If the task asks for a specific answer, pass it to send_msg_to_user.
"""


# =============================================================================
# LLM Client
# =============================================================================

def create_client(provider: str, base_url: str | None = None, api_key: str | None = None):
    if provider == "gemini":
        from google import genai
        return genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY", ""))
    else:
        from openai import OpenAI
        if base_url is None:
            if provider == "vllm":
                base_url = os.environ.get("WEBAGENTBENCH_API_BASE_URL", "http://localhost:8000/v1")
            else:
                base_url = os.environ.get("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
        if api_key is None:
            if provider == "vllm":
                api_key = os.environ.get("WEBAGENTBENCH_API_KEY", "dummy")
            else:
                api_key = os.environ.get("OPENAI_API_KEY", "")
        return OpenAI(base_url=base_url, api_key=api_key)


def llm_complete(
    client, model: str, messages: list[dict],
    temperature: float | None = None, provider: str = "openai",
    reasoning_effort: str | None = None,
) -> tuple[str, str]:
    """Return (content, reasoning) from the LLM."""
    if provider == "gemini":
        return _complete_gemini(client, model, messages, temperature)
    return _complete_openai(client, model, messages, temperature, reasoning_effort)


def _complete_openai(client, model, messages, temperature, reasoning_effort):
    kwargs: dict[str, Any] = {"model": model, "messages": messages}
    if temperature is not None:
        if not (model.startswith("gpt-5") and temperature != 1):
            kwargs["temperature"] = temperature
    max_tok = 4096
    if model.startswith("gpt-5"):
        kwargs["max_completion_tokens"] = max_tok
    else:
        kwargs["max_tokens"] = max_tok
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort
    if model.lower().startswith("qwen3"):
        kwargs["extra_body"] = {"enable_thinking": False}
    for attempt in range(5):
        try:
            response = client.chat.completions.create(**kwargs)
            msg = response.choices[0].message
            reasoning = getattr(msg, "reasoning_content", None) or ""
            return msg.content or "", reasoning
        except Exception as e:
            if "429" in str(e) and attempt < 4:
                time.sleep(2 ** attempt + 1)
                continue
            raise


def _complete_gemini(client, model, messages, temperature):
    from google.genai import types
    system_instruction = None
    contents = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            system_instruction = content
        else:
            contents.append(types.Content(
                role="user" if role != "assistant" else "model",
                parts=[types.Part(text=content)],
            ))
    config_kwargs: dict[str, Any] = {"system_instruction": system_instruction}
    if temperature is not None:
        config_kwargs["temperature"] = temperature
    response = client.models.generate_content(
        model=model, contents=contents,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    return response.text or "", ""


# =============================================================================
# Observation formatting
# =============================================================================

def format_obs_for_llm(obs: dict) -> str:
    """Convert BrowserGym observation dict to a text prompt for the LLM."""
    from browsergym.utils.obs import flatten_axtree_to_str

    parts = []

    # Goal (task instruction)
    goal = obs.get("goal", "")
    if goal:
        parts.append(f"Task: {goal}")

    # Last action result
    last_action = obs.get("last_action", "")
    last_error = obs.get("last_action_error", "")
    if last_action:
        parts.append(f"Last action: {last_action}")
    if last_error:
        parts.append(f"Last action error: {last_error}")

    # URL
    url = obs.get("url", "")
    if url:
        parts.append(f"URL: {url}")

    # AXTree (primary observation) — use BrowserGym's formatter
    axtree = obs.get("axtree_object")
    if axtree:
        axtree_txt = flatten_axtree_to_str(
            axtree,
            extra_properties=obs.get("extra_element_properties", {}),
            with_clickable=True,
            with_visible=True,
            filter_visible_only=True,
            filter_with_bid_only=True,
        )
        if axtree_txt:
            # Strip control characters that can corrupt JSON serialization
            axtree_txt = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', axtree_txt)
            parts.append(f"\nAccessibility tree:\n{axtree_txt}")

    return "\n".join(parts)


# =============================================================================
# Context window management
# =============================================================================

def _estimate_tokens(text: str) -> int:
    return int(len(text) / 2.5)


def _compact_content(content: str, target_chars: int) -> str:
    if len(content) <= target_chars:
        return content
    # Keep first and last sections
    half = target_chars // 2
    return content[:half] + "\n[... content truncated ...]\n" + content[-half:]


def _build_fallback_summary(messages: list[dict]) -> str:
    """Extract verifiable facts from dropped conversation turns."""
    route = ""
    outcomes: list[str] = []
    selections: list[str] = []
    field_values: list[str] = []

    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        m = re.match(r"Last action:\s*(.+)", content, re.MULTILINE)
        if m:
            outcome = m.group(1).strip()
            outcomes.append(outcome)
        for line in content.split("\n"):
            line = line.strip()
            tm = re.match(r"\[\w+\]\s+(.+)", line)
            if not tm:
                continue
            node_text = tm.group(1)
            if node_text.startswith("main ") or node_text.startswith("heading "):
                route = node_text
            if "selected" in node_text:
                selections.append(node_text)
            if "value=" in node_text:
                field_values.append(node_text)

    parts = []
    if route:
        parts.append(f"Latest route/view: {route}")
    if outcomes:
        parts.append(f"Recent verified outcomes: {outcomes[-1]}")
    if selections:
        parts.append(f"Current selection state: {selections[-1]}")
    if field_values:
        parts.append(f"Current field values: {field_values[-1]}")
    return "\n".join(parts)


def trim_messages(
    messages: list[dict],
    max_input_tokens: int = MAX_INPUT_TOKENS,
    client=None,
    model: str = "",
    provider: str = "openai",
) -> list[dict]:
    target_chars = int(max_input_tokens * 2.0)
    result = []
    for msg in messages:
        if msg.get("role") == "user" and len(msg.get("content", "")) > target_chars:
            msg = copy.copy(msg)
            msg["content"] = _compact_content(msg["content"], target_chars)
        result.append(msg)
    messages = result

    total = sum(_estimate_tokens(m.get("content", "")) for m in messages)
    if total <= max_input_tokens or len(messages) <= 3:
        return messages

    head = messages[:2]
    head_tokens = sum(_estimate_tokens(m.get("content", "")) for m in head)
    budget = max_input_tokens - head_tokens - 200

    tail: list[dict] = []
    tail_tokens = 0
    for msg in reversed(messages[2:]):
        msg_tokens = _estimate_tokens(msg.get("content", ""))
        if tail_tokens + msg_tokens > budget:
            break
        tail.insert(0, msg)
        tail_tokens += msg_tokens

    if len(tail) == len(messages) - 2:
        return messages

    dropped = messages[2: len(messages) - len(tail)]

    if client is not None and len(dropped) >= 4:
        turns = []
        for msg in dropped:
            if msg.get("role") == "assistant":
                turns.append(f"Agent: {msg['content'][:300]}")
            elif msg.get("role") == "user":
                line = msg["content"].split("\n")[0][:200]
                turns.append(f"Obs: {line}")
        try:
            summary, _ = llm_complete(
                client, model,
                [{"role": "user", "content":
                    "Summarize this agent history into brief bullet points. "
                    "Focus on actions taken and progress made. Under 200 words.\n\n"
                    + "\n".join(turns)
                }],
                temperature=0.0, provider=provider,
            )
            marker_text = (
                f"[Summary of steps 1-{len(dropped) // 2}]\n{summary.strip()}\n"
                "[End of summary. Continue from current observation below.]"
            )
        except Exception:
            marker_text = f"[Compressed factual state from {len(dropped)} earlier steps]\n{_build_fallback_summary(dropped)}"
    else:
        marker_text = f"[Compressed factual state from {len(dropped)} earlier steps]\n{_build_fallback_summary(dropped)}"

    return head + [{"role": "user", "content": marker_text}] + tail


# =============================================================================
# Agent
# =============================================================================

class LLMAgent:
    """LLM agent for BrowserGym environments.

    Receives BrowserGym observation dicts, outputs BrowserGym action strings.
    """

    def __init__(
        self,
        model: str,
        provider: str = "openai",
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
        max_input_tokens: int = MAX_INPUT_TOKENS,
        system_prompt: str = SYSTEM_PROMPT,
    ):
        self.model = model
        self.provider = provider
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.max_input_tokens = max_input_tokens
        self.system_prompt = system_prompt
        self.client = create_client(provider, base_url, api_key)
        self.messages: list[dict] = []
        self._has_initial_obs = False
        self._last_raw_response = ""
        self._last_thought = ""

    def reset(self, obs: dict | None = None) -> None:
        """Clear history for a new episode. Optionally process first obs."""
        self.messages = [{"role": "system", "content": self.system_prompt}]
        self._has_initial_obs = False
        if obs is not None:
            content = format_obs_for_llm(obs) if isinstance(obs, dict) else str(obs)
            self.messages.append({"role": "user", "content": content})
            self._has_initial_obs = True

    def act(self, obs: dict | str) -> str:
        """Given a BrowserGym observation, return an action string.

        Args:
            obs: BrowserGym observation dict (or text string for backward compat).

        Returns:
            Action string like ``click('a51')`` or ``fill('b22', 'hello')``.
        """
        # Skip appending if this is the same observation already added by reset()
        if self._has_initial_obs:
            self._has_initial_obs = False
        else:
            content = format_obs_for_llm(obs) if isinstance(obs, dict) else str(obs)
            self.messages.append({"role": "user", "content": content})

        trimmed = trim_messages(
            self.messages,
            max_input_tokens=self.max_input_tokens,
            client=self.client,
            model=self.model,
            provider=self.provider,
        )

        try:
            response, reasoning = llm_complete(
                self.client, self.model, trimmed,
                temperature=self.temperature,
                provider=self.provider,
                reasoning_effort=self.reasoning_effort,
            )
        except Exception as e:
            if "input length" in str(e) or "context_length" in str(e):
                logger.warning("Context overflow, compacting...")
                trimmed = trim_messages(
                    self.messages,
                    max_input_tokens=self.max_input_tokens - 4000,
                    client=self.client,
                    model=self.model,
                    provider=self.provider,
                )
                response, reasoning = llm_complete(
                    self.client, self.model, trimmed,
                    temperature=self.temperature,
                    provider=self.provider,
                    reasoning_effort=self.reasoning_effort,
                )
            else:
                raise

        # Clean response — extract the action call
        action = _extract_action(response)
        self._last_raw_response = response
        self._last_thought = reasoning
        if not self._last_thought and response != action:
            # For non-reasoning models, extract thought from text before the action
            # Use the raw response for find() since _extract_action may normalize quotes
            action_start = re.search(re.escape(action[:20]), response)
            if action_start and action_start.start() > 0:
                self._last_thought = response[:action_start.start()].strip()
            self._last_thought = re.sub(r"<think>.*?</think>", "", self._last_thought, flags=re.DOTALL).strip()

        self.messages.append({"role": "assistant", "content": action})
        return action

    @property
    def conversation(self) -> list[dict]:
        return list(self.messages)


def _extract_action(raw: str) -> str:
    """Extract a BrowserGym action from raw LLM output.

    Strips thinking tags, markdown fences, and extra text.
    Returns the first function call found.
    """
    # Strip <think>...</think>
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    if "<think>" in cleaned:
        cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL).strip()

    # Strip markdown fences
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    # Try to find a function call pattern: name(args) with balanced parens
    name_match = re.search(
        r'(click|fill|select_option|hover|press|scroll|dblclick|drag_and_drop|'
        r'clear|focus|send_msg_to_user|report_infeasible|noop|'
        r'go_back|go_forward|goto|new_tab|tab_close|tab_focus|upload_file)'
        r'\s*\(',
        cleaned,
    )
    if name_match:
        start = name_match.start()
        paren_start = name_match.end() - 1  # position of '('
        depth = 1
        i = paren_start + 1
        in_string = None
        while i < len(cleaned) and depth > 0:
            ch = cleaned[i]
            if in_string:
                if ch == '\\':
                    i += 1  # skip escaped char
                elif ch == in_string:
                    in_string = None
            else:
                if ch in ('"', "'"):
                    in_string = ch
                elif ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
            i += 1
        if depth == 0:
            return _normalize_action_call(cleaned[start:i])

    # Fallback: return the cleaned text (BrowserGym will try to parse it)
    return cleaned.strip() or 'noop()'


def _normalize_action_call(action: str) -> str:
    """Canonicalize simple function-call actions and quote string args when needed."""
    try:
        expr = ast.parse(action.strip(), mode="eval").body
    except SyntaxError:
        return action.strip()

    if not isinstance(expr, ast.Call) or not isinstance(expr.func, ast.Name):
        return action.strip()
    if expr.keywords:
        return action.strip()

    func_name = expr.func.id
    args: list[Any] = []
    for index, node in enumerate(expr.args):
        try:
            value = _literal_from_ast(node)
        except ValueError:
            return action.strip()
        if index in _STRING_ARG_POSITIONS.get(func_name, set()) and not isinstance(value, str):
            value = str(value)
        args.append(value)

    rendered_args = ", ".join(_python_literal(value) for value in args)
    return f"{func_name}({rendered_args})"


def _literal_from_ast(node: ast.AST) -> Any:
    """Return the literal value represented by a simple AST node."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.operand, ast.Constant):
        operand = node.operand.value
        if isinstance(operand, (int, float)) and not isinstance(operand, bool):
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return operand
    raise ValueError("non-literal action argument")


def _python_literal(value: Any) -> str:
    """Serialize a simple Python literal for BrowserGym actions."""
    if isinstance(value, str):
        return json.dumps(value)
    if value is True:
        return "True"
    if value is False:
        return "False"
    if value is None:
        return "None"
    return repr(value)
