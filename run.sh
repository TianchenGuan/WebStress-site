#!/bin/bash
# =============================================================================
# LLMOS Run Examples
# =============================================================================
# Uncomment the command you want to run, or use as reference.
# Usage: ./run.sh
# =============================================================================

set -e
cd "$(dirname "$0")"
source .venv/bin/activate

# =============================================================================
# CLI PARAMETERS REFERENCE
# =============================================================================
#
# python -m llmos.main run
#   --task, -t            Task instruction (string)
#   --task-file, -f       JSON file with task instruction
#   --template            Initial state template: desktop, browser, form
#   --difficulty, -d      Simulator difficulty: easy, medium, hard, expert
#   --strictness, -s      Simulator strictness: lenient, moderate, strict
#   --action-space        Agent action space: minimal, full
#   --task-difficulty     Task metadata difficulty (defaults to --difficulty)
#   --human               Use human agent for debugging
#   --no-save             Don't save episode to disk
#   --quiet, -q           Less output
#
#   # Simulator modules
#   --preset              Preset: classic, default, efficient, thorough
#   --state-output        Output: full_state, delta_only, semantic_description
#   --abstraction         Level: full_dom, semantic_elements, task_relevant, viewport_only, interactive_only
#   --memory              Mode: full_history, rolling_window, summarized, checkpoints
#   --reasoning           Mode: direct, chain
#   --verification        Mode: none, schema, constraint_check, backward
#   --temporal            Mode: instant, async_aware, event_driven
#   --uncertainty         Mode: deterministic, with_confidence, probabilistic, admits_uncertainty
#   --grounding           Strategy: llm_knowledge, example_grounded, doc_grounded, trace_grounded
#
#   # Adversarial (creates realistic obstacles for agent training)
#   --adversarial         Mode: none, subtle, deceptive, hostile, primitive_targeted
#   --adversarial-primitives  Target specific primitives (with --adversarial primitive_targeted):
#                             backtracking, reflection, exploration, planning, memory,
#                             patience, error_recovery, verification, constraint_satisfaction,
#                             adversarial_robustness, attention_focus, spatial_reasoning
#
#   # Model selection
#   --agent-model         Agent model name (e.g., gpt-4o, gemini-1.5-pro, Qwen/Qwen3-8B)
#   --agent-provider      Agent provider: openai, gemini, vllm
#   --sim-model           Simulator model name
#   --sim-provider        Simulator provider: openai, gemini, vllm
#
# python -m llmos.main curriculum
#   --episodes, -n        Number of episodes (default: 10)
#   --tasks-file          JSON file with initial tasks
#   --auto-adjust         Auto-adjust difficulty based on performance
#   (+ all run parameters above)
#
# python -m llmos.main benchmark <name>
#   name                  Benchmark: workarena, webarena, osworld, miniwob
#   --episodes, -n        Number of episodes (default: all tasks)
#   --max-tasks           Maximum tasks to load
#   --shuffle             Shuffle task order
#   --seed                Random seed
#   --filter              Filter tasks by name patterns
#   --parallel, -p        Run episodes in parallel
#   --workers, -w         Number of parallel workers (default: 4)
#   (+ all run parameters above)
#
# =============================================================================


# =============================================================================
# 1. BASIC EXAMPLES
# =============================================================================

# Minimal
# python -m llmos.main run --task "Click the Settings button"

# With template
# python -m llmos.main run --task "Search for flights" --template browser
# python -m llmos.main run --task "Fill in the form" --template form

# Human agent (interactive debugging)
# python -m llmos.main run --task "Open the file manager" --human

# =============================================================================
# 2. DIFFICULTY & STRICTNESS
# =============================================================================

# Difficulty (simulator noise/chaos level)
# python -m llmos.main run --task "Open Chrome" --difficulty easy     # High determinism, clean output
# python -m llmos.main run --task "Open Chrome" --difficulty medium   # Moderate noise
# python -m llmos.main run --task "Open Chrome" --difficulty hard     # Realistic noise
# python -m llmos.main run --task "Open Chrome" --difficulty expert   # Maximum realism

# Strictness (rule enforcement)
# python -m llmos.main run --task "Open Settings" --strictness lenient   # Single click opens, shortcuts OK
# python -m llmos.main run --task "Open Settings" --strictness moderate  # Some shortcuts
# python -m llmos.main run --task "Open Settings" --strictness strict    # Dblclick required, no shortcuts

# =============================================================================
# 3. ADVERSARIAL MODES
# =============================================================================
# Adversarial modes create realistic obstacles to challenge the agent.
# When active, difficulty/strictness are disabled (adversarial controls behavior).

# Subtle: realistic obstacles (popups, validation errors, loading delays)
# python -m llmos.main run --task "Submit the contact form" --adversarial subtle

# Deceptive: ambiguous UI (similar buttons, misleading labels, dark patterns)
# python -m llmos.main run --task "Cancel the subscription" --adversarial deceptive

# Hostile: active interference (session expiry, network errors, forced redirects)
# python -m llmos.main run --task "Save the document" --adversarial hostile

# Primitive-targeted: challenge specific agent capabilities
# python -m llmos.main run --task "Fill the multi-page form" \
#     --adversarial primitive_targeted

# Target specific primitives only
# python -m llmos.main run --task "Fill the multi-page form" \
#     --adversarial primitive_targeted \
#     --adversarial-primitives backtracking memory verification

# All 12 primitives: backtracking, reflection, exploration, planning, memory,
#   patience, error_recovery, verification, constraint_satisfaction,
#   adversarial_robustness, attention_focus, spatial_reasoning

# =============================================================================
# 4. SIMULATOR PRESETS & MODULES
# =============================================================================

# Presets
# python -m llmos.main run --task "Open Chrome" --preset classic     # Full state, full history, direct
# python -m llmos.main run --task "Open Chrome" --preset default     # Delta only, rolling window
# python -m llmos.main run --task "Open Chrome" --preset efficient   # Delta, semantic elements, window=3
# python -m llmos.main run --task "Open Chrome" --preset thorough    # Full state, chain reasoning, verification

# Individual module overrides
# python -m llmos.main run --task "Open Chrome" --state-output delta_only
# python -m llmos.main run --task "Open Chrome" --abstraction semantic_elements
# python -m llmos.main run --task "Open Chrome" --memory rolling_window
# python -m llmos.main run --task "Open Chrome" --reasoning chain
# python -m llmos.main run --task "Open Chrome" --verification constraint_check
# python -m llmos.main run --task "Open Chrome" --temporal async_aware
# python -m llmos.main run --task "Open Chrome" --uncertainty with_confidence
# python -m llmos.main run --task "Open Chrome" --grounding example_grounded

# =============================================================================
# 5. MODEL SELECTION
# =============================================================================

# API models
# python -m llmos.main run --task "Open Chrome" --agent-model gpt-4o --agent-provider openai
# python -m llmos.main run --task "Open Chrome" --agent-model gemini-1.5-pro --agent-provider gemini

# vLLM local models (requires running vLLM server)
#   python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen3-8B --port 8000
# python -m llmos.main run \
#     --task "Click the Settings button" \
#     --agent-provider vllm --agent-model Qwen/Qwen3-8B \
#     --sim-provider gemini --sim-model gemini-3-flash-preview

# Fine-tuned model evaluation (after RL training with Tinker)
# python -m llmos.main run \
#     --task "Fill out the form" --template form --difficulty hard \
#     --agent-provider vllm --agent-model /path/to/finetuned-model \
#     --sim-provider gemini --sim-model gemini-3-flash-preview

# Fully local (vLLM as both agent and simulator, no API keys)
# python -m llmos.main run \
#     --task "Open Chrome" \
#     --agent-provider vllm --agent-model Qwen/Qwen3-8B \
#     --sim-provider vllm --sim-model Qwen/Qwen3-8B

# =============================================================================
# 6. FULL PARAMETER EXAMPLE
# =============================================================================

# python -m llmos.main run \
#     --task "Change the Chrome start page background image to the third most recent photo, sorted by time, from the /user/yxj/image folder." \
#     --template desktop \
#     --difficulty hard \
#     --strictness strict \
#     --action-space minimal \
#     --preset classic \
#     --state-output full_state \
#     --abstraction full_dom \
#     --memory full_history \
#     --reasoning direct \
#     --verification schema \
#     --temporal instant \
#     --uncertainty deterministic \
#     --grounding llm_knowledge \
#     --agent-model gpt-4o-mini \
#     --agent-provider openai

# =============================================================================
# 7. CURRICULUM LEARNING
# =============================================================================

# python -m llmos.main curriculum --episodes 10
# python -m llmos.main curriculum --episodes 20 --auto-adjust
# python -m llmos.main curriculum \
#     --episodes 20 --difficulty easy --strictness strict \
#     --preset classic --reasoning chain --agent-model gpt-4o-mini --auto-adjust

# With adversarial obstacles
# python -m llmos.main curriculum --episodes 20 --adversarial subtle --auto-adjust

# =============================================================================
# 8. BENCHMARK EVALUATION
# =============================================================================

# python -m llmos.main benchmark workarena --episodes 5
# python -m llmos.main benchmark workarena \
#     --episodes 10 --max-tasks 50 --shuffle --seed 42 \
#     --difficulty hard --strictness strict \
#     --agent-model gpt-4o --agent-provider openai

# Parallel benchmark
# python -m llmos.main benchmark workarena \
#     --episodes 20 --parallel --workers 4 \
#     --agent-provider vllm --agent-model Qwen/Qwen3-8B \
#     --sim-provider gemini --sim-model gemini-3-flash-preview

# Adversarial benchmark (stress-test agent robustness)
# python -m llmos.main benchmark workarena \
#     --episodes 10 --adversarial hostile \
#     --agent-model gpt-4o --agent-provider openai

# =============================================================================
# 9. LIGHTWEIGHT SCRIPTS
# =============================================================================

# python -m llmos.scripts.run_example \
#     --task "Click the Settings button" --template desktop \
#     --difficulty hard --strictness strict --max-steps 10

# python -m llmos.scripts.run_workarena \
#     --num-tasks 5 --agent gpt-4o-mini \
#     --difficulty hard --strictness strict --output-dir results/test

# =============================================================================
# 10. UTILITY COMMANDS
# =============================================================================

# python -m llmos.main config --show
# python -m llmos.main list-benchmarks

# =============================================================================
# DEFAULT COMMAND
# =============================================================================

python -m llmos.main run \
    --task "Play the most popular song by the artist of my fourth most recently added track. Also, favorite and download that song." \
    --template desktop \
    --difficulty expert \
    --strictness strict \
    --action-space minimal \
    --sim-model "gemini-3-flash-preview" \
    --sim-provider gemini \
    --agent-provider gemini \
    --agent-model "gemini-3-flash-preview"