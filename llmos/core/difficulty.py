"""
Simulator Difficulty Configuration for LLMOS.
Defines curriculum-based difficulty modes for training agents.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class DifficultyConfig:
    """Configuration for simulator difficulty."""
    information_density: str = "simple"  # simple, moderate, rich
    signal_noise_ratio: str = "clean"    # clean, moderate, noisy
    determinism: str = "idealized"       # idealized, moderate, hostile
    preset: str = "easy"                 # easy, medium, hard, expert, custom


# Preset configurations
DIFFICULTY_PRESETS = {
    "easy": DifficultyConfig(
        information_density="simple",
        signal_noise_ratio="clean",
        determinism="idealized",
        preset="easy",
    ),
    "medium": DifficultyConfig(
        information_density="moderate",
        signal_noise_ratio="clean",
        determinism="moderate",
        preset="medium",
    ),
    "hard": DifficultyConfig(
        information_density="rich",
        signal_noise_ratio="moderate",
        determinism="moderate",
        preset="hard",
    ),
    "expert": DifficultyConfig(
        information_density="rich",
        signal_noise_ratio="noisy",
        determinism="hostile",
        preset="expert",
    ),
}


# Prompt modifiers for each dimension
INFORMATION_DENSITY_PROMPTS = {
    "simple": """
## Information Density: SIMPLE (Abstracted)
- Show only information relevant to the user's intent
- Hide hidden files (dotfiles like .bashrc, .cache, .config) unless explicitly requested
- Summarize verbose outputs into key information
- Omit metadata like permissions, timestamps, inodes unless relevant
- Present clean, focused UI states without clutter
""",
    "moderate": """
## Information Density: MODERATE (Balanced)
- Show relevant information plus some context
- Include commonly accessed hidden files if they might be relevant
- Show moderate detail in outputs (first few lines of files, key metadata)
- Include basic metadata when useful (file sizes, modification times)
- Present UI with standard detail level
""",
    "rich": """
## Information Density: RICH (Raw Reality)
- Show full raw output without summarization
- Include ALL files including hidden dotfiles (.bashrc, .cache, .config, .git, etc.)
- Show verbose metadata: permissions, timestamps, inodes, ownership
- Include system processes and background tasks in state
- Present UI with full detail including invisible elements, z-indices, overflow states
- Show environment variables, shell state, and process context
""",
}


SIGNAL_NOISE_PROMPTS = {
    "clean": """
## Signal-to-Noise: CLEAN (Perfect Formatting)
- All text is perfectly formatted (valid JSON, aligned tables, proper indentation)
- Clear separation between stdout and stderr
- No encoding errors or special characters
- Consistent line endings and spacing
- UI elements have clean, predictable structure
""",
    "moderate": """
## Signal-to-Noise: MODERATE (Realistic)
- Mostly clean output with occasional formatting quirks
- stdout and stderr may occasionally interleave
- Some outputs may have trailing whitespace or inconsistent indentation
- Occasional warning messages mixed with output
- UI may have minor rendering inconsistencies
""",
    "noisy": """
## Signal-to-Noise: NOISY (Dirty/Raw)
- Include raw ANSI escape codes in terminal output (e.g., \\033[0;31m for colors)
- stdout and stderr interleaved due to race conditions
- Outputs may have broken formatting, line wrapping issues, or truncation
- Include progress bars, spinners, and cursor control sequences
- May include "garbled" text simulating encoding issues or buffer corruption
- UI may have overlapping elements, broken layouts, or rendering artifacts
- Include debug output, deprecation warnings, and verbose logging
""",
}


DETERMINISM_PROMPTS = {
    "idealized": """
## System Determinism: IDEALIZED (Perfect)
- Commands always succeed if syntactically correct
- Instant execution with no delays
- Resources are always available
- Network is always connected and fast
- Files are always accessible with correct permissions
- No race conditions or timing issues
""",
    "moderate": """
## System Determinism: MODERATE (Realistic)
- Most commands succeed, but some may have warnings
- Occasional "file not found" for edge cases
- Some operations may take time (show progress)
- Network may have minor latency
- Permissions are enforced realistically
- May encounter "file in use" or similar transient issues
- Do not "teleport" through complex workflows; require prerequisite UI steps and explicit submissions before success
""",
    "hostile": """
## System Determinism: HOSTILE (Chaotic)
- Simulate real-world flakiness and failures:
  * "Resource temporarily unavailable" errors
  * Network timeouts and connection resets
  * "Permission denied" for some operations
  * "Disk quota exceeded" or "No space left on device"
  * Partial file writes or corrupted saves
  * Version mismatch warnings
  * "Too many open files" errors
  * Process killed by OOM killer
  * Stale NFS file handles
- Commands may fail intermittently even if correct
- Race conditions between concurrent operations
- System may be "slow" (operations take multiple ticks)
- Background processes may interfere with user operations
- Strongly avoid shortcutting: complex tasks often require additional confirmations, retries, or missing-info prompts
""",
}


def get_difficulty_config(
    preset: Optional[str] = None,
    information_density: Optional[str] = None,
    signal_noise_ratio: Optional[str] = None,
    determinism: Optional[str] = None,
) -> DifficultyConfig:
    """
    Get a difficulty configuration.

    Args:
        preset: Use a preset ("easy", "medium", "hard", "expert").
        information_density: Override information density setting.
        signal_noise_ratio: Override signal-to-noise setting.
        determinism: Override determinism setting.

    Returns:
        DifficultyConfig with the specified settings.
    """
    if preset and preset != "custom":
        config = DIFFICULTY_PRESETS.get(preset, DIFFICULTY_PRESETS["easy"])
        # Create a new instance to allow overrides
        config = DifficultyConfig(
            information_density=config.information_density,
            signal_noise_ratio=config.signal_noise_ratio,
            determinism=config.determinism,
            preset=preset,
        )
    else:
        config = DifficultyConfig(preset="custom")

    # Apply overrides
    if information_density:
        config.information_density = information_density
    if signal_noise_ratio:
        config.signal_noise_ratio = signal_noise_ratio
    if determinism:
        config.determinism = determinism

    return config


def build_difficulty_prompt(config: DifficultyConfig) -> str:
    """
    Build the difficulty-specific prompt section.

    Args:
        config: The difficulty configuration.

    Returns:
        Prompt string with difficulty instructions.
    """
    parts = [
        "\n# IMPORTANT (Applies to all difficulty modes)\n"
        "- Your outer response must always be valid JSON (no markdown/code fences).\n"
        "- Any simulated noise (ANSI codes, garbling, interleaving) applies only inside simulated content fields (e.g., terminal output, file contents, UI text), not the wrapper JSON.\n",
        f"\n# DIFFICULTY MODE: {config.preset.upper()}\n",
        INFORMATION_DENSITY_PROMPTS.get(config.information_density, ""),
        SIGNAL_NOISE_PROMPTS.get(config.signal_noise_ratio, ""),
        DETERMINISM_PROMPTS.get(config.determinism, ""),
    ]

    return "\n".join(parts)


def get_difficulty_from_dict(d: dict) -> DifficultyConfig:
    """
    Create a DifficultyConfig from a dictionary.

    Args:
        d: Dictionary with difficulty settings.

    Returns:
        DifficultyConfig instance.
    """
    return get_difficulty_config(
        preset=d.get("preset"),
        information_density=d.get("information_density"),
        signal_noise_ratio=d.get("signal_noise_ratio"),
        determinism=d.get("determinism"),
    )
