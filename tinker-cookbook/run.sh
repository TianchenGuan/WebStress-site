# export TINKER_API_KEY=tml-O3SgjxAhYQ9uT5eM1XNyfcsymjqi3iv6dgmGFLm194dclTvXHDEcQof8cF2q4e8kEAAAA

# duke_url=https://litellm.oit.duke.edu/v1
# duke_key=sk-Ay4jrZcS2qDNxtGT9QLlJQ


# openai_url=https://api.openai.com/v1
# openai_key=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
# openai_model=gpt-5.1

# gemini_url=https://generativelanguage.googleapis.com/v1beta2/projects/202703895966/locations/us-central1/models/
# gemini_model=models/gemini-3-pro-preview
# # gemini_model=models/gemini-flash-latest
# gemini_key=AIzaSyC2mebI93Nn0O05tYl_5JcJsxc__iYDkVw

# use_url=$openai_url
# use_key=$openai_key
# use_model=$openai_model
# # use_url=$gemini_url
# # use_key=$gemini_key
# # use_model=$gemini_model

# export GOOGLE_API_KEY=$use_key

# export SIMULATOR_OPENAI_BASE_URL=$use_url
# export SIMULATOR_OPENAI_API_KEY=$use_key
# export SIMULATOR_MODEL=$use_model
# # export AGENT_OPENAI_BASE_URL=http://127.0.0.1:30000/v1
# # export AGENT_OPENAI_API_KEY=EMPTY
# export AGENT_OPENAI_BASE_URL=https://openrouter.ai/api/v1
# export AGENT_OPENAI_API_KEY=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
# export AGENT_MODEL=qwen/qwen3-vl-235b-a22b-thinking
# export AGENT_TEMP=0.0
# export JUDGE_OPENAI_BASE_URL=$use_url
# export JUDGE_OPENAI_API_KEY=$use_key
# export JUDGE_MODEL=$use_model
# export PROPOSER_OPENAI_API_KEY=$use_key
# export PROPOSER_OPENAI_BASE_URL=$use_url
# export PROPOSER_MODEL=$use_model
# export COMPILER_OPENAI_API_KEY=$use_key
# export COMPILER_OPENAI_BASE_URL=$use_url
# export COMPILER_MODEL=$use_model

set -a           # export everything read afterwards
source .env
set +a

uv run -- \
  python -m tinker_cookbook.recipes.llmos_rl.train \
    instruction_path=../LLMOS/instructions/osworld_two_task.jsonl \
    groups_per_batch=4 \
    group_size=2 \
    max_tokens=512 \
    default_max_steps=6 \
	  log_path=$(pwd)/runs/llmos_rl_run_$(date +%H%M)

