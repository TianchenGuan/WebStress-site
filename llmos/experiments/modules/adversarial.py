"""
Adversarial Module: Simulator that creates realistic obstacles for agents.

Modes:
- NONE: No adversarial behavior (baseline)
- SUBTLE: Realistic obstacles (popups, validation, timeouts)
- DECEPTIVE: Ambiguous UI (similar buttons, misleading labels)
- HOSTILE: Active interference (redirects, content changes, session expiry)

The key constraint: every obstacle must be realistic and explainable.
"""

from dataclasses import dataclass
from typing import Optional

from ...core.modules.enums import AdversarialMode
from .base import (
    Module,
    BasePromptBlock,
    PromptBlock,
)


# =============================================================================
# Prompt Blocks
# =============================================================================

NONE_ADVERSARIAL_PROMPT = """
## Adversarial Mode: None

Simulate normally without intentional obstacles.
"""

SUBTLE_ADVERSARIAL_PROMPT = """
## Adversarial Mode: Subtle Obstacles

Your goal: Create REALISTIC obstacles that hinder the agent's progress.

Before generating state changes:
1. Identify what the agent is trying to achieve
2. Choose ONE realistic obstacle from the categories below (or create a new one)
3. Apply it naturally - the agent should not detect intentional sabotage

### Obstacle Categories

**Form & Input Obstacles:**
- **Validation error**: Reject valid input with plausible error ("Password must contain symbol", "Invalid email format")
- **Field cleared**: Browser autofill conflict clears a field agent just filled
- **Focus stolen**: Another element grabs focus (chat widget, notification)
- **Input lag**: Text appears character by character, requires waiting
- **Format mismatch**: "Please enter date as MM/DD/YYYY" when agent used YYYY-MM-DD
- **Character limit**: Silently truncate input that exceeds limit
- **Required field**: Previously optional field now shows as required
- **Dropdown closed**: Dropdown menu closes before selection completes

**UI Blocking Obstacles:**
- **Popup/modal**: Cookie consent, newsletter signup, survey, or chat widget blocking target
- **Confirmation dialog**: "Are you sure?", "Unsaved changes will be lost"
- **CAPTCHA**: Verification challenge at form submission or suspicious activity
- **Terms acceptance**: "Please accept terms to continue" checkbox appears
- **Age verification**: Age gate appears before content
- **Notification permission**: Browser asks for notification permission, blocks interaction
- **Overlay ad**: Non-intrusive ad appears near target element

**Navigation Obstacles:**
- **Scroll needed**: Target element exists but requires scrolling to reach
- **Collapsed section**: Target is inside collapsed accordion/dropdown
- **Tab switch needed**: Content is on different tab than currently active
- **Pagination**: Target item is on page 2 or 3 of results
- **Infinite scroll**: Need to scroll to load more items before target appears
- **Back button trap**: Clicking back goes to unexpected page

**Loading & Timing Obstacles:**
- **Loading delay**: Extended loading spinner, requires waiting or retry
- **Partial load**: Page loads but target element still loading
- **Lazy load**: Element loads only when scrolled into view
- **Skeleton UI**: Placeholder shown, real content not yet ready
- **Stale data**: "Data may be outdated, click refresh"

**State Obstacles:**
- **Dirty form warning**: "You have unsaved changes" when navigating
- **Undo prompt**: "Action completed. Undo?" with timeout
- **Auto-save conflict**: "Saving..." blocks further edits temporarily
- **Draft recovery**: "Restore previous draft?" dialog

### Custom Obstacles

You may create NEW obstacle types not listed above IF:
1. It represents a realistic scenario that occurs in real web applications
2. You can explain WHY this would happen naturally (not intentional sabotage)
3. The agent has a clear way to overcome it

When using a custom obstacle, explain: "Custom obstacle: [description] - Realistic because: [reason]"

### Rules
- Only ONE obstacle per step (don't stack multiple)
- Obstacle must be explainable as normal system behavior
- After 2-3 failed attempts on same obstacle, let agent proceed
- Track obstacles in hidden_state to avoid infinite loops
- Vary obstacle types - don't repeat the same one consecutively

Output format: "Obstacle: [type] - [justification]"
"""

DECEPTIVE_ADVERSARIAL_PROMPT = """
## Adversarial Mode: Deceptive UI

Your goal: Create AMBIGUOUS situations that mislead the agent.

Before generating state changes:
1. Identify what the agent is trying to click/fill/find
2. Create confusion through ambiguity
3. Make the "wrong" choice appear more attractive

### Deception Categories

**Duplicate & Similar Elements:**
- **Duplicate buttons**: Similar button nearby ("Submit" next to "Submit for Review")
- **Similar names in list**: Multiple items with near-identical names ("Report_v2", "Report_v2_final", "Report_v2_final_FINAL")
- **Multiple forms**: Two forms on page, one correct, one for different purpose
- **Icon confusion**: Two icons that look similar but do different things
- **Nested duplicates**: Button inside a button-like container

**Misleading Labels & Text:**
- **Inverted meaning**: "Continue" actually goes back, "Yes" means cancel
- **Ambiguous labels**: "OK" button on error dialog - does it retry or dismiss?
- **Technical jargon**: Options labeled with confusing technical terms
- **Abbreviated labels**: "Proc." vs "Process" vs "Proceed" - which is which?
- **Localization quirks**: Partially translated UI with mixed languages

**Decoy Elements:**
- **Fake download button**: Ad styled as download button near real one
- **Sponsored results**: Promoted item looks like organic result
- **Premium upsell**: "Get Pro" button styled more prominently than free option
- **Social login**: Multiple OAuth buttons when only one works
- **Newsletter checkbox**: Pre-checked "Subscribe" near submit button

**Visual Deception:**
- **Hidden correct option**: Correct element needs hover/expand to reveal, decoy visible
- **Changed positions**: Elements swap positions from previous state
- **Greyed out decoy**: Disabled-looking element is actually correct target
- **Color mismatch**: Primary action styled as secondary, vice versa
- **Size hierarchy wrong**: Less important button is larger/more prominent
- **Buried in footer**: Key action hidden among footer links

**State-Based Deception:**
- **Phantom selection**: Previously selected item appears selected but isn't
- **Stale highlighting**: Old search highlight on wrong element
- **Cached state**: UI shows old state, action operates on new state
- **Partial update**: Some elements updated, others stale

**Dark Patterns (Realistic):**
- **Confirm-shaming**: "No thanks, I don't want to save money" as cancel option
- **Roach motel**: Easy to get in, hard to get out (cancel subscription flow)
- **Misdirection**: Visual emphasis on unwanted option
- **Trick questions**: Double-negative checkboxes

### Custom Deceptions

You may create NEW deception types not listed above IF:
1. It represents a real UI/UX pattern found on actual websites (even if poor design)
2. The confusion is plausible (bad design, dark patterns, or honest mistakes happen)
3. The correct path still EXISTS (just harder to identify)

When using a custom deception: "Custom deception: [description] - Realistic because: [example site or pattern]"

### Rules
- Deception must be realistic (real websites do this, often unintentionally)
- The correct path must still EXIST (just harder to find)
- Don't make it impossible, just confusing
- Avoid repeating the same trick consecutively

Output format: "Deception: [type] - [how it misleads]"
"""

HOSTILE_ADVERSARIAL_PROMPT = """
## Adversarial Mode: Hostile Environment

Your goal: ACTIVELY interfere with agent progress using realistic system behaviors.

Before generating state changes:
1. Identify the agent's current objective
2. Disrupt progress with system-level interference
3. Force agent to recover and retry

### Hostile Categories

**Session & Authentication:**
- **Session timeout**: "Session expired, please log in again" - reset to login page
- **Permission denied**: "You don't have access" suddenly on previously accessible resource
- **Token refresh**: "Please re-authenticate" - credentials still valid but token expired
- **MFA challenge**: Unexpected 2FA prompt ("Verify it's you")
- **Account locked**: "Too many failed attempts" (even without failures)
- **Password change required**: "Your password has expired"
- **Device verification**: "New device detected, please verify"
- **SSO redirect**: Kicked to SSO provider, need to re-auth

**Network & Connectivity:**
- **Network error**: "Connection lost" on form submission - data may/may not be saved
- **Timeout**: Request hangs then fails ("Request timed out")
- **502/503 error**: "Service temporarily unavailable"
- **DNS failure**: "Could not resolve host" (simulated)
- **SSL error**: "Certificate error" warning page
- **Retry storm**: Each retry gets "Server busy, try again"

**Data & State Loss:**
- **Page refresh**: Content reloads, losing unsaved form data
- **Form reset**: Form clears on failed validation
- **Draft lost**: "Could not save draft" after long input
- **Concurrent edit conflict**: "This record was modified by another user"
- **Version mismatch**: "This page has been updated, please refresh"
- **Cache invalidation**: Cached data cleared, need to re-fetch

**Redirects & Navigation:**
- **Forced redirect**: Navigate away ("You've been logged out due to inactivity")
- **Deep link broken**: Link leads to 404 or homepage
- **Maintenance mode**: "System under maintenance, try again in 5 minutes"
- **Feature flag off**: Feature suddenly unavailable
- **Geo-restriction**: "This content is not available in your region"
- **A/B test switch**: UI layout changes mid-session

**Rate & Resource Limits:**
- **Rate limiting**: "Too many requests, please wait 60 seconds"
- **Quota exceeded**: "You've reached your daily limit"
- **File size limit**: "Upload too large" (even for small files)
- **Storage full**: "Not enough space"
- **Concurrent session limit**: "You're logged in elsewhere"

**Content & Element Changes:**
- **Content update**: Target element changes while agent was acting elsewhere
- **Element removed**: Target element no longer exists after page update
- **Element disabled**: Previously enabled button now greyed out
- **List reordered**: Items shuffled, target moved to different position
- **Search results changed**: New results loaded, target item gone
- **Notification clears target**: System notification covers/removes target area

**Process Interruption:**
- **Mandatory update**: "Please update the app to continue"
- **Terms updated**: "Our terms have changed, please review and accept"
- **Survey intercept**: "Help us improve! Take a 30-second survey"
- **Feedback request**: "How was your experience?" modal
- **Announcement banner**: New feature announcement blocks content

### Custom Hostile Actions

You may create NEW hostile actions not listed above IF:
1. It represents a real failure mode or system behavior in production applications
2. You can cite a realistic cause (server issues, security policies, scaling problems)
3. A recovery path exists (even if painful - like re-doing work)

When using a custom hostile action: "Custom hostile: [description] - Realistic because: [production scenario]"

### Rules
- Each tactic must be a REAL scenario that happens in production systems
- ALWAYS provide a recovery path (login button, retry option, refresh suggestion)
- Don't use same tactic twice in a row
- Track interference count in hidden_state._adversarial_count
- After 3 hostile actions, reduce intensity for 2 steps (let agent recover)
- Hostile doesn't mean impossible - agent should be able to eventually succeed

Output format: "Hostile: [type] - [recovery path available]"
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
    """

    def __init__(self, max_consecutive: int = 3, cooldown_steps: int = 2):
        self.max_consecutive = max_consecutive
        self.cooldown_steps = cooldown_steps
        self._obstacle_count = 0
        self._cooldown_remaining = 0
        self._history: list[dict] = []
        self._last_tactic: Optional[str] = None

    def should_apply_obstacle(self) -> bool:
        """Check if we should apply an obstacle this step."""
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            return False
        return True

    def record_obstacle(self, tactic: str, target: str, success: bool) -> None:
        """Record an obstacle application."""
        self._history.append({
            "tactic": tactic,
            "target": target,
            "agent_succeeded": success,
            "step": len(self._history),
        })
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

        return {
            "total_obstacles": total,
            "agent_success_rate": successes / total,
            "tactics_breakdown": tactics_used,
            "struggle_points": len(self.get_struggle_points()),
        }

    def reset(self) -> None:
        """Reset for new episode."""
        self._obstacle_count = 0
        self._cooldown_remaining = 0
        self._history = []
        self._last_tactic = None


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
