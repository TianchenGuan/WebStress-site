"""
Prepare training data from LLMOS episodes and WebAgentBench results.

Exports conversations in the JSONL format expected by tinker-cookbook:
  {"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, ...]}

Usage:
    # From LLMOS episodes only
    python training/prepare_data.py --llmos-dir llmos/runs/ --output training/data/train.jsonl

    # From WebAgentBench results (requires re-run with updated agent_eval.py)
    python training/prepare_data.py --wab-results results/webagentbench/qwen3.5-27b-v5-final.json

    # Both sources, filter to score >= 0
    python training/prepare_data.py \
        --llmos-dir llmos/runs/ \
        --wab-results results/webagentbench/results.json \
        --min-score 0.0 \
        --output training/data/train.jsonl

    # Only successful episodes
    python training/prepare_data.py --llmos-dir llmos/runs/ --only-success
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.trajectory import export_conversations, batch_export


def load_llmos_episodes(runs_dir: str) -> list[dict]:
    """Load all LLMOS episode JSON files from a directory."""
    episodes = []
    for f in sorted(Path(runs_dir).glob("*.json")):
        with open(f) as fh:
            ep = json.load(fh)
        # Skip if no history (e.g. index files)
        if "history" not in ep:
            continue
        episodes.append(ep)
    return episodes


def load_wab_results(results_path: str) -> list[dict]:
    """Load WebAgentBench results."""
    with open(results_path) as f:
        data = json.load(f)
    return data.get("results", [])


def main():
    parser = argparse.ArgumentParser(description="Prepare training data for tinker SFT")
    parser.add_argument("--llmos-dir", type=str, help="Directory with LLMOS episode JSONs")
    parser.add_argument("--wab-results", type=str, help="WebAgentBench results JSON")
    parser.add_argument("--output", "-o", type=str, default="training/data/train.jsonl")
    parser.add_argument("--min-score", type=float, default=None, help="Minimum score filter")
    parser.add_argument("--only-success", action="store_true", help="Only include successful episodes")
    parser.add_argument("--test-split", type=int, default=0,
                        help="Number of conversations to hold out for test set (written to _test.jsonl)")
    args = parser.parse_args()

    if not args.llmos_dir and not args.wab_results:
        parser.error("At least one of --llmos-dir or --wab-results required")

    all_convos = []

    # Load LLMOS episodes
    if args.llmos_dir:
        episodes = load_llmos_episodes(args.llmos_dir)
        convos = batch_export(
            episodes, source="llmos", fmt="messages",
            min_score=args.min_score, only_success=args.only_success,
        )
        print(f"LLMOS: {len(episodes)} episodes → {len(convos)} conversations")
        all_convos.extend(convos)

    # Load WAB results
    if args.wab_results:
        results = load_wab_results(args.wab_results)
        convos = batch_export(
            results, source="wab", fmt="messages",
            min_score=args.min_score, only_success=args.only_success,
        )
        # Warn about lost observations
        for c in convos:
            msgs = c.get("messages", [])
            lost = sum(1 for m in msgs if "not recorded" in m.get("content", ""))
            if lost > 0:
                tid = c.get("metadata", {}).get("task_id", "?")
                print(f"  WARNING: {tid} has {lost} messages with lost observations (re-run WAB to fix)")
        print(f"WAB: {len(results)} results → {len(convos)} conversations")
        all_convos.extend(convos)

    if not all_convos:
        print("No conversations to export. Check filters and data sources.")
        sys.exit(1)

    # Split test set
    test_convos = []
    if args.test_split > 0 and len(all_convos) > args.test_split:
        test_convos = all_convos[:args.test_split]
        all_convos = all_convos[args.test_split:]

    # Write output
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Strip metadata for tinker (it only wants {"messages": [...]})
    def strip_meta(convo):
        return {"messages": convo["messages"]}

    with open(output, "w") as f:
        for c in all_convos:
            f.write(json.dumps(strip_meta(c)) + "\n")
    print(f"\nTrain: {len(all_convos)} conversations → {output}")

    if test_convos:
        test_path = output.with_name(output.stem + "_test" + output.suffix)
        with open(test_path, "w") as f:
            for c in test_convos:
                f.write(json.dumps(strip_meta(c)) + "\n")
        print(f"Test:  {len(test_convos)} conversations → {test_path}")

    # Print stats
    total_msgs = sum(len(c["messages"]) for c in all_convos)
    total_chars = sum(sum(len(m["content"]) for m in c["messages"]) for c in all_convos)
    print(f"\nStats: {total_msgs} messages, ~{total_chars // 4} tokens (estimated)")


if __name__ == "__main__":
    main()
