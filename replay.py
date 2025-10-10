import json
import sys
from typing import Any, Dict

try:
    from simulator_llm import PureLLMSimulator
except Exception:
    PureLLMSimulator = None  # type: ignore


def verify_episode(log: Dict[str, Any]) -> bool:
    """Verification is not supported for pure LLM simulator runs.

    Digest equality cannot be guaranteed due to model variability.
    """
    return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python replay.py path/to/episode.log.json")
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        log = json.load(f)
    ok = verify_episode(log)
    print("replay_verification:", "unsupported" if PureLLMSimulator is not None else "unavailable")


if __name__ == "__main__":
    main()
