"""
Adversarial Module: Simulator that creates realistic obstacles for agents.

Modes:
- NONE: No adversarial behavior (baseline)
- SUBTLE: Realistic obstacles (popups, validation, timeouts)
- DECEPTIVE: Ambiguous UI (similar buttons, misleading labels)
- HOSTILE: Active interference (redirects, content changes, session expiry)
- PRIMITIVE_TARGETED: Challenge specific agent primitives (backtracking,
  reflection, verification, etc.) to diagnose capability gaps

The key constraint: every obstacle must be realistic and explainable.
"""

from dataclasses import dataclass, field
from typing import Optional

from ...core.modules.enums import AdversarialMode, AdversarialPrimitive
from .base import (
    Module,
    BasePromptBlock,
    PromptBlock,
)


# =============================================================================
# Severity-based Prompt Blocks (existing)
# =============================================================================

NONE_ADVERSARIAL_PROMPT = """
## Adversarial Mode: None

Simulate normally without intentional obstacles.
"""

SUBTLE_ADVERSARIAL_PROMPT = """
## Adversarial Mode: Subtle Obstacles

Create ONE realistic obstacle per step. Agent should not detect intentional sabotage.

**Form/Input:** Validation error on valid input, field cleared by autofill, focus stolen by chat widget, format mismatch, silent truncation
**UI Blocking:** Popup/modal (cookie consent, newsletter), confirmation dialog, CAPTCHA, terms checkbox, notification permission
**Navigation:** Target requires scrolling, collapsed section, tab switch, pagination, infinite scroll
**Loading/Timing:** Extended loading spinner, partial load, lazy-load element, skeleton placeholder
**State:** Dirty form warning, undo prompt with timeout, auto-save conflict, draft recovery dialog

Rules: One obstacle per step. Must be explainable as normal behavior. After 2-3 fails, let agent proceed. Vary types.
Output: "Obstacle: [type] - [justification]"
"""

DECEPTIVE_ADVERSARIAL_PROMPT = """
## Adversarial Mode: Deceptive UI

Create AMBIGUOUS situations that mislead the agent. Make the "wrong" choice appear more attractive.

**Duplicates/Similar:** Similar buttons nearby ("Submit" vs "Submit for Review"), near-identical list names, multiple forms, icon confusion
**Misleading Labels:** Inverted meaning ("Continue" goes back), ambiguous "OK", technical jargon, abbreviated labels
**Decoys:** Fake download button (ad-styled), sponsored results as organic, prominent upsell over free option, pre-checked newsletter
**Visual Deception:** Correct option hidden (needs hover/expand), swapped positions, disabled-looking correct target, wrong size hierarchy
**State-Based:** Phantom selection (appears selected but isn't), stale highlighting, cached/partial UI updates
**Dark Patterns:** Confirm-shaming, roach motel (easy in, hard out), misdirection, double-negative checkboxes

Rules: Correct path must always EXIST. Don't make it impossible, just confusing. Vary tricks.
Output: "Deception: [type] - [how it misleads]"
"""

HOSTILE_ADVERSARIAL_PROMPT = """
## Adversarial Mode: Hostile Environment

ACTIVELY interfere with agent progress using realistic system behaviors. Force recovery and retry.

**Session/Auth:** Session timeout to login page, sudden permission denied, token refresh, unexpected MFA, account locked, SSO redirect
**Network:** Connection lost on submit (data ambiguous), request timeout, 502/503, DNS failure, SSL error, retry storm
**Data/State Loss:** Page refresh loses form data, form reset on validation fail, draft lost, concurrent edit conflict, version mismatch
**Redirects:** Forced logout redirect, broken deep links (404), maintenance mode, feature flag off, A/B test layout change
**Rate/Resource Limits:** Rate limiting, quota exceeded, upload size limit, storage full, concurrent session limit
**Content Changes:** Target element changes/removed/disabled mid-task, list reordered, search results refreshed
**Process Interruption:** Mandatory update, terms changed, survey intercept, feedback modal, announcement banner

Rules: ALWAYS provide recovery path. Don't repeat same tactic consecutively. Track count in hidden_state._adversarial_count. After 3 hostile actions, reduce intensity for 2 steps. Agent should eventually succeed.
Output: "Hostile: [type] - [recovery path available]"
"""


# =============================================================================
# Per-Primitive Prompt Blocks
# =============================================================================

PRIMITIVE_PROMPTS: dict[str, str] = {
    AdversarialPrimitive.REFLECTION.value: """\
#### reflection
Test ability to critically evaluate own actions and recognize mistakes.
- **Fake success signals**: Show "Success!" toast but operation actually failed (error hidden in secondary panel)
- **Contradictory secondary UI**: Status bar contradicts main content ("Cart: 0 items" vs "Item added")
- **Silent regression**: Quietly revert part of state after success (checkbox unchecks via "auto-save conflict")
- **Misleading progress indicators**: Progress at 100% or "Complete" badge while required fields empty
- **Partial application**: Apply only some requested changes (fill 2 of 3 fields)
Recovery: Correct state always discoverable by reading actual UI elements.""",

    AdversarialPrimitive.VERIFICATION.value: """\
#### verification
Test ability to confirm outcomes match expectations before moving on.
- **False positive feedback**: "Saved successfully" but data not persisted (reverts on refresh)
- **Subtle state inconsistencies**: Displayed value differs from entered (whitespace stripped, date reformatted, currency rounded)
- **Off-by-one in lists**: Select item N but N-1 or N+1 actually selected (elements shifted by "live update")
- **Stale confirmation dialog**: Confirmation shown for PREVIOUS action, not current one
- **Hidden validation errors**: Validation error in collapsed section or below the fold
- **Async save failure**: Optimistic "Saving..." UI, then quietly show small error icon
Recovery: Ground truth always present in actual DOM state.""",

    AdversarialPrimitive.BACKTRACKING.value: """\
#### backtracking
Test ability to recognize dead ends and revert to earlier states.
- **Semantic dead-end**: Agent navigates deep into wrong path; target only exists under different path. Must use back/breadcrumb.
- **Wizard lock-out**: Early selection disables required option on later step ("Requires Pro Plan"). Must go back and choose differently.
- **Missing prerequisite reveal**: Submit error reveals prerequisite on different page (e.g., enable 2FA first). Must navigate away and return.
- **Cascading undo**: System reverts step A after step B completed; both must be redone in order.
- **False shortcut**: Prominent "Skip to end" leads to incomplete config missing required fields. Must go back to full flow.
Recovery: Back buttons, breadcrumbs, and navigation always provide path to previous decision points.""",

    AdversarialPrimitive.EXPLORATION.value: """\
#### exploration
Test ability to discover non-obvious paths to achieve goal.
- **Hidden in accordion/collapsible**: Target inside collapsed "Advanced Options" section with no strong hint.
- **Pagination depth**: Target on page 3+ of paginated list; must navigate pages or use search/filter.
- **Hamburger/overflow menu**: Target behind three-dot overflow or hamburger menu, not in main toolbar.
- **Nested tab navigation**: Target behind two levels of tabs (Settings > Notifications > Email Preferences).
- **Search-required discovery**: Target among 50+ items; must use search bar or filter controls.
- **Contextual menu only**: Target only available via right-click context menu, not in any toolbar.
Recovery: Target always reachable through standard UI interactions. Multiple discovery paths exist.""",

    AdversarialPrimitive.PLANNING.value: """\
#### planning
Test ability to sequence actions correctly toward a multi-step goal.
- **Order dependency with misleading UI**: UI allows step B before step A; attempting B gives confusing error instead of stating prerequisite.
- **Information gathering first**: Must visit different page to look up required value before filling form; guessing fails validation.
- **Parallel prerequisites**: Two independent steps must both complete before step C becomes available (vague "Complete all prerequisites").
- **Trap of premature submission**: Prominent Submit visible but required sections in other tabs/below fold. Early submit shows "N fields missing."
- **Resource allocation sequencing**: Resource pool empty; must navigate to provisioning first, then return to complete assignment.
Recovery: Error messages and UI states provide enough info to deduce correct sequence.""",

    AdversarialPrimitive.MEMORY.value: """\
#### memory
Test ability to retain and use information from earlier in the episode.
- **Cross-page value recall**: Display confirmation number in dismissible dialog; require entering it on different page steps later.
- **Context switch and return**: Mandatory interruption clears form; agent must remember and re-fill values from memory.
- **Detail-based selection**: Show data table on page A; require selection based on those details on page B.
- **Instruction retention**: Show specific instruction in banner, remove after first action; agent must apply it later without reminder.
- **Running total tracking**: Track cumulative value across sub-tasks; final step requires entering correct total.
Recovery: Information always accessible by navigating back, or was prominently displayed long enough to process.""",

    AdversarialPrimitive.PATIENCE.value: """\
#### patience
Test ability to wait for async operations and avoid premature actions.
- **Extended loading state**: Show spinner for 2-3 ticks; clicking during shows "Please wait." Must issue noop/wait.
- **Progressive loading**: Page loads in stages; target only appears in final stage. Premature interaction gets "Element not yet available."
- **Retry after cooldown**: First two attempts fail with "Rate limited." Only succeeds after issuing noop (wait).
- **Queue processing**: Progress bar across multiple steps; "Continue" only clickable at 100%.
- **Delayed confirmation**: Multi-step save ("Saving..." → "Syncing..." → "Saved"). Navigating away early loses save.
Recovery: Operations complete when agent waits required steps. Premature actions safely rejected.""",

    AdversarialPrimitive.ERROR_RECOVERY.value: """\
#### error_recovery
Test ability to recover from unexpected errors gracefully.
- **Transient server error**: "500 Internal Server Error" modal; retrying same action succeeds. Must dismiss and retry.
- **Validation error with correction**: Specific field errors on submit; must read, correct specific fields, resubmit (not restart).
- **Session interruption**: "Session expired" modal mid-task; after re-auth, form data lost. Must re-enter.
- **Partial failure**: Bulk op: "3 of 5 saved, 2 failed." Must identify failures, resolve conflicts, retry only failed items.
- **Network timeout with ambiguous state**: "Request timed out." Must check if submission went through before retrying.
- **Cascading error**: Error in one field invalidates related field; must fix root cause, not symptom.
Recovery: Every error has clear recovery path. System never enters unrecoverable state.""",

    AdversarialPrimitive.CONSTRAINT_SATISFACTION.value: """\
#### constraint_satisfaction
Test ability to satisfy multiple simultaneous requirements.
- **Interdependent form fields**: Selecting option reveals/changes required fields; fixing one may invalidate another.
- **Budget/resource limits**: Must find valid combination within budget; obvious choices exceed limit.
- **Mid-task constraint addition**: New constraint appears after selections made ("Items over $100 require approval"). Must adjust without restarting.
- **Mutually exclusive options**: Two options can't combine; UI allows selecting both but errors on submit. Must deselect one.
- **Cross-form validation**: Value on page 1 limits options on page 3; error only on page 3, must go back.
- **Dynamic constraint tightening**: Constraints get stricter as form fills (venue limits available dates). Must re-check earlier fields.
Recovery: Valid combination always exists. Error messages indicate violated constraints.""",

    AdversarialPrimitive.ADVERSARIAL_ROBUSTNESS.value: """\
#### adversarial_robustness
Test resistance to intentionally misleading UI patterns.
- **Confirm-shaming**: Cancel option phrased as "No thanks, I don't want to save money." Must select it to decline unwanted subscription.
- **Double-negative checkboxes**: "Uncheck to not opt out of receiving no communications." Must parse logic correctly.
- **Decoy prominence**: Correct "Submit" is small/grey; large colorful "Upgrade to Pro" positioned where submit expected. Must read labels.
- **Misleading icons**: Trash icon means "Archive", download means "Share". Must read tooltips/labels, not assume icon meaning.
- **Pre-checked unwanted options**: Newsletter, data sharing checkboxes pre-checked. Must uncheck irrelevant options before submit.
- **Fake urgency/scarcity**: "Only 2 left!" or "Expires in 5 minutes!" banners. Must ignore urgency and complete task methodically.
Recovery: Correct action always identifiable by carefully reading element text and labels.""",

    AdversarialPrimitive.ATTENTION_FOCUS.value: """\
#### attention_focus
Test ability to maintain focus on primary task amid distractions.
- **Notification popup**: Prominent chat/notification popup overlays workspace; irrelevant to task. Must dismiss or ignore.
- **Competing calls-to-action**: Multiple large colorful buttons alongside small plain text link needed for task. Must identify task-relevant element.
- **Mid-task advertisement**: Full-page interstitial with prominent "Learn More" and tiny "Skip" link. Must find and click "Skip."
- **Badge/counter distraction**: Red notification badge on unrelated nav item. Must resist investigating and stay on task.
- **Dynamic content insertion**: New banner inserted above form, pushing elements down. Must re-locate at new positions.
- **Visual emphasis swap**: Target element de-emphasized while irrelevant element made prominent. Must track by identity (bid/label).
Recovery: Correct target remains present and functional. Distractions dismissible or ignorable.""",

    AdversarialPrimitive.SPATIAL_REASONING.value: """\
#### spatial_reasoning
Test ability to understand UI layout and spatial relationships.
- **Unconventional button placement**: Primary action in footer, sidebar, or floating panel instead of expected position. Must scan full layout.
- **Ambiguous containment**: Adjacent panels each have "Delete" button; must determine which belongs to which via DOM hierarchy.
- **Scrollable container mismatch**: Target in scrollable sub-container; main page scroll doesn't reveal it. Must scroll inner container.
- **Overlapping elements**: Dropdown/modal/tooltip overlaps target; must dismiss overlay first.
- **Split-view layout**: Info split across side-by-side panels; must correlate across panels (select left, act on right).
- **Responsive layout shift**: Elements wrap/stack at current width; must find target at actual wrapped position.
Recovery: Target always exists and is interactable at its actual position.""",
}


def _build_primitive_targeted_prompt(target_primitives: list[str]) -> str:
    """Build the master prompt for primitive-targeted adversarial mode.

    Args:
        target_primitives: List of primitive names to include. If empty, all
            12 primitives are included.

    Returns:
        Complete prompt string.
    """
    if not target_primitives:
        primitives_to_include = list(PRIMITIVE_PROMPTS.keys())
    else:
        primitives_to_include = [p for p in target_primitives if p in PRIMITIVE_PROMPTS]

    primitive_descriptions = "\n\n".join(
        PRIMITIVE_PROMPTS[p] for p in primitives_to_include
    )

    return f"""\
## Adversarial Mode: Primitive-Targeted

Challenge specific agent capabilities through **multi-step arcs**. Each arc develops
ONE primitive across 2-4 consecutive steps to create meaningful impact.

**Arc phases:**
- **setup** (1-2 steps): Create conditions that will test the primitive (e.g., for memory: display key info in a dismissible dialog; for patience: start a loading sequence; for planning: reveal a prerequisite dependency)
- **challenge** (1-2 steps): Activate the obstacle that exercises the primitive, leveraging the setup
- **rest** (1-2 steps): After an arc completes, simulate normally — no obstacle. This gives the agent space to progress before the next arc.

You MUST include in your JSON response:
- `"adversarial_primitive": "<primitive_name>"` — the active primitive (use `"none"` during rest steps)
- `"adversarial_phase": "setup"|"challenge"|"rest"` — current phase

### Available Primitives

{primitive_descriptions}

### Rules
- Develop each primitive across 2-4 steps — do NOT pick a new primitive every step
- Setup steps may look like normal simulation but plant seeds for the coming challenge
- During rest steps between arcs, simulate normally without obstacles
- Choose a DIFFERENT primitive for each new arc
- All obstacles must be explainable as realistic system/UI behavior
- Always provide a realistic recovery path
"""


class NoneAdversarialBlock(BasePromptBlock):
    """Prompt block for no adversarial behavior."""

    def __init__(self):
        super().__init__("none_adversarial", NONE_ADVERSARIAL_PROMPT)


class SubtleAdversarialBlock(BasePromptBlock):
    """Prompt block for subtle obstacles."""

    def __init__(self):
        super().__init__("subtle_adversarial", SUBTLE_ADVERSARIAL_PROMPT)


class DeceptiveAdversarialBlock(BasePromptBlock):
    """Prompt block for deceptive UI."""

    def __init__(self):
        super().__init__("deceptive_adversarial", DECEPTIVE_ADVERSARIAL_PROMPT)


class HostileAdversarialBlock(BasePromptBlock):
    """Prompt block for hostile environment."""

    def __init__(self):
        super().__init__("hostile_adversarial", HOSTILE_ADVERSARIAL_PROMPT)


class PrimitiveTargetedBlock(BasePromptBlock):
    """Prompt block for primitive-targeted adversarial mode.

    When target_primitives is empty, all 12 primitives are included so the
    simulator can choose freely. When non-empty, only the specified
    primitives are injected.
    """

    def __init__(self, target_primitives: Optional[list[str]] = None):
        self._target_primitives = target_primitives or []
        prompt = _build_primitive_targeted_prompt(self._target_primitives)
        super().__init__("primitive_targeted_adversarial", prompt)


# =============================================================================
# Adversarial State Tracker
# =============================================================================

class AdversarialTracker:
    """
    Tracks adversarial actions to prevent infinite loops and manage intensity.

    Used by the simulator to:
    - Avoid repeating the same obstacle
    - Back off after multiple consecutive obstacles
    - Track agent's struggle points for analysis
    - Track per-primitive success/failure for curriculum learning
    """

    def __init__(self, max_consecutive: int = 3, cooldown_steps: int = 2):
        self.max_consecutive = max_consecutive
        self.cooldown_steps = cooldown_steps
        self._obstacle_count = 0
        self._cooldown_remaining = 0
        self._history: list[dict] = []
        self._last_tactic: Optional[str] = None
        # Primitive arc tracking
        self._current_primitive: Optional[str] = None
        self._primitive_step_count: int = 0
        self._current_phase: Optional[str] = None
        self._setup_steps: int = 0  # how many steps were "setup" in current arc
        self._challenge_steps: int = 0  # how many steps were "challenge"
        self._rest_step_count: int = 0  # consecutive rest steps
        self._completed_primitives: list[str] = []  # primitives already used

    @staticmethod
    def detect_obstacle_from_events(events: list) -> tuple[bool, "str | None"]:
        """Detect if an obstacle was applied based on event strings.

        Returns (obstacle_detected, tactic_category).
        """
        for event in events:
            if not isinstance(event, str):
                continue
            ev_lower = event.lower()
            if "hostile:" in ev_lower or "obstacle:" in ev_lower or "deception:" in ev_lower:
                # Extract category: "Hostile: Session Timeout - ..." → "session_timeout"
                parts = event.split(":", 1)
                if len(parts) > 1:
                    tactic = parts[1].split("-")[0].strip().lower().replace(" ", "_")
                    return True, tactic
                return True, "unknown"
        return False, None

    def should_apply_obstacle(self) -> bool:
        """Check if we should apply an obstacle this step."""
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            return False
        return True

    def record_obstacle(
        self,
        tactic: str,
        target: str,
        success: bool,
        primitive: Optional[str] = None,
    ) -> None:
        """Record an obstacle application.

        Args:
            tactic: The obstacle tactic used.
            target: What the obstacle targeted.
            success: Whether the agent overcame the obstacle.
            primitive: Optional primitive name (for primitive-targeted mode).
        """
        entry = {
            "tactic": tactic,
            "target": target,
            "agent_succeeded": success,
            "step": len(self._history),
        }
        if primitive is not None:
            entry["primitive"] = primitive
        self._history.append(entry)
        self._last_tactic = tactic
        self._obstacle_count += 1

        # Enter cooldown after max consecutive obstacles
        if self._obstacle_count >= self.max_consecutive:
            self._cooldown_remaining = self.cooldown_steps
            self._obstacle_count = 0

    def record_success(self) -> None:
        """Record that agent succeeded (reset counter)."""
        self._obstacle_count = 0

    def get_last_tactic(self) -> Optional[str]:
        """Get the last tactic used (to avoid repetition)."""
        return self._last_tactic

    def record_primitive_step(self, primitive: str, phase: str) -> None:
        """Record a step in a primitive arc.

        If the primitive matches the current arc, increments the step count.
        If it's a new primitive (or "none" for rest), enters/continues rest.
        """
        if primitive == "none" or not primitive:
            # Rest step — track rest duration
            if self._current_phase != "rest" and self._current_primitive:
                # Just entered rest — record the completed primitive
                self._completed_primitives.append(self._current_primitive)
            self._current_phase = "rest"
            self._rest_step_count += 1
            return
        # Active primitive step
        self._rest_step_count = 0
        if primitive == self._current_primitive:
            self._primitive_step_count += 1
        else:
            self._current_primitive = primitive
            self._primitive_step_count = 1
            self._setup_steps = 0
            self._challenge_steps = 0
        self._current_phase = phase
        if phase == "setup":
            self._setup_steps += 1
        elif phase == "challenge":
            self._challenge_steps += 1

    def get_primitive_arc_status(self) -> dict:
        """Get current primitive arc status for prompt injection.

        Returns:
            Dict with keys: primitive, step_count, phase, setup_steps,
            challenge_steps, rest_step_count, completed_primitives.
        """
        return {
            "primitive": self._current_primitive,
            "step_count": self._primitive_step_count,
            "phase": self._current_phase,
            "setup_steps": self._setup_steps,
            "challenge_steps": self._challenge_steps,
            "rest_step_count": self._rest_step_count,
            "completed_primitives": list(self._completed_primitives),
        }

    def get_struggle_points(self) -> list[dict]:
        """Get steps where agent struggled (failed multiple times)."""
        struggles = []
        consecutive_failures = 0
        for entry in self._history:
            if not entry["agent_succeeded"]:
                consecutive_failures += 1
                if consecutive_failures >= 2:
                    struggles.append(entry)
            else:
                consecutive_failures = 0
        return struggles

    def get_primitive_stats(self) -> dict:
        """Get per-primitive success/failure breakdown.

        Returns:
            Dict mapping primitive names to stats, e.g.::

                {
                    "reflection": {"count": 3, "agent_success_rate": 0.33},
                    "verification": {"count": 2, "agent_success_rate": 0.50},
                }
        """
        primitive_data: dict[str, dict] = {}
        for entry in self._history:
            prim = entry.get("primitive")
            if prim is None:
                continue
            if prim not in primitive_data:
                primitive_data[prim] = {"count": 0, "successes": 0}
            primitive_data[prim]["count"] += 1
            if entry["agent_succeeded"]:
                primitive_data[prim]["successes"] += 1

        result = {}
        for prim, data in primitive_data.items():
            result[prim] = {
                "count": data["count"],
                "agent_success_rate": (
                    data["successes"] / data["count"] if data["count"] > 0 else 0.0
                ),
            }
        return result

    def get_stats(self) -> dict:
        """Get adversarial statistics for analysis."""
        total = len(self._history)
        if total == 0:
            return {"total_obstacles": 0, "agent_success_rate": 1.0}

        successes = sum(1 for h in self._history if h["agent_succeeded"])
        tactics_used = {}
        for h in self._history:
            t = h["tactic"]
            tactics_used[t] = tactics_used.get(t, 0) + 1

        stats = {
            "total_obstacles": total,
            "agent_success_rate": successes / total,
            "tactics_breakdown": tactics_used,
            "struggle_points": len(self.get_struggle_points()),
        }

        # Include primitive breakdown when primitive data exists
        primitive_stats = self.get_primitive_stats()
        if primitive_stats:
            stats["primitive_breakdown"] = primitive_stats

        return stats

    def reset(self) -> None:
        """Reset for new episode."""
        self._obstacle_count = 0
        self._cooldown_remaining = 0
        self._history = []
        self._last_tactic = None
        self._current_primitive = None
        self._primitive_step_count = 0
        self._current_phase = None
        self._setup_steps = 0
        self._challenge_steps = 0
        self._rest_step_count = 0
        self._completed_primitives = []


# =============================================================================
# Module
# =============================================================================

@dataclass
class AdversarialModule(Module):
    """
    Module for adversarial simulator configuration.

    Provides prompt blocks and tracking for adversarial behavior.
    """

    mode: AdversarialMode = AdversarialMode.NONE
    max_consecutive_obstacles: int = 3
    cooldown_steps: int = 2
    target_primitives: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.name = f"adversarial_{self.mode.value}"
        self.description = f"Adversarial mode: {self.mode.value}"
        self._tracker = AdversarialTracker(
            max_consecutive=self.max_consecutive_obstacles,
            cooldown_steps=self.cooldown_steps,
        )

    def get_prompt_blocks(self) -> list[PromptBlock]:
        """Return prompt block for selected mode."""
        blocks = {
            AdversarialMode.NONE: NoneAdversarialBlock(),
            AdversarialMode.SUBTLE: SubtleAdversarialBlock(),
            AdversarialMode.DECEPTIVE: DeceptiveAdversarialBlock(),
            AdversarialMode.HOSTILE: HostileAdversarialBlock(),
        }
        if self.mode == AdversarialMode.PRIMITIVE_TARGETED:
            return [PrimitiveTargetedBlock(self.target_primitives)]
        return [blocks[self.mode]]

    def get_tracker(self) -> AdversarialTracker:
        """Get the adversarial tracker."""
        return self._tracker

    def is_adversarial(self) -> bool:
        """Check if adversarial mode is active."""
        return self.mode != AdversarialMode.NONE

    def reset(self) -> None:
        """Reset tracker for new episode."""
        self._tracker.reset()
