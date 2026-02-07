#!/bin/bash
# =============================================================================
# LLMOS Run Examples
# =============================================================================
# This file documents all available parameters and configuration options.
# Uncomment the command you want to run, or use as reference.
#
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
#   # Simulator modules
#   --preset              Simulator preset: classic, default, efficient, thorough
#   --state-output        State output: full_state, delta_only, semantic_description
#   --abstraction         Abstraction: full_dom, semantic_elements, task_relevant, viewport_only, interactive_only
#   --memory              Memory: full_history, rolling_window, summarized, checkpoints
#   --reasoning           Reasoning: direct, chain
#   --verification        Verification: none, schema, constraint_check, backward
#   --temporal            Temporal: instant, async_aware, event_driven
#   --uncertainty         Uncertainty: deterministic, with_confidence, probabilistic, admits_uncertainty
#   --grounding           Grounding: llm_knowledge, example_grounded, doc_grounded, trace_grounded
#   # Agent
#   --agent-model         Agent model name (e.g., gpt-4o, gemini-1.5-pro, Qwen/Qwen3-8B)
#   --agent-provider      Agent provider: openai, gemini, vllm
#   --sim-model           Simulator model name
#   --sim-provider        Simulator provider: openai, gemini, vllm
#
# python -m llmos.main curriculum
#   --episodes, -n        Number of episodes (default: 10)
#   --tasks-file          JSON file with initial tasks
#   --auto-adjust         Auto-adjust difficulty based on performance
#   (+ all simulator/agent parameters above)
#
# python -m llmos.main benchmark <name>
#   name                  Benchmark name: workarena, webarena, osworld, miniwob
#   --episodes, -n        Number of episodes (default: all tasks)
#   --max-tasks           Maximum tasks to load from benchmark
#   --shuffle             Shuffle task order
#   --seed                Random seed for shuffling
#   --filter              Filter tasks by name patterns
#   (+ all simulator/agent parameters above)
#
# =============================================================================


# =============================================================================
# SINGLE TASK - BASIC EXAMPLES
# =============================================================================

# Minimal example
# python -m llmos.main run --task "Click the Settings button"

# With template
# python -m llmos.main run --task "Search for flights" --template browser
# python -m llmos.main run --task "Fill in the form" --template form

# =============================================================================
# SINGLE TASK - FULL PARAMETERS (ALL OPTIONS)
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
# DIFFICULTY & STRICTNESS EXAMPLES
# =============================================================================

# Difficulty levels (controls noise/chaos in simulator)
#   easy   - High determinism, low noise, helpful hints
#   medium - Moderate determinism and noise
#   hard   - Low determinism, realistic noise (default)
#   expert - Minimum determinism, maximum realism
# python -m llmos.main run --task "Open Chrome" --difficulty easy
# python -m llmos.main run --task "Open Chrome" --difficulty expert

# Strictness levels (controls rule enforcement)
#   lenient  - Single click can open apps, teleportation allowed
#   moderate - Some shortcuts allowed
#   strict   - Double click required, no teleportation, no shortcuts (default)
# python -m llmos.main run --task "Open Settings" --strictness lenient
# python -m llmos.main run --task "Open Settings" --strictness strict

# =============================================================================
# SIMULATOR PRESET EXAMPLES
# =============================================================================

# classic   - Original behavior (full_state, full_dom, full_history, direct)
# default   - Balanced (delta_only, rolling_window)
# efficient - Speed optimized (delta_only, semantic_elements, window=3)
# thorough  - Maximum accuracy (full_state, chain reasoning, verification)

# python -m llmos.main run --task "Open Chrome" --preset classic
# python -m llmos.main run --task "Open Chrome" --preset efficient
# python -m llmos.main run --task "Open Chrome" --preset thorough

# =============================================================================
# SIMULATOR MODULE EXAMPLES
# =============================================================================

# State output modes
#   full_state           - Complete state every step (consistent but verbose)
#   delta_only           - Only changes (efficient but may accumulate errors)
#   semantic_description - Natural language description
# python -m llmos.main run --task "Open Chrome" --state-output delta_only

# Abstraction levels
#   full_dom           - Full UI tree with all attributes
#   semantic_elements  - Buttons, inputs, text only
#   task_relevant      - Only elements relevant to task
#   viewport_only      - Only visible elements
#   interactive_only   - Only clickable/fillable elements
# python -m llmos.main run --task "Open Chrome" --abstraction semantic_elements

# Memory modes
#   full_history    - Keep all history (accurate but long context)
#   rolling_window  - Keep last N steps
#   summarized      - Summarize old history
#   checkpoints     - Keep key checkpoints
# python -m llmos.main run --task "Open Chrome" --memory rolling_window

# Reasoning modes
#   direct - Direct prediction
#   chain  - Chain-of-thought reasoning (slower but more accurate)
# python -m llmos.main run --task "Open Chrome" --reasoning chain

# Verification modes
#   none             - No verification
#   schema           - JSON schema validation (default)
#   constraint_check - Check physical constraints
#   backward         - Backward verification
# python -m llmos.main run --task "Open Chrome" --verification constraint_check

# Temporal modes
#   instant      - Actions have immediate effects
#   async_aware  - Model loading states, delays
#   event_driven - Explicit event sequences
# python -m llmos.main run --task "Open Chrome" --temporal async_aware

# Uncertainty modes
#   deterministic      - Single prediction
#   with_confidence    - Prediction + confidence score
#   probabilistic      - Multiple outcomes with probabilities
#   admits_uncertainty - Can say "I don't know"
# python -m llmos.main run --task "Open Chrome" --uncertainty with_confidence

# Grounding strategies
#   llm_knowledge     - Trust LLM's world knowledge
#   example_grounded  - Ground to provided examples
#   doc_grounded      - Ground to documentation
#   trace_grounded    - Ground to execution traces
# python -m llmos.main run --task "Open Chrome" --grounding example_grounded

# =============================================================================
# AGENT MODEL EXAMPLES
# =============================================================================

# Use specific agent model
# python -m llmos.main run --task "Open Chrome" --agent-model gpt-4o --agent-provider openai
# python -m llmos.main run --task "Open Chrome" --agent-model gpt-4o-mini --agent-provider openai
# python -m llmos.main run --task "Open Chrome" --agent-model gemini-1.5-pro --agent-provider gemini
# python -m llmos.main run --task "Open Chrome" --agent-model gemini-1.5-flash --agent-provider gemini

# Human agent mode (you control the agent interactively)
# python -m llmos.main run --task "Open the file manager" --human

# =============================================================================
# vLLM LOCAL MODEL EXAMPLES
# =============================================================================
# Use a local model via vLLM as the agent while keeping an API model as simulator.
# Requires a running vLLM server (configure base_url in config.json under llm.vllm).
#
# Start vLLM server first:
#   python -m vllm.entrypoints.openai.api_server \
#       --model Qwen/Qwen3-8B --port 8000
#
# Or for Llama:
#   python -m vllm.entrypoints.openai.api_server \
#       --model meta-llama/Llama-3.1-8B-Instruct --port 8000

# Qwen3-8B agent with Gemini simulator
# python -m llmos.main run \
#     --task "Click the Settings button" \
#     --agent-provider vllm \
#     --agent-model Qwen/Qwen3-8B \
#     --sim-provider gemini \
#     --sim-model gemini-3-flash-preview

# Llama-3.1 agent with Gemini simulator
# python -m llmos.main run \
#     --task "Click the Settings button" \
#     --agent-provider vllm \
#     --agent-model meta-llama/Llama-3.1-8B-Instruct \
#     --sim-provider gemini \
#     --sim-model gemini-3-flash-preview

# Fine-tuned model evaluation (after RL training with Tinker)
# python -m llmos.main run \
#     --task "Fill out the form" \
#     --template form \
#     --difficulty hard \
#     --agent-provider vllm \
#     --agent-model /path/to/finetuned-model \
#     --sim-provider gemini \
#     --sim-model gemini-3-flash-preview

# Benchmark a local model (vLLM agent + API simulator)
# python -m llmos.main benchmark workarena \
#     --episodes 10 \
#     --agent-provider vllm \
#     --agent-model Qwen/Qwen3-8B \
#     --sim-provider gemini \
#     --sim-model gemini-3-flash-preview \
#     --difficulty hard \
#     --strictness strict

# vLLM as both agent AND simulator (fully local, no API keys needed)
# python -m llmos.main run \
#     --task "Open Chrome" \
#     --agent-provider vllm \
#     --agent-model Qwen/Qwen3-8B \
#     --sim-provider vllm \
#     --sim-model Qwen/Qwen3-8B

# =============================================================================
# CURRICULUM LEARNING EXAMPLES
# =============================================================================

# Basic curriculum
# python -m llmos.main curriculum --episodes 10

# With auto-adjusting difficulty
# python -m llmos.main curriculum --episodes 20 --auto-adjust

# Full parameters
# python -m llmos.main curriculum \
#     --episodes 20 \
#     --difficulty easy \
#     --strictness strict \
#     --action-space minimal \
#     --preset classic \
#     --reasoning chain \
#     --agent-model gpt-4o-mini \
#     --auto-adjust

# =============================================================================
# BENCHMARK EVALUATION EXAMPLES
# =============================================================================

# Basic WorkArena benchmark
# python -m llmos.main benchmark workarena --episodes 5

# Full parameters
# python -m llmos.main benchmark workarena \
#     --episodes 10 \
#     --max-tasks 50 \
#     --shuffle \
#     --seed 42 \
#     --difficulty hard \
#     --strictness strict \
#     --action-space minimal \
#     --preset classic \
#     --reasoning chain \
#     --verification constraint_check \
#     --agent-model gpt-4o \
#     --agent-provider openai

# =============================================================================
# LIGHTWEIGHT SCRIPTS (no logging/HTML export overhead)
# =============================================================================

# Quick single task test
# python -m llmos.scripts.run_example \
#     --task "Click the Settings button" \
#     --template desktop \
#     --difficulty hard \
#     --strictness strict \
#     --max-steps 10

# Quick WorkArena test
# python -m llmos.scripts.run_workarena \
#     --num-tasks 5 \
#     --agent gpt-4o-mini \
#     --difficulty hard \
#     --strictness strict \
#     --output-dir results/test

# =============================================================================
# OTHER COMMANDS
# =============================================================================

# Show current config
# python -m llmos.main config --show

# List available benchmarks
# python -m llmos.main list-benchmarks

# =============================================================================
# DEFAULT COMMAND
# =============================================================================

python -m llmos.main run \
    --task "Play the most popular song by the artist of the fourth most recently added song in my Apple Music app's library, add it to my favorites, and download it." \
    --template desktop \
    --difficulty expert \
    --strictness strict \
    --action-space minimal \
    --sim-model "gemini-3-flash-preview" \
    --sim-provider gemini \
    --agent-provider gemini \
    --agent-model "gemini-3-flash-preview"
      



# python -m llmos.main benchmark workarena \
#       --strictness strict \
#       --difficulty hard \
#       --episodes 5 \
#       --max-tasks 50 \
#       --shuffle \
#       --seed 42 \
#       --agent-model "gemini-3-flash-preview" \
#       --agent-provider gemini \
#       --parallel \
#       --workers 4