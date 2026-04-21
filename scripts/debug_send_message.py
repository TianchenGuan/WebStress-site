"""Simulate booking_send_message end-to-end via Python, print why create[0] fails."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from webagentbench.tasks._registry import get_task
from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.booking import BookingState  # noqa: F401

TASK_ID = "booking_send_message"

sm = SessionManager()
sid, targets, _seed = sm.create_session("booking", TASK_ID, None)
state = sm.get(sid)
initial_snap = sm.get_initial_snapshot(sid)
print(f"session_id: {sid}")
print(f"\ntargets:")
for k, v in targets.items():
    print(f"  {k} = {v!r}")

print(f"\n{len(state.properties)} properties in seed:")
for p in state.properties:
    print(f"  id={p.id!r} name={p.name!r}")

print(f"\nInitial messages ({len(state.messages)}):")
for m in state.messages:
    print(f"  id={m.id} sender={m.sender} property_id={m.property_id!r} subject={m.subject!r} read={m.read}")

# Now send the task message as user would
target_pid = targets["property_id"]
print(f"\n>>> Sending message with property_id={target_pid!r}")
msg = state.send_message(
    property_id=target_pid,
    reservation_id="",
    subject="Check-in time inquiry",
    body="Hello, could you please let me know the earliest check-in time available? Thank you.",
)
print(f"Created msg:")
print(f"  id={msg.id!r}")
print(f"  property_id={msg.property_id!r}")
print(f"  property_name={msg.property_name!r}")
print(f"  reservation_id={msg.reservation_id!r}")
print(f"  subject={msg.subject!r}")
print(f"  body={msg.body[:70]!r}...")
print(f"  sender={msg.sender!r}")
print(f"  read={msg.read}")

# Run evaluator
from webagentbench.evaluator_diff import compute_diff, match_diff
task = get_task(TASK_ID)

agent_diff = compute_diff(initial_snap, state)
print(f"\n=== AGENT DIFF ({len(agent_diff)} entries) ===")
for e in agent_diff:
    print(f"  {type(e).__name__}: entity={e.entity} id={e.entity_id}")
    if hasattr(e, "fields") and e.entity == "messages":
        print(f"    fields: {json.dumps(e.fields, indent=6, default=str)[:500]}")

print(f"\n=== CANONICAL DIFF ===")
print(f"create entries: {len(task.canonical_diff.create)}")
for i, c in enumerate(task.canonical_diff.create):
    print(f"  create[{i}]: entity={c.entity} desc={c.desc!r}")
    print(f"    properties: {c.properties}")

report = match_diff(agent_diff, task.canonical_diff, targets, initial_snap, state)
print(f"\n=== EVAL REPORT ===")
print(f"report attrs: {list(vars(report).keys())}")
print(f"checks ({len(report.checks)}):")
for c in report.checks:
    print(f"  {c['passed']} {c['desc'][:80]}")
    if not c['passed']: print(f"    error={c.get('error')}")
print(f"negative_checks ({len(report.negative_checks)}):")
for nc in report.negative_checks:
    print(f"  pass={nc['passed']} penalty={nc.get('penalty', 0)} {nc['desc'][:80]}")
