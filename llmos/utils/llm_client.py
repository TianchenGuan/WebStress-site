"""
Unified LLM Client for LLMOS.
Supports OpenAI and Gemini with automatic JSON mode and retry logic.
"""

import asyncio
import concurrent.futures
import json
import random
import re
import time
import logging
from typing import Optional, Union
from pathlib import Path

logger = logging.getLogger(__name__)


def _exponential_backoff_with_jitter(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter_factor: float = 0.5,
) -> float:
    """
    Calculate delay with exponential backoff and jitter to avoid thundering herd.

    Args:
        attempt: Current attempt number (0-indexed).
        base_delay: Base delay in seconds.
        max_delay: Maximum delay cap.
        jitter_factor: Random jitter as fraction of delay (0.5 = ±50%).

    Returns:
        Delay in seconds with jitter applied.
    """
    # Exponential backoff: base * 2^attempt
    delay = min(base_delay * (2 ** attempt), max_delay)
    # Add random jitter: delay * (1 ± jitter_factor * random)
    jitter = delay * jitter_factor * (2 * random.random() - 1)
    return max(0, delay + jitter)


def _strip_thinking_tags(text: str) -> str:
    """Strip <think>...</think> tags (Qwen3 pattern) from response."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _strip_markdown_code_fences(text: str) -> str:
    """Strip markdown code fences from response."""
    text = text.strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if not lines:
        return ""

    # Drop leading ``` or ```json
    lines = lines[1:]
    # Drop trailing ```
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


class LLMClient:
    """Unified wrapper for LLM providers (OpenAI, Gemini, vLLM)."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the LLM client.

        Args:
            config_path: Path to config.json. If None, looks in default location.
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.json"
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(
                f"LLMOS config.json not found at {config_path}. "
                "Create it (see llmos/config.json) or pass the correct path."
            )

        with open(config_path, "r") as f:
            self.config = json.load(f)

        self.llm_config = self.config.get("llm", {})
        self.default_provider = self.llm_config.get("default_provider", "openai")

        # Lazy-load clients
        self._openai_client = None
        self._gemini_model = None
        self._vllm_client = None

    def _get_openai_client(self):
        """Get or create OpenAI client."""
        if self._openai_client is None:
            from openai import OpenAI

            openai_config = self.llm_config.get("openai", {})
            api_key = openai_config.get("api_key")
            base_url = openai_config.get("base_url")

            if not api_key:
                raise ValueError("OpenAI API key not configured in config.json")

            kwargs = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url

            self._openai_client = OpenAI(**kwargs)

        return self._openai_client

    def _get_gemini_client(self):
        """Get or create Gemini client using new google.genai package."""
        if self._gemini_model is None:
            from google import genai

            gemini_config = self.llm_config.get("gemini", {})
            api_key = gemini_config.get("api_key")

            if not api_key:
                raise ValueError("Gemini API key not configured in config.json")

            self._gemini_model = genai.Client(api_key=api_key)

        return self._gemini_model

    def _get_vllm_client(self):
        """Get or create vLLM client (OpenAI-compatible)."""
        if self._vllm_client is None:
            from openai import OpenAI

            vllm_config = self.llm_config.get("vllm", {})
            base_url = vllm_config.get("base_url", "http://localhost:8000/v1")
            api_key = vllm_config.get("api_key", "dummy")

            self._vllm_client = OpenAI(base_url=base_url, api_key=api_key)

        return self._vllm_client

    def complete(
        self,
        messages: list[dict],
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
        json_mode: bool = True,
        max_retries: int = 3,
        temperature: float = 0.7,
    ) -> Union[dict, str]:
        """
        Send a completion request to the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model_name: Model name to use. If None, uses provider default.
            provider: LLM provider ('openai' or 'gemini'). If None, uses default.
            json_mode: If True, request JSON output and parse response.
            max_retries: Number of retries for JSON parsing failures.
            temperature: Sampling temperature.

        Returns:
            Parsed JSON dict if json_mode=True, else raw string.
        """
        provider = provider or self.default_provider

        for attempt in range(max_retries):
            try:
                if provider == "openai":
                    response = self._complete_openai(
                        messages, model_name, json_mode, temperature
                    )
                elif provider == "gemini":
                    response = self._complete_gemini(
                        messages, model_name, json_mode, temperature
                    )
                elif provider == "vllm":
                    response = self._complete_vllm(
                        messages, model_name, json_mode, temperature
                    )
                else:
                    raise ValueError(f"Unknown provider: {provider}")

                if json_mode:
                    # Try to parse JSON
                    return self._parse_json(response)
                else:
                    return response

            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise
                delay = _exponential_backoff_with_jitter(attempt, base_delay=0.5)
                logger.debug(f"Retrying after {delay:.2f}s due to JSON parse error")
                time.sleep(delay)
            except Exception as e:
                logger.error(f"LLM completion error: {e}")
                if attempt == max_retries - 1:
                    raise
                delay = _exponential_backoff_with_jitter(attempt, base_delay=1.0)
                logger.debug(f"Retrying after {delay:.2f}s due to error: {e}")
                time.sleep(delay)

        # Should be unreachable (loop always returns or raises), but be explicit
        raise RuntimeError("LLM completion failed: exhausted all retries without returning")

    async def complete_async(
        self,
        messages: list[dict],
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
        json_mode: bool = True,
        max_retries: int = 3,
        temperature: float = 0.7,
    ) -> Union[dict, str]:
        """
        Async version of complete() that runs in a thread pool.

        This allows the LLM client to be used in async contexts without blocking
        the event loop. The underlying API calls are still synchronous but are
        offloaded to a thread pool executor.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model_name: Model name to use. If None, uses provider default.
            provider: LLM provider ('openai' or 'gemini'). If None, uses default.
            json_mode: If True, request JSON output and parse response.
            max_retries: Number of retries for JSON parsing failures.
            temperature: Sampling temperature.

        Returns:
            Parsed JSON dict if json_mode=True, else raw string.
        """
        loop = asyncio.get_event_loop()
        # Run the synchronous complete() in a thread pool to avoid blocking
        return await loop.run_in_executor(
            None,  # Use default executor
            lambda: self.complete(
                messages=messages,
                model_name=model_name,
                provider=provider,
                json_mode=json_mode,
                max_retries=max_retries,
                temperature=temperature,
            )
        )

    def _complete_openai(
        self,
        messages: list[dict],
        model_name: Optional[str],
        json_mode: bool,
        temperature: float,
    ) -> str:
        """Complete using OpenAI API."""
        client = self._get_openai_client()
        openai_config = self.llm_config.get("openai", {})
        model = model_name or openai_config.get("default_model", "gpt-4o")

        # Models that don't support custom temperature (only default=1)
        # Includes o1/o4 series and gpt-5-mini reasoning models
        no_temperature_models = ["o1", "o1-mini", "o1-preview", "o4-mini", "gpt-5-mini"]
        supports_temperature = not any(
            model.startswith(m) or m in model for m in no_temperature_models
        )

        # Models that don't support system messages - convert to user messages
        no_system_models = ["o4-mini"]
        needs_system_conversion = any(
            model.startswith(m) or m in model for m in no_system_models
        )

        if needs_system_conversion:
            messages = self._convert_system_to_user_messages(messages)

        kwargs = {
            "model": model,
            "messages": messages,
        }

        if supports_temperature:
            kwargs["temperature"] = temperature

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def _convert_system_to_user_messages(self, messages: list[dict]) -> list[dict]:
        """Convert system messages to user messages for models that don't support them."""
        converted = []
        for msg in messages:
            if msg.get("role") == "system":
                # Convert system message to user message with clear prefix
                converted.append({
                    "role": "user",
                    "content": f"[System Instructions]\n{msg.get('content', '')}"
                })
            else:
                converted.append(msg)
        return converted

    def _complete_gemini(
        self,
        messages: list[dict],
        model_name: Optional[str],
        json_mode: bool,
        temperature: float,
    ) -> str:
        """Complete using Gemini API (new google.genai package)."""
        from google import genai
        from google.genai import types

        client = self._get_gemini_client()
        gemini_config = self.llm_config.get("gemini", {})
        model = model_name or gemini_config.get("default_model", "gemini-2.0-flash")

        # Convert messages to Gemini format
        gemini_messages = self._convert_to_gemini_format(messages)

        # Extract system instruction and chat messages
        system_instruction = None
        contents = []

        for msg in gemini_messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            else:
                contents.append(
                    types.Content(
                        role="user" if msg["role"] == "user" else "model",
                        parts=[types.Part(text=msg["content"])]
                    )
                )

        # Build generation config
        config_kwargs = {"temperature": temperature}
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"

        generation_config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            **config_kwargs
        )

        # Generate response
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generation_config
        )

        return response.text

    def _convert_to_gemini_format(self, messages: list[dict]) -> list[dict]:
        """Convert OpenAI-style messages to Gemini format."""
        converted = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Gemini uses 'model' instead of 'assistant'
            if role == "assistant":
                role = "model"

            converted.append({"role": role, "content": content})

        return converted

    def _complete_vllm(
        self,
        messages: list[dict],
        model_name: Optional[str],
        json_mode: bool,
        temperature: float,
    ) -> str:
        """Complete using a vLLM OpenAI-compatible endpoint."""
        client = self._get_vllm_client()
        vllm_config = self.llm_config.get("vllm", {})
        model = model_name or vllm_config.get("default_model", "Qwen/Qwen3-8B")

        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        # Only request JSON mode if explicitly enabled in config (default: off)
        if json_mode and vllm_config.get("json_mode", False):
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def _parse_json(self, response: str) -> dict:
        """
        Parse JSON from LLM response with best-effort fallback.

        Handles:
        - Raw JSON objects/arrays
        - Markdown fenced code blocks (```json ... ```)
        - <think>...</think> wrapped JSON (Qwen3 pattern)
        - JSON embedded in surrounding prose text
        """
        candidate = _strip_thinking_tags(response)
        candidate = _strip_markdown_code_fences(candidate)

        if not candidate:
            raise json.JSONDecodeError("Empty response after stripping", response, 0)

        # Fast path: direct parse
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        # Fallback: scan for first JSON object or array
        decoder = json.JSONDecoder()
        for start in range(len(candidate)):
            if candidate[start] not in "{[":
                continue
            try:
                value, _end = decoder.raw_decode(candidate[start:])
                return value
            except json.JSONDecodeError:
                continue

        raise json.JSONDecodeError(
            "No valid JSON found in response", response, 0
        )


# Convenience function for quick usage
def create_client(config_path: Optional[str] = None) -> LLMClient:
    """Create an LLM client with the given config."""
    return LLMClient(config_path)
