"""
WebAgentBench Runner — server management and result utilities.

Provides helpers used by agent_eval.py for server lifecycle management,
manifest fetching, and result summarization.

Also supports standalone usage for legacy page evaluation:

Usage:
    # Start server only (for manual browser testing):
    python -m webagentbench.runner --serve-only

    # Evaluate pre-captured states from a directory:
    python -m webagentbench.runner --states-dir ./captured_states/

    # Run with Playwright (automated browser capture):
    python -m webagentbench.runner --playwright

    # Run specific pages:
    python -m webagentbench.runner --playwright --pages dark_checkout wizard_form

    # Custom output file:
    python -m webagentbench.runner --playwright --output results/webagentbench/my_results.json
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
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


def evaluate_state(base_url: str, page_id: str, benchmark_state: dict) -> dict:
    """POST benchmark state to the evaluation endpoint."""
    url = f"{base_url}/benchmark/{page_id}/evaluate"
    data = json.dumps({"benchmarkState": benchmark_state}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_with_playwright(
    base_url: str,
    page_id: str,
    timeout_seconds: int = 180,
    headless: bool = True,
) -> dict:
    """
    Open a page with Playwright, wait for completion, capture state.

    This provides the browser environment for an external agent to interact
    with. The agent should connect to the browser or the page URL.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed. Run: uv pip install playwright && playwright install chromium",
              file=sys.stderr)
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        page.goto(f"{base_url}/pages/{page_id}")
        page.wait_for_load_state("networkidle")

        # Wait for agent interaction / completion
        try:
            page.wait_for_function(
                "() => window.__benchmarkState && window.__benchmarkState.completed",
                timeout=timeout_seconds * 1000,
            )
        except Exception:
            pass  # Timeout — capture whatever state we have

        # Capture benchmark state
        state = page.evaluate("() => JSON.parse(JSON.stringify(window.__benchmarkState))")
        browser.close()

    return state


def load_states_from_dir(states_dir: Path) -> dict[str, dict]:
    """Load pre-captured benchmark states from JSON files in a directory."""
    states = {}
    for f in states_dir.glob("*.json"):
        try:
            with open(f) as fh:
                state = json.load(fh)
            page_id = state.get("pageId", f.stem)
            states[page_id] = state
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  Warning: skipping {f.name}: {e}", file=sys.stderr)
    return states


def get_manifest(base_url: str) -> dict:
    """Fetch the manifest from the running server."""
    with urllib.request.urlopen(f"{base_url}/manifest") as resp:
        return json.loads(resp.read().decode("utf-8"))


def print_result(result: dict) -> None:
    """Print a single page result."""
    evl = result["evaluation"]
    icon = "pass" if evl["success"] else "FAIL"
    score = evl["score"]
    print(f"  {icon} {result['title']:30s}  score={score:+.1f}  {evl['reasoning']}")


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


def write_results(results: list[dict], output_path: str) -> None:
    """Write results to a JSON file."""
    total = len(results)
    passed = sum(1 for r in results if r["evaluation"]["success"])
    avg_score = sum(r["evaluation"]["score"] for r in results) / total if total else 0

    # Primitive aggregation
    prim_scores: dict[str, list[float]] = {}
    for r in results:
        for prim in r.get("primitives", []):
            prim_scores.setdefault(prim, []).append(r["evaluation"]["score"])

    output = {
        "benchmark": "WebAgentBench",
        "version": "1.3.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "summary": {
            "total_pages": total,
            "passed": passed,
            "failed": total - passed,
            "average_score": round(avg_score, 3),
            "primitive_scores": {
                p: round(sum(s) / len(s), 3) for p, s in sorted(prim_scores.items())
            },
        },
    }

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults written to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="WebAgentBench Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument("--serve-only", action="store_true",
                        help="Start server and wait (for manual testing)")
    parser.add_argument("--playwright", action="store_true",
                        help="Use Playwright to open pages in a real browser")
    parser.add_argument("--headless", action="store_true", default=True,
                        help="Run Playwright in headless mode (default: True)")
    parser.add_argument("--no-headless", action="store_false", dest="headless",
                        help="Run Playwright with visible browser")
    parser.add_argument("--states-dir", type=str,
                        help="Directory of pre-captured benchmark state JSON files")
    parser.add_argument("--pages", nargs="*",
                        help="Specific page_ids to evaluate (default: all)")
    parser.add_argument("--output", type=str, default="results/webagentbench/results.json",
                        help="Output file for results (default: results/webagentbench/results.json)")
    parser.add_argument("--timeout", type=int, default=180,
                        help="Timeout per page in seconds (default: 180)")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    # 1. Start server
    print("Starting WebAgentBench server...")
    server_proc = start_server(args.host, args.port)

    try:
        if not wait_for_server(args.host, args.port):
            print("ERROR: Server failed to start", file=sys.stderr)
            server_proc.terminate()
            sys.exit(1)
        print(f"Server ready at {base_url}")

        # 2. Serve-only mode
        if args.serve_only:
            print(f"\nBrowse pages at {base_url}")
            print("Press Ctrl+C to stop.")
            try:
                server_proc.wait()
            except KeyboardInterrupt:
                pass
            return

        # 3. Load manifest
        manifest = get_manifest(base_url)
        pages = manifest["pages"]
        if args.pages:
            pages = [p for p in pages if p["page_id"] in args.pages]

        if not pages:
            print("No pages to evaluate.", file=sys.stderr)
            return

        print(f"\nEvaluating {len(pages)} pages...\n")

        # 4. Run evaluation
        results = []
        states = load_states_from_dir(Path(args.states_dir)) if args.states_dir else {}
        for page_def in pages:
            page_id = page_def["page_id"]
            print(f"[{page_id}]")

            if args.states_dir:
                if page_id not in states:
                    print(f"  ⚠️  No captured state for {page_id}, skipping")
                    continue
                benchmark_state = states[page_id]

            elif args.playwright:
                # Use Playwright to capture state
                print(f"  Opening in browser (timeout: {args.timeout}s)...")
                benchmark_state = run_with_playwright(
                    base_url, page_id,
                    timeout_seconds=args.timeout,
                    headless=args.headless,
                )

            else:
                print("  ERROR: Specify --playwright or --states-dir", file=sys.stderr)
                return

            # Evaluate
            evaluation = evaluate_state(base_url, page_id, benchmark_state)

            result = {
                "page_id": page_id,
                "title": page_def["title"],
                "primitives": page_def["primary_primitives"],
                "difficulty": page_def["difficulty"],
                "evaluation": evaluation,
            }
            results.append(result)
            print_result(result)

        # 5. Output
        write_results(results, args.output)
        print_summary(results)

    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()
            server_proc.wait()


if __name__ == "__main__":
    main()
