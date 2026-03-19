"""
Prepare training data from LLMOS episodes and WebAgentBench results.

Exports conversations in the JSONL format expected by tinker-cookbook:
  {"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, ...]}

Usage:
    # From LLMOS episodes only
    python training/prepare_data.py --llmos-dir llmos/runs/ --output training/data/train.jsonl

    # With quality filters (recommended)
    python training/prepare_data.py \
        --llmos-dir llmos/runs/ \
        --min-score 1.0 \
        --min-steps 3 \
        --test-split 10 \
        --output training/data/sft_train.jsonl

    # Template-aware filtering (per-primitive min steps from PRIMITIVE_CONFIG)
    python training/prepare_data.py \
        --llmos-dir llmos/runs/ \
        --min-score 1.0 \
        --use-template-min-steps \
        --require-all-criteria \
        --output training/data/sft_train.jsonl

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
import re
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.trajectory import export_conversations, batch_export


def _primitive_from_filename(filename: str) -> str | None:
    """Extract primitive name from episode filename like 'episode_*_collect_{primitive}_{n}.json'."""
    m = re.search(r'collect_(.+?)_\d+\.json$', filename)
    return m.group(1) if m else None


def _page_from_episode(episode: dict) -> str | None:
    """Extract page name from the first observation's tree text."""
    history = episode.get("history", [])
    if not history:
        return None
    tree = history[0].get("agent_llm_data", {}).get("tree_text", "")
    if not tree:
        return None
    # Match [1] main "Page Name" or first heading/text
    m = re.search(r'main "(.+?)"', tree)
    if m:
        return m.group(1)
    m = re.search(r'\[1\] \w+ "(.+?)"', tree)
    if m:
        return m.group(1)
    return None


def _all_criteria_met(episode: dict) -> bool:
    """Check if judge's criteria_check has all criteria met."""
    judge_result = episode.get("judge_result", {})
    criteria_check = judge_result.get("criteria_check", [])
    if not criteria_check:
        return True  # No criteria to check -- pass through
    return all(c.get("met", False) for c in criteria_check)


def load_llmos_episodes(
    runs_dir: str,
    exclude_primitives: set[str] | None = None,
    min_steps: int = 0,
) -> tuple[list[dict], dict]:
    """
    Load all LLMOS episode JSON files from a directory.

    Returns (episodes, filter_stats) where filter_stats tracks rejection reasons.
    """
    episodes = []
    stats = {"total": 0, "no_history": 0, "excluded_prim": 0, "too_short": 0, "kept": 0}

    for f in sorted(Path(runs_dir).glob("*.json")):
        with open(f) as fh:
            try:
                ep = json.load(fh)
            except json.JSONDecodeError:
                continue

        # Skip non-episode files (e.g. index.json)
        if "history" not in ep:
            stats["no_history"] += 1
            continue
        stats["total"] += 1

        # Primitive exclusion
        if exclude_primitives:
            prim = _primitive_from_filename(f.name)
            if prim and prim in exclude_primitives:
                stats["excluded_prim"] += 1
                continue

        # Minimum step count filter
        ep_steps = ep.get("steps", len(ep.get("history", [])))
        if ep_steps < min_steps:
            stats["too_short"] += 1
            continue

        # Store filename for diagnostics
        ep["_filename"] = f.name
        episodes.append(ep)
        stats["kept"] += 1

    return episodes, stats


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
    parser.add_argument("--min-steps", type=int, default=0,
                        help="Minimum episode step count (filters trivially short episodes)")
    parser.add_argument("--test-split", type=int, default=0,
                        help="Number of conversations to hold out for test set (written to _test.jsonl)")
    parser.add_argument("--no-split", action="store_true",
                        help="Don't split multi-turn conversations into sub-conversations")
    parser.add_argument("--exclude-primitives", nargs="+", default=None,
                        help="Primitives to exclude (e.g. verification reflection adversarial_robustness)")
    parser.add_argument("--require-all-criteria", action="store_true",
                        help="Only keep episodes where all judge criteria are met")
    parser.add_argument("--use-template-min-steps", action="store_true",
                        help="Apply per-template minimum step counts from PRIMITIVE_CONFIG")
    args = parser.parse_args()

    if not args.llmos_dir and not args.wab_results:
        parser.error("At least one of --llmos-dir or --wab-results required")

    all_convos = []

    # Load LLMOS episodes
    exclude_set = set(args.exclude_primitives) if args.exclude_primitives else None

    if args.llmos_dir:
        episodes, stats = load_llmos_episodes(
            args.llmos_dir,
            exclude_primitives=exclude_set,
            min_steps=args.min_steps,
        )
        if stats["excluded_prim"]:
            print(f"Excluded {stats['excluded_prim']} episodes from primitives: "
                  f"{', '.join(sorted(exclude_set))}")
        if stats["too_short"]:
            print(f"Filtered {stats['too_short']} episodes with < {args.min_steps} steps")

        # --- New filters (applied before batch_export) ---

        # Filter by judge criteria
        if args.require_all_criteria:
            before = len(episodes)
            episodes = [ep for ep in episodes if _all_criteria_met(ep)]
            print(f"Criteria filter: {before} -> {len(episodes)} episodes")

        # Filter by per-template minimum step counts
        if args.use_template_min_steps:
            from llmos.collect import PRIMITIVE_CONFIG
            before = len(episodes)
            filtered = []
            for ep in episodes:
                prim = _primitive_from_filename(ep.get("_filename", ""))
                if prim and prim in PRIMITIVE_CONFIG:
                    min_s = PRIMITIVE_CONFIG[prim].get("min_steps", 0)
                    if ep.get("steps", len(ep.get("history", []))) >= min_s:
                        filtered.append(ep)
                else:
                    filtered.append(ep)  # No config -- pass through
            episodes = filtered
            print(f"Template min-steps filter: {before} -> {len(episodes)} episodes")

        convos = batch_export(
            episodes, source="llmos", fmt="messages",
            min_score=args.min_score, only_success=args.only_success,
        )

        # Report per-page breakdown
        score_filtered = len(episodes) - len(convos)
        print(f"LLMOS: {stats['total']} total -> {len(episodes)} after step filter "
              f"-> {len(convos)} after score filter")
        if convos:
            _print_page_breakdown(episodes, convos, args.min_score)

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
        print(f"WAB: {len(results)} results -> {len(convos)} conversations")
        all_convos.extend(convos)

    if not all_convos:
        print("No conversations to export. Check filters and data sources.")
        sys.exit(1)

    # Split multi-turn conversations into sub-conversations (one per assistant turn)
    # Required for LAST_ASSISTANT_MESSAGE training mode -- ensures every turn gets trained on
    if not args.no_split:
        split_convos = []
        for c in all_convos:
            msgs = c["messages"]
            # Find all assistant message indices
            asst_indices = [i for i, m in enumerate(msgs) if m["role"] == "assistant"]
            for idx in asst_indices:
                # Sub-conversation: everything up to and including this assistant turn
                split_convos.append({"messages": msgs[:idx + 1]})
        print(f"Split: {len(all_convos)} conversations -> {len(split_convos)} sub-conversations "
              f"(one per assistant turn)")
        all_convos = split_convos

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
    print(f"\nTrain: {len(all_convos)} conversations -> {output}")

    if test_convos:
        test_path = output.with_name(output.stem + "_test" + output.suffix)
        with open(test_path, "w") as f:
            for c in test_convos:
                f.write(json.dumps(strip_meta(c)) + "\n")
        print(f"Test:  {len(test_convos)} conversations -> {test_path}")

    # Print stats
    total_msgs = sum(len(c["messages"]) for c in all_convos)
    total_chars = sum(sum(len(m["content"]) for m in c["messages"]) for c in all_convos)
    print(f"\nStats: {total_msgs} messages, ~{total_chars // 4} tokens (estimated)")


def _print_page_breakdown(episodes: list[dict], convos: list[dict], min_score: float | None):
    """Print per-page episode counts, score distribution, and average steps."""
    page_stats: dict[str, dict] = {}
    for ep in episodes:
        page = _page_from_episode(ep) or "unknown"
        if page not in page_stats:
            page_stats[page] = {"total": 0, "passed": 0, "scores": [], "steps": []}
        page_stats[page]["total"] += 1
        score = ep.get("score", 0)
        page_stats[page]["scores"].append(score)
        page_stats[page]["steps"].append(ep.get("steps", len(ep.get("history", []))))
        if min_score is None or score >= min_score:
            page_stats[page]["passed"] += 1

    print(f"  {'Page':<28} {'Total':>5} {'Passed':>6} {'Avg Score':>9} {'Avg Steps':>9}")
    for page in sorted(page_stats.keys()):
        s = page_stats[page]
        avg = sum(s["scores"]) / len(s["scores"]) if s["scores"] else 0
        avg_steps = sum(s["steps"]) / len(s["steps"]) if s["steps"] else 0
        print(f"  {page:<28} {s['total']:>5} {s['passed']:>6} {avg:>+9.2f} {avg_steps:>9.1f}")


if __name__ == "__main__":
    main()
