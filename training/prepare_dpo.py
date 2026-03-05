"""
Prepare DPO (Direct Preference Optimization) training data from LLMOS episodes.

For each primitive, pairs positive episodes (score >= 0.5) with negative episodes
(score <= 0.0, steps >= 3) to create preference pairs.

Output format matches tinker-cookbook's ComparisonBuilderFromJsonl:
  {
    "comparison": {
      "prompt_conversation": [system_msg, first_user_msg],
      "completion_A": [assistant_msg, user_msg, ...],  # chosen
      "completion_B": [assistant_msg, user_msg, ...]   # rejected
    },
    "label": "A"
  }

Usage:
    python training/prepare_dpo.py --llmos-dir llmos/runs/ --output training/data/dpo_train.jsonl
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.trajectory import export_conversations


def load_llmos_episodes(runs_dir: str) -> list[dict]:
    """Load all LLMOS episode JSON files from a directory."""
    episodes = []
    for f in sorted(Path(runs_dir).glob("episode_*.json")):
        with open(f) as fh:
            ep = json.load(fh)
        if "history" not in ep:
            continue
        episodes.append(ep)
    return episodes


def build_dpo_pairs(episodes: list[dict], pos_threshold: float = 0.5,
                    neg_threshold: float = 0.0, min_steps: int = 3) -> list[dict]:
    """
    Build DPO pairs from episodes grouped by primitive.

    Each pair has a shared prompt (system + first user message) and
    completion_A (chosen) vs completion_B (rejected).
    """
    by_prim = defaultdict(list)
    for ep in episodes:
        prim = ep.get("instruction", {}).get("primitive", "unknown")
        by_prim[prim].append(ep)

    pairs = []
    for prim, eps in by_prim.items():
        positives = [e for e in eps if e.get("score", 0) >= pos_threshold and e.get("steps", 0) >= min_steps]
        negatives = [e for e in eps if e.get("score", 0) <= neg_threshold and e.get("steps", 0) >= min_steps]

        if not positives or not negatives:
            continue

        # Convert to message format
        pos_convos = []
        for ep in positives:
            convos = export_conversations(ep, source="llmos", fmt="messages")
            if convos and len(convos[0]["messages"]) >= 3:
                pos_convos.append((ep, convos[0]["messages"]))

        neg_convos = []
        for ep in negatives:
            convos = export_conversations(ep, source="llmos", fmt="messages")
            if convos and len(convos[0]["messages"]) >= 3:
                neg_convos.append((ep, convos[0]["messages"]))

        if not pos_convos or not neg_convos:
            continue

        # Pair them (cycle shorter list)
        n_pairs = max(len(pos_convos), len(neg_convos))
        for i in range(n_pairs):
            pos_ep, pos_msgs = pos_convos[i % len(pos_convos)]
            neg_ep, neg_msgs = neg_convos[i % len(neg_convos)]

            # prompt = system + first user message
            # completion = rest of messages from first assistant response onward
            prompt = pos_msgs[:2]  # [system, first_user]
            chosen = pos_msgs[2:]
            rejected = neg_msgs[2:]

            pairs.append({
                "comparison": {
                    "prompt_conversation": prompt,
                    "completion_A": chosen,
                    "completion_B": rejected,
                },
                "label": "A",
                # metadata for inspection (stripped before writing)
                "_metadata": {
                    "primitive": prim,
                    "chosen_score": pos_ep.get("score"),
                    "chosen_steps": pos_ep.get("steps"),
                    "rejected_score": neg_ep.get("score"),
                    "rejected_steps": neg_ep.get("steps"),
                },
            })

    return pairs


def main():
    parser = argparse.ArgumentParser(description="Prepare DPO training data from LLMOS episodes")
    parser.add_argument("--llmos-dir", type=str, required=True, help="Directory with LLMOS episode JSONs")
    parser.add_argument("--output", "-o", type=str, default="training/data/dpo_train.jsonl")
    parser.add_argument("--pos-threshold", type=float, default=0.5, help="Min score for positive (default: 0.5)")
    parser.add_argument("--neg-threshold", type=float, default=0.0, help="Max score for negative (default: 0.0)")
    parser.add_argument("--min-steps", type=int, default=3, help="Min steps to filter lazy episodes (default: 3)")
    parser.add_argument("--test-split", type=int, default=0,
                        help="Number of pairs to hold out for test set (written to _test.jsonl)")
    args = parser.parse_args()

    episodes = load_llmos_episodes(args.llmos_dir)
    print(f"Loaded {len(episodes)} episodes")

    pairs = build_dpo_pairs(
        episodes,
        pos_threshold=args.pos_threshold,
        neg_threshold=args.neg_threshold,
        min_steps=args.min_steps,
    )
    print(f"Generated {len(pairs)} DPO pairs")

    if not pairs:
        print("No pairs generated. Check thresholds and data.")
        sys.exit(1)

    # Per-primitive breakdown
    prim_counts = Counter(p["_metadata"]["primitive"] for p in pairs)
    for prim, count in sorted(prim_counts.items()):
        print(f"  {prim}: {count} pairs")

    # Split test set
    test_pairs = []
    train_pairs = pairs
    if args.test_split > 0 and len(pairs) > args.test_split:
        test_pairs = pairs[:args.test_split]
        train_pairs = pairs[args.test_split:]

    # Write output (strip _metadata for tinker compatibility)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    def strip_meta(pair):
        return {"comparison": pair["comparison"], "label": pair["label"]}

    with open(output, "w") as f:
        for p in train_pairs:
            f.write(json.dumps(strip_meta(p)) + "\n")
    print(f"\nTrain: {len(train_pairs)} pairs → {output}")

    if test_pairs:
        test_path = output.with_name(output.stem + "_test" + output.suffix)
        with open(test_path, "w") as f:
            for p in test_pairs:
                f.write(json.dumps(strip_meta(p)) + "\n")
        print(f"Test:  {len(test_pairs)} pairs → {test_path}")

    # Stats
    chosen_tokens = sum(sum(len(m["content"]) for m in p["comparison"]["completion_A"]) for p in pairs) // 4
    rejected_tokens = sum(sum(len(m["content"]) for m in p["comparison"]["completion_B"]) for p in pairs) // 4
    print(f"\nEstimated tokens — chosen: ~{chosen_tokens}, rejected: ~{rejected_tokens}")


if __name__ == "__main__":
    main()
