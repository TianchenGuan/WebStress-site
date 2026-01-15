"""
Leaderboard parser for WorkArena benchmark scores.

Parses the official BrowserGym leaderboard CSV and extracts scores
for correlation analysis.
"""

import csv
import re
from pathlib import Path
from typing import Optional


# Mapping from our agent IDs to leaderboard agent name patterns
AGENT_ID_MAPPING = {
    "gpt-5-mini": "GPT-5-mini",
    "gpt-4o-mini": "GPT-4o-mini",
    "gpt-o1-mini": "GPT-o1-mini",
    "gpt-4o": "GPT-4o",
    "gpt-5": "GPT-5",
    "claude-3.5-sonnet": "Claude-3.5-Sonnet",
    "claude-4-sonnet": "Claude-4-Sonnet",
    "llama-3.1-70b": "Llama-3.1-70b",
    "llama-3.1-405b": "Llama-3.1-405b",
}


def extract_agent_name(html_cell: str) -> str:
    """
    Extract agent name from HTML-formatted cell.

    Example input:
        '<a href="...">GenericAgent-GPT-4o-mini</a>'

    Returns:
        'GPT-4o-mini'
    """
    # Try to extract from HTML anchor tag
    match = re.search(r'>([^<]+)</a>', html_cell)
    if match:
        full_name = match.group(1)
        # Remove common prefixes
        for prefix in ["GenericAgent-", "OrbyAgent-"]:
            if full_name.startswith(prefix):
                return full_name[len(prefix):]
        return full_name

    # If no HTML, return as-is
    return html_cell.strip()


def parse_leaderboard(
    csv_path: str,
    benchmark_column: str = "WorkArena-L2",
) -> dict[str, float]:
    """
    Parse leaderboard CSV and extract scores for a specific benchmark.

    Args:
        csv_path: Path to the leaderboard CSV file.
        benchmark_column: Column name for the benchmark scores.

    Returns:
        Dictionary mapping agent names to scores.
    """
    scores = {}
    csv_path = Path(csv_path)

    if not csv_path.exists():
        raise FileNotFoundError(f"Leaderboard file not found: {csv_path}")

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if benchmark_column not in reader.fieldnames:
            raise ValueError(
                f"Column '{benchmark_column}' not found. "
                f"Available columns: {reader.fieldnames}"
            )

        for row in reader:
            agent_html = row.get("Agent", "")
            agent_name = extract_agent_name(agent_html)

            score_str = row.get(benchmark_column, "").strip()

            # Skip missing scores (marked as "-" or empty)
            if not score_str or score_str == "-":
                continue

            try:
                score = float(score_str)
                scores[agent_name] = score
            except ValueError:
                continue

    return scores


def get_workarena_l2_scores(
    csv_path: Optional[str] = None,
    agent_ids: Optional[list[str]] = None,
) -> dict[str, float]:
    """
    Get WorkArena L2 scores for specified agents.

    Args:
        csv_path: Path to leaderboard CSV. If None, uses default location.
        agent_ids: List of agent IDs to retrieve. If None, returns all.

    Returns:
        Dictionary mapping agent IDs to their WorkArena-L2 scores.
    """
    if csv_path is None:
        # Default path relative to this file
        csv_path = Path(__file__).parent.parent / "workarena-official-leaderboard.csv"

    all_scores = parse_leaderboard(str(csv_path), "WorkArena-L2")

    if agent_ids is None:
        # Return all scores with normalized agent IDs
        result = {}
        for agent_name, score in all_scores.items():
            # Find matching agent ID
            agent_id = normalize_agent_id(agent_name)
            result[agent_id] = score
        return result

    # Filter to requested agent IDs
    result = {}
    for agent_id in agent_ids:
        leaderboard_name = AGENT_ID_MAPPING.get(agent_id)
        if leaderboard_name and leaderboard_name in all_scores:
            result[agent_id] = all_scores[leaderboard_name]
        else:
            # Try direct match
            for name, score in all_scores.items():
                if normalize_agent_id(name) == agent_id:
                    result[agent_id] = score
                    break

    return result


def normalize_agent_id(agent_name: str) -> str:
    """
    Normalize agent name to standard agent ID format.

    Example:
        'GPT-4o-mini' -> 'gpt-4o-mini'
        'Claude-3.5-Sonnet' -> 'claude-3.5-sonnet'
    """
    return agent_name.lower().replace(" ", "-")


def get_agent_ranking(
    csv_path: Optional[str] = None,
    benchmark_column: str = "WorkArena-L2",
) -> list[tuple[str, float]]:
    """
    Get agents ranked by score (descending).

    Returns:
        List of (agent_id, score) tuples, sorted by score descending.
    """
    scores = get_workarena_l2_scores(csv_path)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


if __name__ == "__main__":
    # Test the parser
    import sys

    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        csv_path = Path(__file__).parent.parent / "workarena-official-leaderboard.csv"

    print(f"Parsing: {csv_path}")
    print()

    scores = get_workarena_l2_scores(str(csv_path))
    print("WorkArena-L2 Scores:")
    print("-" * 40)

    for agent_id, score in get_agent_ranking(str(csv_path)):
        print(f"  {agent_id:<25} {score:>6.2f}%")

    print()
    print("Target agents for correlation study:")
    target_agents = ["gpt-5-mini", "gpt-4o-mini", "gpt-o1-mini"]
    target_scores = get_workarena_l2_scores(str(csv_path), target_agents)
    for agent_id, score in target_scores.items():
        print(f"  {agent_id}: {score}%")
