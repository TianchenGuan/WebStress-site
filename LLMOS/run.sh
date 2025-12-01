# export OPENAI_BASE_URL=http://127.0.0.1:30000/v1
# export OPENAI_API_KEY=EMPTY
# export LLM_MODEL=default



duke_url=https://litellm.oit.duke.edu/v1
duke_key=sk-Ay4jrZcS2qDNxtGT9QLlJQ

openai_url=https://api.openai.com/v1
openai_key=***REDACTED***
openai_model=gpt-5.1

gemini_url=https://generativelanguage.googleapis.com/v1beta2/projects/202703895966/locations/us-central1/models/
gemini_model=models/gemini-3-pro-preview
# gemini_model=models/gemini-flash-latest
gemini_key=AIzaSyC2mebI93Nn0O05tYl_5JcJsxc__iYDkVw

use_url=$openai_url
use_key=$openai_key
use_model=$openai_model
# use_url=$gemini_url
# use_key=$gemini_key
# use_model=$gemini_model

export GOOGLE_API_KEY=$use_key

export SIMULATOR_OPENAI_BASE_URL=$use_url
export SIMULATOR_OPENAI_API_KEY=$use_key
export SIMULATOR_MODEL=$use_model
# export AGENT_OPENAI_BASE_URL=http://127.0.0.1:30000/v1
# export AGENT_OPENAI_API_KEY=EMPTY
export AGENT_OPENAI_BASE_URL=https://openrouter.ai/api/v1
export AGENT_OPENAI_API_KEY=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
export AGENT_MODEL=qwen/qwen3-vl-235b-a22b-thinking
export AGENT_TEMP=0.0
export JUDGE_OPENAI_BASE_URL=$use_url
export JUDGE_OPENAI_API_KEY=$use_key
export JUDGE_MODEL=$use_model
export PROPOSER_OPENAI_API_KEY=$use_key
export PROPOSER_OPENAI_BASE_URL=$use_url
export PROPOSER_MODEL=$use_model
export COMPILER_OPENAI_API_KEY=$use_key
export COMPILER_OPENAI_BASE_URL=$use_url
export COMPILER_MODEL=$use_model

python orchestrator.py --steps 16 --sim-feature-config prompts/feature_easy.json --log-profile both --log-state-snapshots --instr-jsonl instructions/osworld_two_task.jsonl --success-threshold 0.9


python orchestrator.py --steps 16 --sim-feature-config prompts/feature_easy2.json --log-profile both --log-state-snapshots --instr-jsonl instructions/osworld_two_task.jsonl --success-threshold 0.9

python orchestrator.py --steps 16 --sim-feature-config prompts/feature_medium.json --log-profile both --log-state-snapshots --instr-jsonl instructions/osworld_two_task.jsonl --success-threshold 0.9

python orchestrator.py --steps 16 --sim-feature-config prompts/feature_hard.json --log-profile both --log-state-snapshots --instr-jsonl instructions/osworld_two_task.jsonl --success-threshold 0.9

python orchestrator.py --steps 16 --sim-feature-config prompts/feature_hard2.json --log-profile both --log-state-snapshots --instr-jsonl instructions/osworld_two_task.jsonl --success-threshold 0.9



# python tools/profile_runner.py --instr-jsonl instructions/osworld_small.jsonl --instr-id bb5e4c0d-f964-439c-97b6-bdb9747de3f4 --steps 16 --sim-feature-config prompts/simulator_features.example.json


# python replay_agent_call.py \
#       --payload runs/ep-123-bb5e4c0d-f964-439c-97b6-bdb9747de3f4/llm/agent_step_0000.json \
#       --with-schema


# streamlit run viewer_streamlit.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
# ssh -L 8501:localhost:8501 xy200@cs-login
