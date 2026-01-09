"""
Evaluator interface for determining task success.
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

from .task_provider import Task


@dataclass
class EvalResult:
    """
    Standardized evaluation result.

    Matches the output format of LLMOS Judge for compatibility.
    """
    score: float  # -1.0 (failure) to 1.0 (success)
    success: bool
    reasoning: str
    feedback: str = ""
    error_analysis: dict = field(default_factory=lambda: {
        "error_type": "none",
        "critical_mistake_step": None,
        "suggestion": "",
    })
    partial_credits: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)  # Benchmark-specific data

    def to_dict(self) -> dict:
        """Convert to dict format expected by LLMOS components."""
        return {
            "score": self.score,
            "success": self.success,
            "reasoning": self.reasoning,
            "feedback": self.feedback,
            "error_analysis": self.error_analysis,
            "partial_credits": self.partial_credits,
            **self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EvalResult":
        """Create EvalResult from dict."""
        return cls(
            score=data.get("score", 0.0),
            success=data.get("success", False),
            reasoning=data.get("reasoning", ""),
            feedback=data.get("feedback", ""),
            error_analysis=data.get("error_analysis", {}),
            partial_credits=data.get("partial_credits", []),
            extra={k: v for k, v in data.items() if k not in {
                "score", "success", "reasoning", "feedback",
                "error_analysis", "partial_credits"
            }},
        )

    @classmethod
    def success_result(cls, reasoning: str = "Task completed successfully") -> "EvalResult":
        """Create a successful result."""
        return cls(score=1.0, success=True, reasoning=reasoning)

    @classmethod
    def failure_result(cls, reasoning: str, error_type: str = "incomplete") -> "EvalResult":
        """Create a failure result."""
        return cls(
            score=-1.0,
            success=False,
            reasoning=reasoning,
            error_analysis={"error_type": error_type, "critical_mistake_step": None, "suggestion": ""},
        )

    @classmethod
    def partial_result(cls, score: float, reasoning: str) -> "EvalResult":
        """Create a partial success result."""
        return cls(
            score=score,
            success=score > 0.5,
            reasoning=reasoning,
        )


@runtime_checkable
class Evaluator(Protocol):
    """
    Protocol for evaluating task completion.

    Implementations:
    - LLMEvaluator: Use LLM to evaluate (current LLMOS Judge behavior)
    - HeuristicEvaluator: Rule-based evaluation
    - BenchmarkEvaluator: Use benchmark's ground-truth validator
    - CompositeEvaluator: Chain multiple evaluators
    """

    async def evaluate(
        self,
        task: Task,
        final_state: dict,
        history: list[dict],
        initial_state: Optional[dict] = None,
        **kwargs: Any,
    ) -> EvalResult:
        """
        Evaluate whether the task was completed successfully.

        Args:
            task: The task that was attempted.
            final_state: Final state after episode.
            history: List of action history entries.
            initial_state: Initial state (optional, for comparison).
            **kwargs: Additional evaluator-specific arguments.

        Returns:
            EvalResult with score, success, reasoning, etc.
        """
        ...

    def priority(self) -> int:
        """
        Return execution priority (lower = runs first).

        Used by CompositeEvaluator to order evaluators.
        """
        ...


class JudgeEvaluator:
    """
    Evaluator that wraps the existing LLMOS Judge.

    Provides backwards compatibility with the current evaluation system.
    """

    def __init__(self, judge: Any = None, config_path: Optional[str] = None):
        """
        Initialize with an LLMOS Judge instance.

        Args:
            judge: Existing Judge instance, or None to create new one.
            config_path: Config path for creating new Judge.
        """
        if judge is None:
            from ..core.judge import Judge
            judge = Judge(config_path=config_path)
        self.judge = judge

    async def evaluate(
        self,
        task: Task,
        final_state: dict,
        history: list[dict],
        initial_state: Optional[dict] = None,
        **kwargs: Any,
    ) -> EvalResult:
        """Evaluate using LLMOS Judge."""
        # Convert Task to dict format expected by Judge
        instruction = task.to_dict()

        # Judge.evaluate is sync, but we're in async context
        result = self.judge.evaluate(
            instruction=instruction,
            final_state=final_state,
            history=history,
            initial_state=initial_state,
        )

        return EvalResult.from_dict(result)

    def priority(self) -> int:
        return 100  # Low priority - run after faster evaluators


class CompositeEvaluator:
    """
    Evaluator that chains multiple evaluators.

    Runs evaluators in priority order and returns the first definitive result.
    """

    def __init__(self, evaluators: list[Evaluator]):
        """
        Initialize with a list of evaluators.

        Args:
            evaluators: List of Evaluator instances.
        """
        self.evaluators = sorted(evaluators, key=lambda e: e.priority())

    async def evaluate(
        self,
        task: Task,
        final_state: dict,
        history: list[dict],
        initial_state: Optional[dict] = None,
        **kwargs: Any,
    ) -> EvalResult:
        """Run evaluators in priority order."""
        for evaluator in self.evaluators:
            try:
                result = await evaluator.evaluate(
                    task, final_state, history, initial_state, **kwargs
                )
                # Return first definitive result
                if result is not None:
                    return result
            except Exception as e:
                # Log and continue to next evaluator
                import logging
                logging.warning(f"Evaluator {evaluator} failed: {e}")
                continue

        # Fallback
        return EvalResult(
            score=0.0,
            success=False,
            reasoning="No evaluator could determine outcome",
        )

    def priority(self) -> int:
        return min(e.priority() for e in self.evaluators) if self.evaluators else 0