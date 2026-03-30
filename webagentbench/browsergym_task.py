"""BrowserGym AbstractBrowserTask implementation for WebAgentBench.

Each Gmail task is an AbstractBrowserTask that:
  1. Starts the WebAgentBench FastAPI server
  2. Creates a session with seeded state (+ optional degradation)
  3. Navigates the Playwright page to the Gmail SPA
  4. Validates by calling the server-side evaluator
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Tuple

import playwright.sync_api
from browsergym.core.task import AbstractBrowserTask

logger = logging.getLogger(__name__)

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8080


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


class WebAgentBenchTask(AbstractBrowserTask):
    """A single WebAgentBench task, compatible with BrowserGym's BrowserEnv."""

    @classmethod
    def get_task_id(cls):
        return "webagentbench"

    def __init__(
        self,
        seed: int,
        task_id: str,
        degradation: str | None = None,
        server_host: str = _DEFAULT_HOST,
        server_port: int = _DEFAULT_PORT,
    ):
        super().__init__(seed)
        self.task_id = task_id
        self.degradation = degradation
        self.server_host = server_host
        self.server_port = server_port
        self._bench_url = f"http://{server_host}:{server_port}"
        self._server_proc = None
        self._session_id: str | None = None
        self._env_id: str | None = None
        self._instruction: str = ""
        self._degradation_config = None
        self._evaluated = False
        self._initial_chat_count = 0  # track initial chat messages to avoid false termination

        # BrowserGym task properties
        self.viewport = {"width": 1280, "height": 720}
        self.slow_mo = 0
        self.timeout = 10000

        # Load degradation config if provided
        if degradation:
            from .injector.config import DegradationConfig
            deg_path = Path(degradation)
            if not deg_path.exists():
                deg_path = Path(__file__).parent / degradation
            if not deg_path.exists():
                deg_path = Path(__file__).parent / "injector" / "variants" / degradation
            if deg_path.exists():
                self._degradation_config = DegradationConfig.from_yaml(deg_path)

    def _ensure_server(self) -> None:
        from .runner import start_server, wait_for_server
        if wait_for_server(self.server_host, self.server_port, timeout=2):
            return
        self._server_proc = start_server(self.server_host, self.server_port)
        if not wait_for_server(self.server_host, self.server_port):
            raise RuntimeError("WebAgentBench server failed to start")

    def setup(self, page: playwright.sync_api.Page) -> tuple[str, dict]:
        """Start server, create session, navigate page, apply degradations."""
        self._ensure_server()
        self._evaluated = False

        # Resolve task metadata
        from .tasks._registry import get_task
        task_def = get_task(self.task_id)
        self._env_id = task_def.env_id

        # Create session
        session_payload: dict[str, Any] = {
            "task_id": self.task_id,
            "seed": self.seed if hasattr(self, 'seed') else int(self.random.randint(0, 2**31)),
        }

        # Deliver the full degradation config so the server can apply seed/server
        # injections and register network/client behavior for the live browser.
        if self._degradation_config:
            session_payload["degradation"] = {
                "variant_id": self._degradation_config.variant_id,
                "base_task_id": self._degradation_config.base_task_id,
                "target_primitive": self._degradation_config.target_primitive,
                "description": self._degradation_config.description,
                "injections": [
                    {"layer": inj.layer, "params": inj.params}
                    for inj in self._degradation_config.injections
                ],
            }

        created = _http_json(
            f"{self._bench_url}/api/env/{self._env_id}/session",
            method="POST",
            payload=session_payload,
        )
        self._session_id = created["session_id"]
        start_path = created.get("start_path", task_def.start_path or "/")
        resolved_targets = created.get("resolved_targets", {})

        from .task_rendering import render_template
        self._instruction = (
            created.get("instruction")
            or render_template(task_def.instruction_template or task_def.instruction or "", resolved_targets)
        )

        # Navigate to the Gmail SPA
        base_url = f"/env/{self._env_id}"
        session_url = (
            f"{self._bench_url}{base_url}{start_path}"
            f"?session={urllib.parse.quote(self._session_id)}&agent_mode=1"
        )
        page.goto(session_url)
        page.wait_for_load_state("networkidle")

        # BrowserGym seeds initial chat messages (greeting + goal).
        # We must ignore these when checking for agent-initiated termination.
        self._initial_chat_count = 0  # will be set after first validate() call

        info: dict[str, Any] = {
            "task_id": self.task_id,
            "session_id": self._session_id,
            "env_id": self._env_id,
            "difficulty": task_def.difficulty,
            "primitives": task_def.primary_primitives,
        }
        if self._degradation_config:
            info["degradation"] = {
                "variant_id": self._degradation_config.variant_id,
                "target_primitive": self._degradation_config.target_primitive,
            }

        return self._instruction, info

    def validate(
        self, page: playwright.sync_api.Page, chat_messages: list[str]
    ) -> Tuple[float, bool, str, dict]:
        """Check if the agent finished (via send_msg_to_user) and evaluate."""
        # On the first call, snapshot how many chat messages already exist
        # (BrowserGym adds an initial greeting + goal before any agent action).
        if self._initial_chat_count == 0 and chat_messages:
            self._initial_chat_count = len(chat_messages)

        # The agent is "done" when NEW chat messages appear beyond the initial set.
        # This happens when the agent calls send_msg_to_user() or report_infeasible().
        done = False
        new_messages = chat_messages[self._initial_chat_count:]
        for msg in new_messages:
            if msg.get("role") == "assistant" and not self._evaluated:
                done = True
                break
            if msg.get("role") == "infeasible":
                done = True
                break

        if not done:
            return 0.0, False, "", {}

        # Evaluate via server
        if not self._evaluated and self._session_id and self._env_id:
            self._evaluated = True
            try:
                try:
                    benchmark_state = page.evaluate("() => window.__benchmarkState || {}")
                except Exception:
                    benchmark_state = {}
                result = _http_json(
                    f"{self._bench_url}/api/env/{self._env_id}/evaluate",
                    method="POST",
                    payload={
                        "session_id": self._session_id,
                        "task_id": self.task_id,
                        "benchmark_state": benchmark_state,
                    },
                )
                reward = float(result.get("score", result.get("final_score", 0.0)))
                return reward, True, "", {"evaluation": result}
            except Exception as e:
                logger.error("Evaluation failed: %s", e)
                return 0.0, True, "", {"evaluation_error": str(e)}

        return 0.0, True, "", {}

    def teardown(self) -> None:
        """Destroy session and stop server if we started it."""
        if self._session_id and self._env_id:
            try:
                _http_json(
                    f"{self._bench_url}/api/env/{self._env_id}/session/{urllib.parse.quote(self._session_id)}",
                    method="DELETE",
                )
            except Exception:
                pass
            self._session_id = None

        if self._server_proc:
            self._server_proc.terminate()
            try:
                self._server_proc.wait(timeout=5)
            except Exception:
                self._server_proc.kill()
            self._server_proc = None
