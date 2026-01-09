"""
Example experiment configurations for WorkArena ablation studies.

This file defines specific ablation experiments to study simulator fidelity.
"""

from ..simulator_config import (
    SimulatorConfig,
    PromptConfig,
    StateRepresentationConfig,
    LLMProvider,
    StateRepresentation,
    ActionFormat,
    HistoryMode,
    SIMULATOR_PRESETS,
    get_ablation_configs,
)


# =============================================================================
# Experiment 1: LLM Backend Ablation
# Question: Which LLM provides the best simulator fidelity?
# =============================================================================

LLM_ABLATION_CONFIGS = [
    # OpenAI models
    SimulatorConfig(
        name="gpt4o",
        description="GPT-4o (baseline)",
        llm_provider=LLMProvider.OPENAI,
        llm_model="gpt-4o",
        tags=["llm_ablation", "openai", "baseline"],
    ),
    SimulatorConfig(
        name="gpt4o_mini",
        description="GPT-4o-mini (smaller, faster)",
        llm_provider=LLMProvider.OPENAI,
        llm_model="gpt-4o-mini",
        tags=["llm_ablation", "openai"],
    ),
    SimulatorConfig(
        name="gpt4_turbo",
        description="GPT-4 Turbo",
        llm_provider=LLMProvider.OPENAI,
        llm_model="gpt-4-turbo",
        tags=["llm_ablation", "openai"],
    ),

    # Gemini models
    SimulatorConfig(
        name="gemini_15_pro",
        description="Gemini 1.5 Pro",
        llm_provider=LLMProvider.GEMINI,
        llm_model="gemini-1.5-pro",
        tags=["llm_ablation", "gemini"],
    ),
    SimulatorConfig(
        name="gemini_15_flash",
        description="Gemini 1.5 Flash (faster)",
        llm_provider=LLMProvider.GEMINI,
        llm_model="gemini-1.5-flash",
        tags=["llm_ablation", "gemini"],
    ),
]


# =============================================================================
# Experiment 2: Prompt Design Ablation
# Question: How does prompt design affect simulator fidelity?
# =============================================================================

PROMPT_ABLATION_CONFIGS = [
    # Baseline: full prompt
    SimulatorConfig(
        name="prompt_full",
        description="Full prompt with CoT, examples, detailed instructions",
        prompt_config=PromptConfig(
            use_chain_of_thought=True,
            include_examples=True,
            num_examples=3,
            detailed_instructions=True,
            include_error_handling=True,
            include_edge_cases=True,
        ),
        tags=["prompt_ablation", "baseline"],
    ),

    # No chain-of-thought
    SimulatorConfig(
        name="prompt_no_cot",
        description="No chain-of-thought reasoning",
        prompt_config=PromptConfig(
            use_chain_of_thought=False,
            require_thought_field=False,
            include_examples=True,
            num_examples=3,
            detailed_instructions=True,
        ),
        tags=["prompt_ablation", "no_cot"],
    ),

    # No examples
    SimulatorConfig(
        name="prompt_no_examples",
        description="No examples in prompt",
        prompt_config=PromptConfig(
            use_chain_of_thought=True,
            include_examples=False,
            detailed_instructions=True,
        ),
        tags=["prompt_ablation", "no_examples"],
    ),

    # Minimal prompt
    SimulatorConfig(
        name="prompt_minimal",
        description="Minimal prompt - bare instructions only",
        prompt_config=PromptConfig(
            use_chain_of_thought=False,
            include_examples=False,
            detailed_instructions=False,
            include_error_handling=False,
            include_edge_cases=False,
            require_thought_field=False,
            require_events_field=False,
        ),
        tags=["prompt_ablation", "minimal"],
    ),

    # Varying number of examples
    SimulatorConfig(
        name="prompt_1_example",
        description="Single example in prompt",
        prompt_config=PromptConfig(
            include_examples=True,
            num_examples=1,
        ),
        tags=["prompt_ablation", "examples"],
    ),
    SimulatorConfig(
        name="prompt_5_examples",
        description="Five examples in prompt",
        prompt_config=PromptConfig(
            include_examples=True,
            num_examples=5,
        ),
        tags=["prompt_ablation", "examples"],
    ),
]


# =============================================================================
# Experiment 3: State Representation Ablation
# Question: How should state be represented to the simulator LLM?
# =============================================================================

STATE_ABLATION_CONFIGS = [
    # Full JSON (baseline)
    SimulatorConfig(
        name="state_full_json",
        description="Full JSON state including hidden_state",
        state_config=StateRepresentationConfig(
            mode=StateRepresentation.FULL_JSON,
            include_hidden_state=True,
            include_filesystem=True,
            include_tabs=True,
        ),
        tags=["state_ablation", "baseline"],
    ),

    # No hidden state
    SimulatorConfig(
        name="state_no_hidden",
        description="JSON without hidden_state",
        state_config=StateRepresentationConfig(
            mode=StateRepresentation.FILTERED_JSON,
            include_hidden_state=False,
        ),
        tags=["state_ablation", "no_hidden"],
    ),

    # Text-only accessibility tree
    SimulatorConfig(
        name="state_text_axtree",
        description="Text accessibility tree only",
        state_config=StateRepresentationConfig(
            mode=StateRepresentation.TEXT_AXTREE,
        ),
        tags=["state_ablation", "text_only"],
    ),

    # Truncated state
    SimulatorConfig(
        name="state_truncated_shallow",
        description="Truncated state (depth=3)",
        state_config=StateRepresentationConfig(
            max_ui_depth=3,
            max_children_per_node=5,
            max_text_length=100,
        ),
        tags=["state_ablation", "truncated"],
    ),
    SimulatorConfig(
        name="state_truncated_medium",
        description="Truncated state (depth=5)",
        state_config=StateRepresentationConfig(
            max_ui_depth=5,
            max_children_per_node=10,
            max_text_length=200,
        ),
        tags=["state_ablation", "truncated"],
    ),
    SimulatorConfig(
        name="state_truncated_deep",
        description="Truncated state (depth=10)",
        state_config=StateRepresentationConfig(
            max_ui_depth=10,
            max_children_per_node=20,
            max_text_length=500,
        ),
        tags=["state_ablation", "truncated"],
    ),
]


# =============================================================================
# Experiment 4: History Length Ablation
# Question: How much action history should the simulator see?
# =============================================================================

HISTORY_ABLATION_CONFIGS = [
    SimulatorConfig(
        name="history_none",
        description="No history",
        history_mode=HistoryMode.NONE,
        tags=["history_ablation"],
    ),
    SimulatorConfig(
        name="history_1",
        description="Last 1 action",
        history_mode=HistoryMode.LAST_N,
        history_length=1,
        tags=["history_ablation"],
    ),
    SimulatorConfig(
        name="history_3",
        description="Last 3 actions",
        history_mode=HistoryMode.LAST_N,
        history_length=3,
        tags=["history_ablation"],
    ),
    SimulatorConfig(
        name="history_5",
        description="Last 5 actions (baseline)",
        history_mode=HistoryMode.LAST_N,
        history_length=5,
        tags=["history_ablation", "baseline"],
    ),
    SimulatorConfig(
        name="history_10",
        description="Last 10 actions",
        history_mode=HistoryMode.LAST_N,
        history_length=10,
        tags=["history_ablation"],
    ),
    SimulatorConfig(
        name="history_full",
        description="Full history",
        history_mode=HistoryMode.FULL,
        tags=["history_ablation"],
    ),
]


# =============================================================================
# Experiment 5: Difficulty Settings Ablation
# Question: How do noise/determinism settings affect fidelity?
# =============================================================================

DIFFICULTY_ABLATION_CONFIGS = [
    SimulatorConfig(
        name="diff_clean_deterministic",
        description="Clean, deterministic (easiest)",
        information_density="rich",
        signal_noise_ratio="clean",
        determinism="deterministic",
        tags=["difficulty_ablation"],
    ),
    SimulatorConfig(
        name="diff_moderate",
        description="Moderate noise and determinism",
        information_density="moderate",
        signal_noise_ratio="moderate",
        determinism="moderate",
        tags=["difficulty_ablation"],
    ),
    SimulatorConfig(
        name="diff_noisy_stochastic",
        description="Noisy, stochastic (hardest)",
        information_density="minimal",
        signal_noise_ratio="noisy",
        determinism="stochastic",
        tags=["difficulty_ablation"],
    ),
]


# =============================================================================
# Combined: Full Factorial Experiment
# =============================================================================

def get_factorial_configs(
    llm_models: list[str] = ["gpt-4o", "gemini-1.5-pro"],
    history_lengths: list[int] = [0, 5, 10],
    with_cot: list[bool] = [True, False],
) -> list[SimulatorConfig]:
    """
    Generate factorial experiment configs.

    For a small factorial: 2 LLMs × 3 history × 2 CoT = 12 configs
    """
    configs = []

    for model in llm_models:
        provider = LLMProvider.OPENAI if "gpt" in model else LLMProvider.GEMINI

        for hist_len in history_lengths:
            for cot in with_cot:
                name = f"factorial_{model.replace('-', '')}_{hist_len}hist_{'cot' if cot else 'nocot'}"

                config = SimulatorConfig(
                    name=name,
                    description=f"{model}, history={hist_len}, CoT={cot}",
                    llm_provider=provider,
                    llm_model=model,
                    history_mode=HistoryMode.LAST_N if hist_len > 0 else HistoryMode.NONE,
                    history_length=hist_len if hist_len > 0 else 1,
                    prompt_config=PromptConfig(
                        use_chain_of_thought=cot,
                        require_thought_field=cot,
                    ),
                    tags=["factorial"],
                )
                configs.append(config)

    return configs


# =============================================================================
# All experiments
# =============================================================================

ALL_EXPERIMENTS = {
    "llm_ablation": LLM_ABLATION_CONFIGS,
    "prompt_ablation": PROMPT_ABLATION_CONFIGS,
    "state_ablation": STATE_ABLATION_CONFIGS,
    "history_ablation": HISTORY_ABLATION_CONFIGS,
    "difficulty_ablation": DIFFICULTY_ABLATION_CONFIGS,
}


def get_experiment_configs(experiment_name: str) -> list[SimulatorConfig]:
    """Get configs for a named experiment."""
    if experiment_name == "factorial":
        return get_factorial_configs()
    return ALL_EXPERIMENTS.get(experiment_name, [])
