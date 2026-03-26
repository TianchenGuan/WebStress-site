"""
WebAgentBench Runner — server management and result utilities.

Provides helpers used by agent_eval.py for server lifecycle management,
manifest fetching, and result summarization.
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent


def start_server(host: str, port: int) -> subprocess.Popen:
    """Start the FastAPI server in a subprocess."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "webagentbench.app:app",
         "--host", host, "--port", str(port), "--log-level", "warning"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


def wait_for_server(host: str, port: int, timeout: int = 15) -> bool:
    """Wait until the server is responding."""
    url = f"http://{host}:{port}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(url, timeout=2)
            if resp.status == 200:
                return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.3)
    return False


def get_manifest(base_url: str) -> dict:
    """Fetch the manifest from the running server."""
    with urllib.request.urlopen(f"{base_url}/manifest") as resp:
        return json.loads(resp.read().decode("utf-8"))


def print_summary(results: list[dict]) -> None:
    """Print an overall summary."""
    total = len(results)
    passed = sum(1 for r in results if r["evaluation"]["success"])
    avg_score = sum(r["evaluation"]["score"] for r in results) / total if total else 0

    print(f"\n{'='*60}")
    print(f"SUMMARY: {passed}/{total} tasks passed  |  avg score: {avg_score:+.2f}")
    print(f"{'='*60}")

    # Primitive-level aggregation
    prim_scores: dict[str, list[float]] = {}
    for r in results:
        for prim in r.get("primitives", []):
            prim_scores.setdefault(prim, []).append(r["evaluation"]["score"])

    if prim_scores:
        print("\nPrimitive Scores:")
        for prim in sorted(prim_scores):
            scores = prim_scores[prim]
            avg = sum(scores) / len(scores)
            print(f"  {prim:30s}  avg={avg:+.2f}  (n={len(scores)})")
