#!/bin/bash
# Test a Gemini agent with a Gemini simulator on a WebAgentBench template.
# Defaults target the WAB "dark_checkout" task.

# set -euo pipefail
# cd "$(dirname "$0")"

# source .venv/bin/activate

AGENT_MODEL=${AGENT_MODEL:-"gemini-3-flash-preview"}
SIM_MODEL=${SIM_MODEL:-"gemini-3-flash-preview"}
ADVERSARIAL=${ADVERSARIAL:-0}

PAGES=(
  wizard_form
  slow_search
  dark_checkout
  popup_landing
  flaky_form
  filter_dashboard
  scavenger_hunt
  fake_success
  broken_layout
  session_content
)

declare -A TASKS=(
  [wizard_form]="Complete the insurance application for a California property. You need earthquake coverage, which requires the Premium plan. Fill out all 4 steps and submit the form."
  [slow_search]="Find the property at 742 Evergreen Terrace and report its price per square foot. You may need to load additional results and expand property details."
  [dark_checkout]="Purchase the laptop for \\$1,299.99 with standard shipping (\\$9.99). Do not add any optional extras, warranties, or subscriptions. Your final total should be \\$1,309.98."
  [popup_landing]="Find the screen size specification for the UltraView Pro monitor. Dismiss any overlays or popups that block the content. Report the exact screen size value."
  [flaky_form]="Submit the bug report form with title 'Memory leak in auth module', severity 'High', and description 'Auth tokens not cleared on logout'. The form may fail -- persist until successful. Use the Save Draft feature to protect your progress."
  [filter_dashboard]="Find all Senior Engineers in the San Francisco office with salary above \\$150,000, sorted by name ascending. Report the total count of matching employees."
  [scavenger_hunt]="Navigate between the three sections of this portal. Find the project coordinator's name in Section 1, the revised budget amount referenced in Section 2, and submit both values in the form in Section 1."
  [fake_success]="Change the notification preference to 'Email Only' and the timezone to 'Pacific (UTC-8)'. Make sure the changes are actually saved, not just displayed as saved."
  [broken_layout]="Fill out the registration form with: Name 'Alex Rivera', Email 'alex@example.com', Department 'Engineering', and check the 'Agree to Terms' checkbox. Submit the form."
  [session_content]="Complete the orientation: take the skill assessment quiz, study your assigned module, find the key code in your module, and enter it in the final assessment form."
)

declare -A PRIMS=(
  [wizard_form]="backtracking memory reflection"
  [slow_search]="patience exploration"
  [dark_checkout]="adversarial_robustness verification attention_focus"
  [popup_landing]="attention_focus spatial_reasoning"
  [flaky_form]="error_recovery reflection"
  [filter_dashboard]="constraint_satisfaction planning"
  [scavenger_hunt]="memory exploration planning"
  [fake_success]="verification reflection"
  [broken_layout]="spatial_reasoning exploration"
  [session_content]="planning memory"
)

for page_id in "${PAGES[@]}"; do
  template="wab_${page_id}"
  task="${TASKS[$page_id]}"
  if [[ -z "${task}" ]]; then
    echo "ERROR: Missing task instruction for ${page_id}" >&2
    exit 1
  fi

  adv_args=()
  if [[ "${ADVERSARIAL}" == "1" || "${ADVERSARIAL}" == "true" ]]; then
    prims="${PRIMS[$page_id]}"
    if [[ -z "${prims}" ]]; then
      echo "ERROR: Missing adversarial primitives for ${page_id}" >&2
      exit 1
    fi
    adv_args=(--adversarial primitive_targeted --adversarial-primitives ${prims})
  fi

  echo "=== Running ${template} ==="
  python -m llmos.main run \
    --task "$task" \
    --template "$template" \
    --difficulty hard \
    --strictness strict \
    --action-space minimal \
    "${adv_args[@]}" \
    --sim-provider gemini \
    --sim-model "$SIM_MODEL" \
    --agent-provider gemini \
    --agent-model "$AGENT_MODEL"
done
