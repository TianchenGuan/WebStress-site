from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import chz
import tinker

from tinker_cookbook import cli_utils
from tinker_cookbook.recipes.llmos_rl.dataset import LLMOSInstructionDatasetBuilder
from tinker_cookbook.recipes.llmos_rl.env import LLMOSEnvOptions, RendererBundle
from tinker_cookbook.rl import train
logger = logging.getLogger(__name__)


# --- Locate LLMOS sources so we can import simulator/judge components ---------------------------
THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[4]  # .../LLMOS/
LLMOS_SRC = REPO_ROOT / "LLMOS"

if not LLMOS_SRC.exists():
    raise RuntimeError(
        f"Cannot find LLMOS sources at {LLMOS_SRC}. Ensure the simulator lives under LLMOS/LLMOS/."
    )

if str(LLMOS_SRC) not in sys.path:
    sys.path.append(str(LLMOS_SRC))

def _load_sim_feature_config(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Simulator feature config not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Simulator feature config must be a JSON object")
    return data


@chz.chz
class CLIConfig:
    model_name: str = "Qwen/Qwen3-4B-Instruct-2507"
    lora_rank: int = 32
    instruction_path: str = str(LLMOS_SRC / "instructions" / "osworld_two_task.jsonl")
    groups_per_batch: int = 8
    group_size: int = 4
    learning_rate: float = 1e-5
    max_tokens: int = 512
    kl_penalty_coef: float = 0.0
    num_substeps: int = 1
    dataset_n: int = -1
    dataset_seed: int | None = None
    default_fidelity: str = "low"
    default_max_steps: int = 8
    agent_history: int = 4
    sim_feature_config_path: str | None = None
    sim_include_state: bool = True
    judge_temperature: float = 0.0
    log_path: str | None = None
    eval_every: int = 0
    save_every: int = 10
    wandb_project: str | None = None
    wandb_name: str | None = None
    train_batches: int = 256
    behavior_if_log_dir_exists: cli_utils.LogdirBehavior = "ask"


async def cli_main(cli_config: CLIConfig, env: Any | None):
    model_name_safe = cli_config.model_name.replace("/", "-")
    run_id = datetime.now().strftime("%Y-%m-%d-%H-%M")
    run_name = f"llmos_rl_{model_name_safe}_{run_id}"
    log_path = cli_config.log_path or f"/tmp/tinker-examples/llmos_rl/{run_name}"
    cli_utils.check_log_dir(log_path, behavior_if_exists=cli_config.behavior_if_log_dir_exists)

    sim_feature_config = _load_sim_feature_config(cli_config.sim_feature_config_path)

    renderer_bundle = RendererBundle.from_model_name(cli_config.model_name)
    env_options = LLMOSEnvOptions(
        renderer_bundle=renderer_bundle,
        sim_include_state=cli_config.sim_include_state,
        judge_temperature=cli_config.judge_temperature,
        group_size=cli_config.group_size,
    )

    dataset_builder = LLMOSInstructionDatasetBuilder(
        instruction_path=cli_config.instruction_path,
        groups_per_batch=cli_config.groups_per_batch,
        default_seed=cli_config.dataset_seed or 0,
        default_fidelity=cli_config.default_fidelity,
        default_max_steps=cli_config.default_max_steps,
        agent_history=cli_config.agent_history,
        dataset_n=cli_config.dataset_n,
        dataset_seed=cli_config.dataset_seed,
        sim_feature_config=sim_feature_config,
        env_options=env_options,
        max_batches=cli_config.train_batches,
    )

    cfg = train.Config(
        learning_rate=cli_config.learning_rate,
        dataset_builder=dataset_builder,
        model_name=cli_config.model_name,
        max_tokens=cli_config.max_tokens,
        lora_rank=cli_config.lora_rank,
        kl_penalty_coef=cli_config.kl_penalty_coef,
        num_substeps=cli_config.num_substeps,
        wandb_project=cli_config.wandb_project,
        wandb_name=cli_config.wandb_name or run_name,
        log_path=log_path,
        eval_every=cli_config.eval_every,
        save_every=cli_config.save_every,
        stream_minibatch_config=None,
    )

    await train.main(cfg)


def main():
    cli_config = chz.entrypoint(CLIConfig)
    asyncio.run(cli_main(cli_config, None))


if __name__ == "__main__":
    main()
