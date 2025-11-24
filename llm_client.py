import json
import os
import time
from typing import Any, Dict, List, Optional
import re

_API_LOG_PATH: Optional[str] = os.getenv("LLM_API_LOG_PATH")
_API_CALL_SEQ: int = 0


def configure_api_logger(path: Optional[str]) -> None:
    """Configure a shared JSONL log file for all LLM API calls."""
    global _API_LOG_PATH
    _API_LOG_PATH = path


def _sanitize_context(ctx: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(ctx, dict):
        return {}
    allowed: Dict[str, Any] = {}
    for key, value in ctx.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            allowed[key] = value
    return allowed


def _append_api_log(entry: Dict[str, Any]) -> None:
    path = _API_LOG_PATH or os.getenv("LLM_API_LOG_PATH")
    if not path:
        return
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(entry) + "\n")
    except Exception:
        # Logging issues should never block primary execution.
        pass


def _next_api_sequence() -> int:
    global _API_CALL_SEQ
    _API_CALL_SEQ += 1
    return _API_CALL_SEQ


class LLMClient:
    """Thin wrapper around an LLM provider (OpenAI-compatible) for JSON outputs.

    - Uses environment variables:
      - OPENAI_API_KEY
      - OPENAI_BASE_URL (optional)
      - LLM_MODEL (default: gpt-5)
    - Supports JSON-only responses with retry on malformed JSON.
    - No network calls occur unless methods are invoked.
    """

    def __init__(self, model: Optional[str] = None, temperature: float = 0.0, seed: Optional[int] = None, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.model = model or os.getenv("LLM_MODEL", "gpt-5")
        self.temperature = float(temperature)
        self.seed = seed
        self._client = None
        self._last_io: Optional[Dict[str, Any]] = None
        self._base_url = base_url
        self._api_key = api_key

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        api_key = self._api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set; cannot use LLM client.")
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("openai package not installed. Run 'pip install openai'.") from e
        base_url = self._base_url or os.getenv("OPENAI_BASE_URL")
        if base_url:
            self._client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = OpenAI(api_key=api_key)
        return self._client

    def complete_json(self, system_prompt: str, user_json: Dict[str, Any], max_retries: int = 1, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get a JSON object from the model using chat.completions with json_object formatting."""
        context = context or {}
        client = self._ensure_client()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_json, separators=(",", ":"))},
        ]
        response_format: Dict[str, Any] = {"type": "json_object"}
        last_err = None
        temp_supported = True  # assume temperature is supported until server proves otherwise

        attempt_count = 0
        raw_response_text: Optional[str] = None
        parsed_response: Optional[Dict[str, Any]] = None
        error_info: Optional[Dict[str, Any]] = None
        call_started = time.time()
        call_started_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        last_used_temperature: Optional[float] = None

        def _call_with_tracking(with_temp: bool):
            nonlocal attempt_count, last_used_temperature
            resp, used = _call(with_temp=with_temp)
            attempt_count += 1
            last_used_temperature = used.get("temperature")
            return resp, used

        def _call(with_temp: bool):
            params: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "response_format": response_format,
            }
            if with_temp and self.temperature is not None:
                params["temperature"] = self.temperature
            if self.seed is not None:
                params["seed"] = self.seed
            return client.chat.completions.create(**params), params

        try:
            # Exactly (max_retries + 1) attempts total, with a same-iteration fallback if temperature is unsupported
            for attempt in range(max_retries + 1):
                try:
                    resp, used_params = _call_with_tracking(with_temp=(self.temperature is not None and temp_supported))
                except Exception as e:
                    estr = str(e).lower()
                    last_err = e
                    # Fallback: some models reject explicit temperature; retry once without it in the same attempt
                    if temp_supported and ("unsupported" in estr and "temperature" in estr):
                        temp_supported = False
                        try:
                            resp, used_params = _call_with_tracking(with_temp=False)
                        except Exception as e2:
                            last_err = e2
                            raise
                    else:
                        raise
                message_obj = resp.choices[0].message
                txt_raw = message_obj.content or ""
                tool_calls = getattr(message_obj, "tool_calls", None)
                if not txt_raw:
                    # Many providers (including OpenRouter/Qwen) return JSON via tool/function calls
                    if tool_calls and isinstance(tool_calls, (list, tuple)):
                        for tc in tool_calls:
                            try:
                                fn = getattr(tc, "function", None)
                                args = getattr(fn, "arguments", None) if fn is not None else None
                                if not args and isinstance(tc, dict):
                                    args = ((tc.get("function") or {}).get("arguments"))
                                if isinstance(args, str) and args.strip():
                                    txt_raw = args
                                    break
                            except Exception:
                                continue
                    if (not txt_raw) and hasattr(message_obj, "function_call"):
                        fn_call = getattr(message_obj, "function_call", None)
                        args = getattr(fn_call, "arguments", None) if fn_call is not None else None
                        if not args and isinstance(fn_call, dict):
                            args = fn_call.get("arguments")
                        if isinstance(args, str) and args.strip():
                            txt_raw = args
                raw_response_text = txt_raw
                # Record last raw IO for debugging
                self._last_io = {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "model": self.model,
                    "temperature": self.temperature,
                    "used_temperature": (used_params.get("temperature", None) if isinstance(used_params, dict) else last_used_temperature),
                    "seed": self.seed,
                    "system_prompt": system_prompt,
                    "user_json": user_json,
                    "response_text": txt_raw,
                }
                try:
                    # Try primary content first
                    if not txt_raw or txt_raw.strip() == "":
                        raise ValueError("empty content from model")
                    parsed = json.loads(txt_raw)
                    if isinstance(parsed, dict) and not parsed:
                        raise ValueError("empty JSON object from model")
                    parsed_response = parsed
                    return parsed
                except Exception as e:
                    last_err = e
                    # Tolerant JSON extraction for models that prepend thoughts/markdown
                    try:
                        extracted = self._extract_json_object(txt_raw)
                        if extracted is not None:
                            out = json.loads(extracted)
                            if isinstance(out, dict):
                                # Note extraction for debugging
                                if isinstance(self._last_io, dict):
                                    self._last_io["extracted_json"] = extracted[:5000]
                                parsed_response = out
                                return out
                    except Exception as _e2:
                        last_err = _e2
                    # Some providers return function/tool calls with JSON args instead of content
                    try:
                        choice0 = getattr(resp, "choices", [None])[0]
                        message = getattr(choice0, "message", None)
                        tool_calls = getattr(message, "tool_calls", None) if message is not None else None
                        function_call = getattr(message, "function_call", None) if message is not None else None
                        # Prefer tool_calls
                        if tool_calls and isinstance(tool_calls, (list, tuple)):
                            for tc in tool_calls:
                                fn = getattr(tc, "function", None)
                                args = None
                                if fn is not None:
                                    args = getattr(fn, "arguments", None)
                                if not args and isinstance(tc, dict):
                                    args = ((tc.get("function") or {}).get("arguments"))
                                if isinstance(args, str) and args.strip():
                                    out = json.loads(args)
                                    if isinstance(out, dict):
                                        if isinstance(self._last_io, dict):
                                            self._last_io["extracted_from_tool_call"] = args[:5000]
                                        parsed_response = out
                                        return out
                        # Legacy function_call
                        if function_call:
                            args = getattr(function_call, "arguments", None)
                            if not args and isinstance(function_call, dict):
                                args = function_call.get("arguments")
                            if isinstance(args, str) and args.strip():
                                out = json.loads(args)
                                if isinstance(out, dict):
                                    if isinstance(self._last_io, dict):
                                        self._last_io["extracted_from_function_call"] = args[:5000]
                                    parsed_response = out
                                    return out
                    except Exception as _e3:
                        last_err = _e3
                    # Ask the model to reformat strictly as JSON — only if more retries remain
                    if attempt < max_retries:
                        messages.append({
                            "role": "system",
                            "content": "Return strictly valid JSON object only. Output a single JSON object with no extra text, no markdown, no <think> tags.",
                        })
                        continue
                    break
            if last_err:
                raise last_err
            parsed_response = {}
            return {}
        except Exception as exc:
            error_info = {"type": exc.__class__.__name__, "message": str(exc)}
            raise
        finally:
            duration_ms = int((time.time() - call_started) * 1000)
            clean_ctx = _sanitize_context(context)
            call_id = _next_api_sequence()
            iteration_value = clean_ctx.get("iteration")
            if iteration_value is None:
                iteration_value = call_id
            extra_context = {k: v for k, v in clean_ctx.items() if k not in {"role", "iteration", "phase"}}
            log_entry = {
                "t_start": call_started_iso,
                "duration_ms": duration_ms,
                "call_id": call_id,
                "model": self.model,
                "temperature": self.temperature,
                "used_temperature": last_used_temperature,
                "seed": self.seed,
                "role": clean_ctx.get("role"),
                "phase": clean_ctx.get("phase"),
                "iteration": iteration_value,
                "context": extra_context or None,
                "attempts": attempt_count,
                "status": "ok" if error_info is None else "error",
                "input": {
                    "system_prompt": system_prompt,
                    "user_json": user_json,
                },
                "output": parsed_response,
                "raw_response_excerpt": (raw_response_text or "")[:2000],
            }
            if error_info is not None:
                log_entry["error"] = error_info
            _append_api_log(log_entry)

    def _extract_json_object(self, text: str) -> Optional[str]:
        """Best-effort extraction of a single JSON object from free-form text.

        Heuristics:
        - Prefer fenced blocks ```json { ... } ``` or ``` { ... } ```
        - Otherwise, scan for the first balanced {...} object considering quotes/escapes
        - As a fallback, scan for the last balanced object
        Returns the substring of the JSON object if found, else None.
        """
        # 1) Code fences with json
        try:
            m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
            if m:
                return m.group(1)
            m = re.search(r"```\s*(\{[\s\S]*?\})\s*```", text)
            if m:
                return m.group(1)
        except Exception:
            pass

        def _scan_from(s: str, start: int) -> Optional[str]:
            depth = 0
            in_str = False
            esc = False
            first = -1
            for i in range(start, len(s)):
                ch = s[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                else:
                    if ch == '"':
                        in_str = True
                        continue
                    if ch == '{':
                        if depth == 0:
                            first = i
                        depth += 1
                        continue
                    if ch == '}':
                        if depth > 0:
                            depth -= 1
                            if depth == 0 and first != -1:
                                return s[first:i + 1]
            return None

        # 2) First balanced brace object
        try:
            first_brace = text.find('{')
            if first_brace != -1:
                got = _scan_from(text, first_brace)
                if got:
                    return got
        except Exception:
            pass

        # 3) Last balanced brace object
        try:
            last_brace = text.rfind('{')
            if last_brace != -1:
                got = _scan_from(text, last_brace)
                if got:
                    return got
        except Exception:
            pass
        return None
