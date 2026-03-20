#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p results/llmos/logs
mkdir -p results/llmos/training
mkdir -p results/webagentbench/archive
mkdir -p llmos/runs/archive
mkdir -p llmos/runs/current

move_if_exists() {
  local src="$1"
  local dst_dir="$2"
  if [[ -e "$src" ]]; then
    mv -n "$src" "$dst_dir"/
    echo "moved: $src -> $dst_dir/"
  fi
}

shopt -s nullglob

# Root collection logs.
for file in collect_*.log collect_v*.log; do
  move_if_exists "$file" "results/llmos/logs"
done

# Root WebAgentBench result dumps.
for file in results_*.json; do
  move_if_exists "$file" "results/webagentbench/archive"
done

# Root exported training data.
for file in training_data*.jsonl; do
  move_if_exists "$file" "results/llmos/training"
done

# Archive old versioned LLMOS run directories.
for dir in llmos/runs_v*; do
  if [[ -d "$dir" ]]; then
    mv -n "$dir" llmos/runs/archive/
    echo "moved: $dir -> llmos/runs/archive/"
  fi
done

# Move flat run artifacts into llmos/runs/current.
for file in llmos/runs/*; do
  if [[ -f "$file" ]]; then
    mv -n "$file" llmos/runs/current/
    echo "moved: $file -> llmos/runs/current/"
  fi
done

echo "Organization complete."
