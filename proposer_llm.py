import os
from typing import Any, Dict, List, Optional

from llm_client import LLMClient
from validation import validate_instruction


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


class LLMProposer:
    def __init__(self, model: Optional[str] = None, temperature: float = 0.7, seed: Optional[int] = None):
        self.client = LLMClient(model=model, temperature=temperature, seed=seed)
        self.system = _read(os.path.join(PROMPTS_DIR, "proposer.system.txt"))

    def propose_next(self, agent_id: str, recent_episodes: List[Dict[str, Any]], global_task_pool: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        payload = {"agent_id": agent_id, "recent_episodes": recent_episodes, "global_task_pool": global_task_pool or []}
        self._last_call = {"payload": payload}
        out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
        validate_instruction(out)
        self._last_call.update({"output": out, "raw": getattr(self.client, "_last_io", None)})
        return out


class InstructionCompiler:
    """Compile freeform instruction text into Instruction JSON using an LLM."""

    def __init__(self, model: Optional[str] = None, temperature: float = 0.2, seed: Optional[int] = None):
        self.client = LLMClient(model=model, temperature=temperature, seed=seed)
        self.system = _read(os.path.join(PROMPTS_DIR, "compiler.system.txt"))

    def compile(self, instruction_text: str) -> Dict[str, Any]:
        payload = {"task": instruction_text, "environment": "desktop"}
        self._last_call = {"payload": payload}
        out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
        validate_instruction(out)
        self._last_call.update({"output": out, "raw": getattr(self.client, "_last_io", None)})
        return out

