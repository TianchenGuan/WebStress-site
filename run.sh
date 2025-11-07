# export OPENAI_BASE_URL=http://127.0.0.1:30000/v1
# export OPENAI_API_KEY=EMPTY
# export LLM_MODEL=default


export SIMULATOR_OPENAI_BASE_URL=https://litellm.oit.duke.edu/v1
export SIMULATOR_OPENAI_API_KEY=sk-Ay4jrZcS2qDNxtGT9QLlJQ
export SIMULATOR_MODEL=gpt-5
# export AGENT_OPENAI_BASE_URL=http://127.0.0.1:30000/v1
# export AGENT_OPENAI_API_KEY=EMPTY
export AGENT_OPENAI_BASE_URL=https://openrouter.ai/api/v1
export AGENT_OPENAI_API_KEY=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
export AGENT_MODEL=qwen/qwen3-vl-235b-a22b-thinking
export AGENT_TEMP=0.0
export JUDGE_OPENAI_BASE_URL=https://litellm.oit.duke.edu/v1
export JUDGE_OPENAI_API_KEY=sk-Ay4jrZcS2qDNxtGT9QLlJQ
export JUDGE_MODEL=gpt-5
export PROPOSER_OPENAI_API_KEY=sk-Ay4jrZcS2qDNxtGT9QLlJQ
export PROPOSER_OPENAI_BASE_URL=https://litellm.oit.duke.edu/v1
export PROPOSER_MODEL=gpt-5
export COMPILER_OPENAI_API_KEY=sk-Ay4jrZcS2qDNxtGT9QLlJQ
export COMPILER_OPENAI_BASE_URL=https://litellm.oit.duke.edu/v1
export COMPILER_MODEL=gpt-5

python orchestrator.py --steps 16 --sim-mode diverse  --log-profile both --log-state-snapshots --instr-jsonl instructions/osworld_small.jsonl  --fidelity high --success-threshold 0.9


# python tools/profile_runner.py --instr-jsonl instructions/osworld_small.jsonl --instr-id bb5e4c0d-f964-439c-97b6-bdb9747de3f4 --steps 16 --sim-mode diverse --fidelity high


# python replay_agent_call.py \
#       --payload runs/ep-123-bb5e4c0d-f964-439c-97b6-bdb9747de3f4/llm/agent_step_0000.json \
#       --with-schema