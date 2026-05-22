#!/usr/bin/env python3
"""Emit the headline results JSON for the /results page.

We use only numbers that appear in the published paper (Tables 2, 4, 5;
Figures 4 and 5). Per-trajectory data and the rule-based classifier's
internal counts are intentionally NOT exported — the site shows headline
aggregates, not raw runs.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "public" / "data"
OUT.mkdir(parents=True, exist_ok=True)


# Headline per-(model, primitive) intervention pass rate (%) and matched
# paired drop in pp, copied verbatim from Table 2 of the paper.
AGENTS = [
    {
        "model": "Gemini-3.1-Pro", "harness": "text",
        "total_clean_pass": 72.1, "total_iv_pass": 44.5, "total_delta_p": 27.6,
        "per_primitive": {
            "grounding":      {"iv_pass": 42.3, "delta_p": 34.5},
            "planning":       {"iv_pass": 59.6, "delta_p":  9.6},
            "state_tracking": {"iv_pass": 48.8, "delta_p": 13.1},
            "backtracking":   {"iv_pass": 40.2, "delta_p": 37.8},
            "patience":       {"iv_pass": 48.0, "delta_p": 24.0},
            "exploration":    {"iv_pass": 37.8, "delta_p": 10.8},
            "verification":   {"iv_pass": 40.8, "delta_p": 39.4},
        },
    },
    {
        "model": "Gemini-3-Flash", "harness": "text",
        "total_clean_pass": 63.2, "total_iv_pass": 42.6, "total_delta_p": 20.6,
        "per_primitive": {
            "grounding":      {"iv_pass": 34.5, "delta_p": 22.0},
            "planning":       {"iv_pass": 61.5, "delta_p":  3.8},
            "state_tracking": {"iv_pass": 47.6, "delta_p": 13.1},
            "backtracking":   {"iv_pass": 42.7, "delta_p": 35.4},
            "patience":       {"iv_pass": 48.0, "delta_p":  4.0},
            "exploration":    {"iv_pass": 43.2, "delta_p":  8.1},
            "verification":   {"iv_pass": 39.4, "delta_p": 33.8},
        },
    },
    {
        "model": "GPT-5.4", "harness": "text",
        "total_clean_pass": 61.3, "total_iv_pass": 35.1, "total_delta_p": 26.2,
        "per_primitive": {
            "grounding":      {"iv_pass": 26.8, "delta_p": 28.6},
            "planning":       {"iv_pass": 44.2, "delta_p": 28.8},
            "state_tracking": {"iv_pass": 36.9, "delta_p": 14.3},
            "backtracking":   {"iv_pass": 41.5, "delta_p": 35.4},
            "patience":       {"iv_pass": 52.0, "delta_p":  4.0},
            "exploration":    {"iv_pass": 29.7, "delta_p": 13.5},
            "verification":   {"iv_pass": 35.2, "delta_p": 36.6},
        },
    },
    {
        "model": "GPT-5.4-mini", "harness": "text",
        "total_clean_pass": 33.1, "total_iv_pass": 15.2, "total_delta_p": 17.9,
        "per_primitive": {
            "grounding":      {"iv_pass": 15.5, "delta_p": 14.3},
            "planning":       {"iv_pass": 15.4, "delta_p": 11.5},
            "state_tracking": {"iv_pass": 17.9, "delta_p":  8.3},
            "backtracking":   {"iv_pass":  8.5, "delta_p": 36.6},
            "patience":       {"iv_pass":  8.0, "delta_p": 20.0},
            "exploration":    {"iv_pass": 18.9, "delta_p":  2.7},
            "verification":   {"iv_pass": 19.7, "delta_p": 28.2},
        },
    },
    {
        "model": "Opus-4.7", "harness": "text",
        "total_clean_pass": 54.5, "total_iv_pass": 31.6, "total_delta_p": 22.9,
        "per_primitive": {
            "grounding":      {"iv_pass": 29.2, "delta_p": 24.4},
            "planning":       {"iv_pass": 23.1, "delta_p": 21.2},
            "state_tracking": {"iv_pass": 31.0, "delta_p": 19.0},
            "backtracking":   {"iv_pass": 37.8, "delta_p": 29.3},
            "patience":       {"iv_pass": 32.0, "delta_p":  8.0},
            "exploration":    {"iv_pass": 27.0, "delta_p":  5.4},
            "verification":   {"iv_pass": 39.4, "delta_p": 32.4},
        },
    },
    {
        "model": "Sonnet-4.6", "harness": "text",
        "total_clean_pass": 50.3, "total_iv_pass": 28.1, "total_delta_p": 22.2,
        "per_primitive": {
            "grounding":      {"iv_pass": 24.4, "delta_p": 29.8},
            "planning":       {"iv_pass": 21.2, "delta_p": 19.2},
            "state_tracking": {"iv_pass": 26.2, "delta_p": 17.9},
            "backtracking":   {"iv_pass": 34.1, "delta_p": 25.6},
            "patience":       {"iv_pass": 28.0, "delta_p":  0.0},
            "exploration":    {"iv_pass": 27.0, "delta_p":  2.7},
            "verification":   {"iv_pass": 38.0, "delta_p": 25.4},
        },
    },
    {
        "model": "v-Gemini-3.1-Pro", "harness": "vision",
        "total_clean_pass": 28.1, "total_iv_pass": 13.1, "total_delta_p": 15.0,
        "per_primitive": {
            "grounding":      {"iv_pass": 11.9, "delta_p": 14.3},
            "planning":       {"iv_pass": 11.5, "delta_p":  7.7},
            "state_tracking": {"iv_pass": 15.5, "delta_p": 15.5},
            "backtracking":   {"iv_pass": 12.2, "delta_p": 18.3},
            "patience":       {"iv_pass":  8.0, "delta_p":  0.0},
            "exploration":    {"iv_pass": 16.2, "delta_p":  5.4},
            "verification":   {"iv_pass": 15.5, "delta_p": 28.2},
        },
    },
    {
        "model": "v-GPT-5.4", "harness": "vision",
        "total_clean_pass": 10.2, "total_iv_pass": 5.6, "total_delta_p": 4.6,
        "per_primitive": {
            "grounding":      {"iv_pass":  7.1, "delta_p":  2.4},
            "planning":       {"iv_pass":  3.8, "delta_p":  3.8},
            "state_tracking": {"iv_pass":  4.8, "delta_p":  6.0},
            "backtracking":   {"iv_pass":  4.9, "delta_p":  6.1},
            "patience":       {"iv_pass":  4.0, "delta_p": -4.0},
            "exploration":    {"iv_pass":  5.4, "delta_p": -2.7},
            "verification":   {"iv_pass":  5.6, "delta_p": 14.1},
        },
    },
    {
        "model": "v-Opus-4.7", "harness": "vision",
        "total_clean_pass": 33.7, "total_iv_pass": 15.8, "total_delta_p": 17.9,
        "per_primitive": {
            "grounding":      {"iv_pass": 16.1, "delta_p": 17.3},
            "planning":       {"iv_pass": 17.3, "delta_p":  7.7},
            "state_tracking": {"iv_pass": 16.7, "delta_p": 11.9},
            "backtracking":   {"iv_pass": 14.6, "delta_p": 25.6},
            "patience":       {"iv_pass": 16.0, "delta_p":  4.0},
            "exploration":    {"iv_pass": 13.5, "delta_p": 10.8},
            "verification":   {"iv_pass": 15.5, "delta_p": 33.8},
        },
    },
]


SUMMARY = {
    "headline": {
        "text_drop_range_pp": [17.9, 27.6],
        "text_belief_failure_share_pct": 75,
        "vision_action_failure_share_pct": 57,
        "warm_human_drop_pp": 5.7,
        "cold_human_drop_pp": 10.0,
    },
    "agents": AGENTS,
    "failure_class_by_harness": {
        "text":   {"belief_pct": 75, "action_pct":  7, "overreach_pct": 18, "n": 1841},
        "vision": {"belief_pct": 42, "action_pct": 57, "overreach_pct":  1, "n": 1196},
    },
    "figures": [
        {
            "src": "/figures/fig_results_overview.png",
            "caption": "Per-(model, primitive) intervention pass rate and matched paired drop. Backtracking and verification are the most-affected primitives across the six text-mode agents (Table 2 / Figure 4).",
        },
        {
            "src": "/figures/fig_failure_landscape.png",
            "caption": "Failure landscape. Text agents are dominated by belief failures (the agent declares done on an unmutated backend); vision agents are dominated by action failures (the agent gets stuck on the page).",
        },
        {
            "src": "/figures/fig_agent_vs_human.png",
            "caption": "Human-vs-agent comparison on Human-140 intervention runs. Warm humans hold near 75% pass rate; the strongest text agent reaches 44.5%; the strongest vision agent reaches 15.8%.",
        },
    ],
}


def main() -> int:
    (OUT / "results_summary.json").write_text(json.dumps(SUMMARY, indent=2))
    print(f"emitted: results_summary.json ({len(AGENTS)} agents)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
