"""
Proposer Module for LLMOS.
Implements curriculum learning by generating new tasks based on agent performance.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from ..utils.llm_client import LLMClient
from ..utils.validation import validate_instruction

logger = logging.getLogger(__name__)


class Proposer:
    """
    Curriculum Learning Proposer.

    Analyzes agent performance history and proposes new tasks
    that target weak points.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        config_path: Optional[str] = None,
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        """
        Initialize the proposer.

        Args:
            llm_client: LLM client instance.
            config_path: Path to config file.
            model_name: Model to use (overrides config).
            provider: LLM provider to use (overrides config).
        """
        self.llm_client = llm_client or LLMClient(config_path)

        # Load config
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.json"
        with open(config_path, "r") as f:
            config = json.load(f)

        self.proposer_config = config.get("proposer", {})
        self.history_window = self.proposer_config.get("history_window", 10)

        # Get role-specific LLM settings (params override config)
        llm_config = config.get("llm", {})
        role_config = llm_config.get("roles", {}).get("proposer", {})
        self.provider = provider or role_config.get("provider", llm_config.get("default_provider"))
        self.model_name = model_name or role_config.get("model")

        # Load system prompt
        self.system_prompt = self._load_system_prompt()

        # Available templates
        self.templates = self._discover_templates()

    def _load_system_prompt(self) -> str:
        """Load the proposer system prompt."""
        prompt_path = Path(__file__).parent.parent / "prompts" / "proposer.system.md"

        if prompt_path.exists():
            with open(prompt_path, "r") as f:
                return f.read()

        return self._get_default_system_prompt()

    def _get_default_system_prompt(self) -> str:
        """Get the default proposer system prompt."""
        return """You are a curriculum designer for training computer-use agents.

## Your Goal
Analyze the agent's recent performance and propose a new task that will help the agent improve.

## Curriculum Strategy
1. **Start Simple**: Begin with basic tasks if the agent is struggling
2. **Progressive Difficulty**: Increase complexity as the agent succeeds
3. **Target Weaknesses**: Focus on areas where the agent failed
4. **Variety**: Mix different task types to ensure broad capability

## Task Categories
- file_management: Create, move, copy, delete files
- web_navigation: Browse websites, fill forms, search
- form_filling: Complete forms, input data
- text_editing: Edit documents, format text
- app_interaction: Use desktop applications
- multi_step: Tasks requiring multiple sequential actions

## Output Format
Return a JSON object representing a new task instruction:
{
  "task_id": "<unique_id>",
  "instruction": "<clear task description>",
  "initial_state_template": "<template_name>",
  "difficulty": "<easy|medium|hard|expert>",
  "category": "<category>",
  "success_criteria": {
    "type": "state_match",
    "conditions": [...]
  },
  "hints": ["<optional hints>"]
}

## Guidelines
- Make instructions clear and unambiguous
- Set appropriate difficulty based on recent performance
- Include measurable success criteria when possible
- Consider what skills the agent needs to practice
"""

    def _discover_templates(self) -> list[str]:
        """Discover available state templates."""
        templates_dir = Path(__file__).parent.parent / "templates"
        if not templates_dir.exists():
            return ["desktop", "browser"]  # Default templates

        templates = []
        for path in templates_dir.glob("*.json"):
            templates.append(path.stem)

        return templates if templates else ["desktop", "browser"]

    def propose_next_task(
        self,
        history: list[dict],
        constraints: Optional[dict] = None,
    ) -> dict:
        """
        Propose a new task based on performance history.

        Args:
            history: List of past episodes with instruction, score, feedback.
            constraints: Optional constraints for task generation.

        Returns:
            New instruction dict.
        """
        # Analyze history
        analysis = self._analyze_history(history)

        # Build proposal request
        user_message = self._build_proposal_request(analysis, constraints)

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]

        try:
            response = self.llm_client.complete(
                messages=messages,
                provider=self.provider,
                model_name=self.model_name,
                json_mode=True,
            )

            # Ensure task_id is unique
            if "task_id" not in response or not response["task_id"]:
                response["task_id"] = f"task_{uuid.uuid4().hex[:8]}"

            # Max steps is configured globally (config.json), not per task
            response.pop("max_steps", None)

            # Validate instruction
            is_valid, errors = validate_instruction(response)
            if not is_valid:
                logger.warning(f"Invalid instruction proposed: {errors}")
                # Fix common issues
                response = self._fix_instruction(response)

            return response

        except Exception as e:
            logger.error(f"Proposer LLM call failed: {e}")
            return self._fallback_task()

    def _analyze_history(self, history: list[dict]) -> dict:
        """
        Analyze performance history.

        Args:
            history: List of episode summaries.

        Returns:
            Analysis dict with success rate, weak areas, etc.
        """
        if not history:
            return {
                "total_episodes": 0,
                "success_rate": 0.0,
                "average_score": 0.0,
                "weak_categories": [],
                "recent_trend": "unknown",
                "recommendation": "start_simple"
            }

        # Take recent history
        recent = history[-self.history_window:]

        # Calculate metrics
        scores = [ep.get("score", 0) for ep in recent]
        successes = [ep.get("success", False) for ep in recent]

        success_rate = sum(successes) / len(successes) if successes else 0
        avg_score = sum(scores) / len(scores) if scores else 0

        # Identify weak categories
        category_scores = {}
        for ep in recent:
            cat = ep.get("category", "unknown")
            if cat not in category_scores:
                category_scores[cat] = []
            category_scores[cat].append(ep.get("score", 0))

        weak_categories = []
        for cat, cat_scores in category_scores.items():
            if sum(cat_scores) / len(cat_scores) < 0.5:
                weak_categories.append(cat)

        # Determine trend
        if len(scores) >= 3:
            recent_avg = sum(scores[-3:]) / 3
            older_avg = sum(scores[:-3]) / max(len(scores) - 3, 1)
            if recent_avg > older_avg + 0.1:
                trend = "improving"
            elif recent_avg < older_avg - 0.1:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        # Recommendation
        if success_rate > 0.8:
            recommendation = "increase_difficulty"
        elif success_rate < 0.3:
            recommendation = "decrease_difficulty"
        elif weak_categories:
            recommendation = f"focus_on_{weak_categories[0]}"
        else:
            recommendation = "maintain_variety"

        return {
            "total_episodes": len(history),
            "recent_episodes": len(recent),
            "success_rate": success_rate,
            "average_score": avg_score,
            "weak_categories": weak_categories,
            "recent_trend": trend,
            "recommendation": recommendation,
            "recent_failures": [
                ep.get("feedback", "") for ep in recent
                if not ep.get("success", False)
            ][-3:]
        }

    def _build_proposal_request(
        self,
        analysis: dict,
        constraints: Optional[dict],
    ) -> str:
        """Build the proposal request message."""
        parts = []

        parts.append("## Performance Analysis")
        parts.append(f"- Total episodes: {analysis['total_episodes']}")
        parts.append(f"- Success rate: {analysis['success_rate']:.1%}")
        parts.append(f"- Average score: {analysis['average_score']:.2f}")
        parts.append(f"- Trend: {analysis['recent_trend']}")
        parts.append(f"- Recommendation: {analysis['recommendation']}")

        if analysis['weak_categories']:
            parts.append(f"- Weak areas: {', '.join(analysis['weak_categories'])}")

        if analysis.get('recent_failures'):
            parts.append("\n## Recent Failure Feedback")
            for feedback in analysis['recent_failures']:
                if feedback:
                    parts.append(f"- {feedback[:100]}...")

        parts.append(f"\n## Available Templates")
        parts.append(", ".join(self.templates))

        if constraints:
            parts.append("\n## Constraints")
            for key, value in constraints.items():
                parts.append(f"- {key}: {value}")

        parts.append("\nPlease propose a new task that will help the agent improve.")

        return "\n".join(parts)

    def _fix_instruction(self, instruction: dict) -> dict:
        """Fix common issues in generated instructions."""
        # Ensure required fields
        if "task_id" not in instruction:
            instruction["task_id"] = f"task_{uuid.uuid4().hex[:8]}"

        if "instruction" not in instruction:
            instruction["instruction"] = "Complete the task shown on screen."

        if "initial_state_template" not in instruction:
            instruction["initial_state_template"] = "desktop"

        # Validate template exists
        if instruction["initial_state_template"] not in self.templates:
            instruction["initial_state_template"] = self.templates[0] if self.templates else "desktop"

        return instruction

    def _fallback_task(self) -> dict:
        """Generate a simple fallback task."""
        return {
            "task_id": f"fallback_{uuid.uuid4().hex[:8]}",
            "instruction": "Click the start button on the desktop.",
            "initial_state_template": "desktop",
            "difficulty": "easy",
            "category": "app_interaction",
        }

    def propose_batch(
        self,
        history: list[dict],
        count: int = 5,
        variety: bool = True,
    ) -> list[dict]:
        """
        Propose multiple tasks at once.

        Args:
            history: Performance history.
            count: Number of tasks to propose.
            variety: If True, ensure variety in task types.

        Returns:
            List of instruction dicts.
        """
        tasks = []
        categories_used = set()

        for i in range(count):
            constraints = {}
            if variety and categories_used:
                constraints["avoid_categories"] = list(categories_used)

            task = self.propose_next_task(history, constraints)
            tasks.append(task)

            # Track category for variety
            if "category" in task:
                categories_used.add(task["category"])

        return tasks


def create_proposer(config_path: Optional[str] = None) -> Proposer:
    """Create a proposer instance."""
    return Proposer(config_path=config_path)
