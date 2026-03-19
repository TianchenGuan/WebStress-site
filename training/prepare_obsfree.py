"""
Prepare observation-free training data from multi-turn LLMOS conversations.

Converts multi-turn episodes into single-turn examples where the model sees
only ONE observation (the current one) plus a compact action history. This
avoids training the model to condition its reasoning on simulator-generated
observations, which differ from real browser observations at inference time.

Input: JSONL with multi-turn conversations (from prepare_data.py --no-split, or raw exports)
Output: JSONL with single-turn training examples (one per step, step >= 2)

Usage:
    python training/prepare_obsfree.py \
        --input training/data/raw_v6.jsonl \
        --min-score 1.0 \
        --test-split 10 \
        --output training/data/obsfree_v9_train.jsonl
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.format import SYSTEM_PROMPT, parse_action


def summarize_action(assistant_content: str) -> str:
    """Extract a compact action summary from an assistant message.

    Returns e.g. 'click [7]' or 'fill [37] "March 22"' or 'select [8] "California"'.
    """
    action = parse_action(assistant_content)
    action_type = action.get("action", "unknown")

    parts = [action_type]

    # Add ref
    ref = action.get("ref")
    if ref is not None:
        parts.append(f"[{ref}]")

    # Add from_ref/to_ref for drag_and_drop
    if action_type == "drag_and_drop":
        parts = [action_type, f"[{action.get('from_ref')}]", "→", f"[{action.get('to_ref')}]"]

    # Add value for fill/select
    value = action.get("value")
    if value is not None:
        display = value[:50] + "..." if len(value) > 50 else value
        parts.append(f'"{display}"')

    # Add key for press
    key = action.get("key")
    if key is not None:
        parts.append(f'key={key}')

    # Add direction for scroll
    direction = action.get("direction")
    if direction is not None:
        parts.append(direction)

    # Add answer for finish
    answer = action.get("answer")
    if answer is not None:
        display = answer[:50] + "..." if len(answer) > 50 else answer
        parts.append(f'"{display}"')

    return " ".join(parts)


def extract_result_line(user_content: str) -> str:
    """Extract the 'Result: ...' line from a user message (text before first \\n\\n)."""
    parts = user_content.split("\n\n", 1)
    return parts[0].strip()


def extract_observation(user_content: str) -> str:
    """Extract the observation (tree text) from a user message (text after first \\n\\n)."""
    parts = user_content.split("\n\n", 1)
    return parts[1] if len(parts) > 1 else ""


def extract_instruction(first_user_content: str) -> str:
    """Extract instruction from first user message ('Task: ...' before \\n\\n)."""
    parts = first_user_content.split("\n\n", 1)
    return parts[0].strip()


def build_action_history(steps: list[dict], window: int | None = None) -> str:
    """Build compact action history string from previous steps.

    Each step dict has 'action_summary' and 'result'.
    """
    if not steps:
        return ""

    # Apply window limit
    if window is not None and len(steps) > window:
        steps = steps[-window:]

    lines = ["Previous actions:"]
    for i, step in enumerate(steps, 1):
        result = step["result"]
        lines.append(f"  Step {i}: {step['action_summary']} → {result}")

    return "\n".join(lines)


def process_conversation(messages: list[dict], history_window: int | None = None,
                         skip_first: bool = True) -> list[dict]:
    """Convert a multi-turn conversation into single-turn observation-free examples.

    Args:
        messages: List of message dicts (system, user, assistant, user, assistant, ...)
        history_window: Max number of previous steps to include in history (None = unlimited)
        skip_first: Whether to skip step 1 (no action history)

    Returns:
        List of single-turn training examples (each is a {"messages": [...]} dict)
    """
    if len(messages) < 3:
        return []

    # Extract instruction from first user message
    instruction = extract_instruction(messages[1]["content"])

    # Parse all steps
    # Step k: user=messages[2k-1], assistant=messages[2k], k=1,2,...
    num_steps = (len(messages) - 1) // 2  # exclude system message
    examples = []

    # Build action history incrementally
    history: list[dict] = []

    for k in range(1, num_steps + 1):
        user_idx = 2 * k - 1
        asst_idx = 2 * k

        if asst_idx >= len(messages):
            break

        user_msg = messages[user_idx]["content"]
        asst_msg = messages[asst_idx]["content"]

        # Extract current observation
        observation = extract_observation(user_msg)

        # Extract action summary and result for history
        action_summary = summarize_action(asst_msg)
        # Result comes from the NEXT user message (messages[asst_idx + 1])
        next_user_idx = asst_idx + 1
        if next_user_idx < len(messages) and messages[next_user_idx]["role"] == "user":
            result = extract_result_line(messages[next_user_idx]["content"])
        else:
            result = "Done"

        if k == 1:
            # Step 1: add to history, but skip emitting example (unless --include-step1)
            history.append({"action_summary": action_summary, "result": result})
            if skip_first:
                continue
            # If not skipping first, emit with no history
            user_content = f"{instruction}\n\n{observation}"
        else:
            # Step k >= 2: build observation-free example
            history_text = build_action_history(history, window=history_window)
            user_content = f"{instruction}\n\n{history_text}\n\n{observation}"

            # Add current step to history for future steps
            history.append({"action_summary": action_summary, "result": result})

        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": asst_msg},
            ]
        })

    return examples


def primitive_from_task_id(task_id: str) -> str | None:
    """Extract primitive name from task_id like 'collect_backtracking_7'."""
    m = re.match(r"collect_(.+?)_\d+$", task_id)
    return m.group(1) if m else None


def main():
    parser = argparse.ArgumentParser(description="Prepare observation-free SFT data")
    parser.add_argument("--input", "-i", required=True, help="Input JSONL (multi-turn conversations)")
    parser.add_argument("--output", "-o", default="training/data/obsfree_train.jsonl", help="Output JSONL")
    parser.add_argument("--min-score", type=float, default=None, help="Minimum episode score")
    parser.add_argument("--only-success", action="store_true", help="Only score=1.0 episodes")
    parser.add_argument("--test-split", type=int, default=0, help="Hold out N examples for test set")
    parser.add_argument("--history-window", type=int, default=10,
                        help="Max previous steps in action history (default: 10)")
    parser.add_argument("--include-step1", action="store_true",
                        help="Include step 1 (no action history) in output")
    parser.add_argument("--exclude-primitives", nargs="+", default=None,
                        help="Primitives to exclude")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: {input_path} not found")
        sys.exit(1)

    exclude_set = set(args.exclude_primitives) if args.exclude_primitives else set()

    # Process conversations
    all_examples = []
    prim_counts = Counter()
    stats = {"total": 0, "score_filtered": 0, "prim_filtered": 0, "kept": 0}

    with open(input_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            messages = data["messages"]
            metadata = data.get("metadata", {})

            stats["total"] += 1

            # Score filtering
            score = metadata.get("score", 0)
            if args.only_success and score < 1.0:
                stats["score_filtered"] += 1
                continue
            if args.min_score is not None and score < args.min_score:
                stats["score_filtered"] += 1
                continue

            # Primitive filtering
            task_id = metadata.get("task_id", "")
            prim = primitive_from_task_id(task_id)
            if prim and prim in exclude_set:
                stats["prim_filtered"] += 1
                continue

            # Convert to single-turn examples
            examples = process_conversation(
                messages,
                history_window=args.history_window,
                skip_first=not args.include_step1,
            )

            if examples:
                stats["kept"] += 1
                all_examples.extend(examples)
                if prim:
                    prim_counts[prim] += len(examples)

    print(f"Episodes: {stats['total']} total, {stats['score_filtered']} score-filtered, "
          f"{stats['prim_filtered']} prim-filtered, {stats['kept']} kept")
    print(f"Examples: {len(all_examples)} single-turn training examples")

    if not all_examples:
        print("No examples to export.")
        sys.exit(1)

    # Per-primitive breakdown
    print(f"\nPer-primitive breakdown:")
    print(f"  {'Primitive':<30} {'Examples':>8}")
    for prim in sorted(prim_counts.keys()):
        print(f"  {prim:<30} {prim_counts[prim]:>8}")

    # Split test set
    test_examples = []
    if args.test_split > 0 and len(all_examples) > args.test_split:
        test_examples = all_examples[:args.test_split]
        all_examples = all_examples[args.test_split:]

    # Write output
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "w") as f:
        for ex in all_examples:
            f.write(json.dumps(ex) + "\n")
    print(f"\nTrain: {len(all_examples)} examples → {output}")

    if test_examples:
        test_path = output.with_name(output.stem + "_test" + output.suffix)
        with open(test_path, "w") as f:
            for ex in test_examples:
                f.write(json.dumps(ex) + "\n")
        print(f"Test:  {len(test_examples)} examples → {test_path}")

    # Stats
    total_chars = sum(
        sum(len(m["content"]) for m in ex["messages"])
        for ex in all_examples
    )
    print(f"\nStats: ~{total_chars // 4} tokens (estimated)")


if __name__ == "__main__":
    main()
