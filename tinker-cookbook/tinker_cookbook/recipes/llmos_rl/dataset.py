from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Sequence

import chz

from tinker_cookbook.recipes.llmos_rl.env import LLMOSEnvGroupBuilder, LLMOSEnvOptions
from tinker_cookbook.rl.types import EnvGroupBuilder, RLDataset, RLDatasetBuilder


def _load_instruction_objects(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Instruction file not found: {path}")
    if path.suffix.lower() == ".jsonl":
        rows: list[dict] = []
        with path.open("r", encoding="utf-8") as handle:
            for ln in handle:
                ln = (ln or "").strip()
                if not ln:
                    continue
                try:
                    obj = json.loads(ln)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON on line {len(rows)+1} of {path}: {exc}") from exc
                if isinstance(obj, dict):
                    rows.append(obj)
        return rows
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return [obj for obj in payload if isinstance(obj, dict)]
    if isinstance(payload, dict):
        # Some instruction dumps store the actual task object under well-known keys.
        if "instructions" in payload and isinstance(payload["instructions"], list):
            return [obj for obj in payload["instructions"] if isinstance(obj, dict)]
        # If the object itself looks like an instruction, treat it as a singleton list.
        return [payload]
    raise ValueError(f"Unsupported instruction file structure for {path}")


class LLMOSInstructionDataset(RLDataset):
    def __init__(
        self,
        rows: list[dict],
        groups_per_batch: int,
        total_batches: int,
        env_options: LLMOSEnvOptions,
    ):
        if not rows:
            raise ValueError("LLMOSInstructionDataset requires at least one instruction row")
        if total_batches <= 0:
            raise ValueError("total_batches must be positive")
        self.rows = rows
        self.groups_per_batch = groups_per_batch
        self.total_batches = total_batches
        self.env_options = env_options

    def __len__(self) -> int:
        return self.total_batches

    def get_batch(self, index: int) -> Sequence[EnvGroupBuilder]:
        builders: list[EnvGroupBuilder] = []
        row_count = len(self.rows)
        for offset in range(self.groups_per_batch):
            row_idx = (index * self.groups_per_batch + offset) % row_count
            seed_offset = index * self.groups_per_batch + offset
            row = self.rows[row_idx]
            builders.append(
                LLMOSEnvGroupBuilder(
                    instruction=row["instruction"],
                    seed=row["seed"] + seed_offset,
                    fidelity=row["fidelity"],
                    max_steps=row["max_steps"],
                    agent_history=row["agent_history"],
                    sim_feature_config=row.get("sim_feature_config"),
                    options=self.env_options,
                )
            )
        return builders


@chz.chz
class LLMOSInstructionDatasetBuilder(RLDatasetBuilder):
    instruction_path: str
    groups_per_batch: int = 8
    default_seed: int = 0
    default_fidelity: str = "low"
    default_max_steps: int = 8
    agent_history: int = 4
    dataset_n: int = -1
    dataset_seed: int | None = None
    shuffle: bool = True
    sim_feature_config: Dict[str, Any] | None = None
    env_options: LLMOSEnvOptions | None = None
    max_batches: int | None = None

    async def __call__(self) -> tuple[RLDataset, RLDataset | None]:
        path = Path(self.instruction_path)
        raw = _load_instruction_objects(path)
        if not raw:
            raise RuntimeError(f"No instructions found in {path}")
        rows = self._materialize_rows(raw)
        if self.env_options is None:
            raise RuntimeError("LLMOSEnvOptions must be provided to build the dataset")
        batches_per_epoch = max(1, math.ceil(len(rows) / self.groups_per_batch))
        total_batches = (
            self.max_batches if isinstance(self.max_batches, int) and self.max_batches > 0 else batches_per_epoch
        )
        dataset = LLMOSInstructionDataset(rows, self.groups_per_batch, total_batches, self.env_options)
        return dataset, None

    def _materialize_rows(self, instructions: list[dict]) -> list[dict]:
        dataset = list(instructions)
        if self.dataset_seed is not None:
            rng = random.Random(self.dataset_seed)
            rng.shuffle(dataset)
        elif self.shuffle:
            random.shuffle(dataset)
        if self.dataset_n and self.dataset_n > 0:
            dataset = dataset[: self.dataset_n]
        rng = random.Random(self.default_seed)
        rows: list[dict] = []
        for idx, instruction in enumerate(dataset):
            if not isinstance(instruction, dict):
                continue
            seed = int(instruction.get("seed", rng.randint(0, 2**31 - 1)))
            fidelity = str(instruction.get("fidelity", self.default_fidelity))
            max_steps = int(instruction.get("max_steps", self.default_max_steps))
            rows.append(
                {
                    "instruction": instruction,
                    "seed": seed,
                    "fidelity": fidelity,
                    "max_steps": max_steps,
                    "agent_history": self.agent_history,
                    "sim_feature_config": instruction.get("sim_feature_config", self.sim_feature_config),
                }
            )
        return rows
