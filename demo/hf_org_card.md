<!-- Paste into https://huggingface.co/organizations/BreakingWeb/settings -> Organization card -->

# BreakingWeb

**Diagnosing web-agent failures with matched clean / intervention tasks.**
Every browser task runs twice — once in a healthy self-hosted web app, once with a controlled, recoverable intervention — so the paired drop tells you *which* capability broke. 519 task pairs, 7 environments, 29 intervention families, 9 evaluated agents plus a 140-task human panel.

- 🌐 Website & results explorer: https://www.breakingweb.app
- 🎮 Live demo (play any task): https://tianchenguan-breakingweb-demo.hf.space
- 💻 Code, tasks, environments, harness: https://github.com/Arvid-pku/WebStress
- 📄 Paper: NeurIPS 2026 Datasets & Benchmarks track (under review)

## Datasets

| Dataset | Contents |
|---|---|
| [primbench-results-v2](https://huggingface.co/datasets/BreakingWeb/primbench-results-v2) | Browser-Use text agents: Gemini 3.1 Pro, Gemini 3 Flash, GPT-5.4, GPT-5.4 mini, Opus 4.7, Qwen3-VL-235B |
| [primbench-results-v3](https://huggingface.co/datasets/BreakingWeb/primbench-results-v3) | Sonnet 4.6, the Opus 4.7 60-step retry pass, and the three pixel-mode agents |

Human-panel annotation data is private. BreakingWeb was previously developed under the working names *PrimBench* and *WebStress*; the `PrimBench` organization holds the original copies of these datasets.
