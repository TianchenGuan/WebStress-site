#!/bin/bash
# =============================================================================
# WebAgentBench — Agent Evaluation Runner
# =============================================================================
# Evaluates an LLM agent on the standalone WebAgentBench (real browser pages).
#
# Prerequisites:
#   1. Install dependencies:  uv pip install playwright && playwright install chromium
#   2. For vLLM models: start a vLLM server (see below)
#
# Usage: ./run_webagentbench.sh
# =============================================================================

set -e
cd "$(dirname "$0")"
source .venv/bin/activate

# =============================================================================
# PARAMETER REFERENCE
# =============================================================================
#
# python -m webagentbench.agent_eval
#   --model             Model name (required)
#   --provider          LLM provider: vllm, openai (default: vllm)
#   --api-base-url      API base URL (auto-detected per provider)
#   --api-key           API key (auto-detected per provider)
#   --temperature       Sampling temperature (default: 0.3)
#   --pages             Specific page_ids to evaluate (default: all 10)
#   --max-steps         Max agent steps per page (default: 30)
#   --timeout           Timeout per page in seconds (default: 180)
#   --headless          Run browser headless (default)
#   --no-headless       Show the browser window
#   --server-host       WebAgentBench server host (default: 127.0.0.1)
#   --server-port       WebAgentBench server port (default: 8080)
#   --output            Results JSON path (default: results.json)
#   --quiet             Less output
#
# Available pages:
#   wizard_form, slow_search, dark_checkout, popup_landing, flaky_form,
#   filter_dashboard, scavenger_hunt, fake_success, broken_layout, session_content
#

# =============================================================================
# 1. vLLM SERVER (start separately before running this script)
# =============================================================================
# For Llama-3.1-8B:
#   python -m vllm.entrypoints.openai.api_server \
#       --model meta-llama/Llama-3.1-8B-Instruct \
#       --port 8000
#
# For Qwen3-8B:
#   python -m vllm.entrypoints.openai.api_server \
#       --model Qwen/Qwen3-8B \
#       --port 8000

# =============================================================================
# 2. EXAMPLES
# =============================================================================

# --- Llama-3.1-8B (all 10 pages) ---
# python -m webagentbench.agent_eval \
#     --model meta-llama/Llama-3.1-8B-Instruct \
#     --provider vllm \
#     --output results/llama3.1-8b_all.json

# --- Llama-3.1-8B (specific pages) ---
# python -m webagentbench.agent_eval \
#     --model meta-llama/Llama-3.1-8B-Instruct \
#     --provider vllm \
#     --pages dark_checkout wizard_form broken_layout \
#     --output results/llama3.1-8b_subset.json

# --- Llama-3.1-8B (with visible browser for debugging) ---
# python -m webagentbench.agent_eval \
#     --model meta-llama/Llama-3.1-8B-Instruct \
#     --provider vllm \
#     --no-headless \
#     --pages broken_layout \
#     --output results/llama3.1-8b_debug.json

# --- Qwen3-8B ---
# python -m webagentbench.agent_eval \
#     --model Qwen/Qwen3-8B \
#     --provider vllm \
#     --output results/qwen3-8b_all.json

# --- OpenAI model ---
# python -m webagentbench.agent_eval \
#     --model gpt-4o \
#     --provider openai \
#     --output results/gpt4o_all.json

# --- Custom vLLM server URL ---
# python -m webagentbench.agent_eval \
#     --model meta-llama/Llama-3.1-8B-Instruct \
#     --provider vllm \
#     --api-base-url http://gpu-server:8000/v1 \
#     --output results/llama3.1-8b_remote.json

# =============================================================================
# DEFAULT COMMAND
# =============================================================================

python -m webagentbench.agent_eval \
    --model meta-llama/Llama-3.1-8B-Instruct \
    --provider vllm \
    --max-steps 30 \
    --timeout 180 \
    --output results/llama3.1-8b_webagentbench.json
