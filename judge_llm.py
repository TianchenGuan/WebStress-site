import os
from typing import Any, Dict, Optional

from llm_client import LLMClient
from validation import validate_judge_output


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


class LLMJudge:
    def __init__(self, model: Optional[str] = None, temperature: float = 0.0, seed: Optional[int] = None):
        self.client = LLMClient(model=model, temperature=temperature, seed=seed)
        self.system = _read(os.path.join(PROMPTS_DIR, "judge.system.txt"))

    def evaluate(self, instruction: Dict[str, Any], start_state_summary: Dict[str, Any], end_state_summary: Dict[str, Any], episode_log: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "instruction": instruction,
            "start_state_summary": start_state_summary,
            "end_state_summary": end_state_summary,
            "episode_log": episode_log,
        }
        self._last_call = {"payload": payload}
        out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
        validate_judge_output(out)
        self._last_call.update({"output": out, "raw": getattr(self.client, "_last_io", None)})
        return out

