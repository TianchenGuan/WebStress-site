"""
Task definitions for WebAgentBench environments.

Each task has: task_id, title, difficulty, instruction_template, env_id,
primary_primitives, start_path (optional).
"""

from __future__ import annotations

GMAIL_TASKS: list[dict] = [
    {
        "task_id": "gmail_thread_detective",
        "title": "Thread Detective",
        "difficulty": "hard",
        "env_id": "gmail",
        "instruction_template": (
            "Find the single meeting time that works for everyone by reading the scheduling "
            "email thread. Reply to the most recent message in the thread with the correct time."
        ),
        "primary_primitives": ["memory", "attention"],
    },
    {
        "task_id": "gmail_inbox_triage_protocol",
        "title": "Inbox Triage Protocol",
        "difficulty": "hard",
        "env_id": "gmail",
        "instruction_template": (
            "Triage your inbox: approve the invoice, ignore the promo, report the security "
            "alert, approve the travel request, and respond to the onboarding email without "
            "using Reply All. Forward the escalation email to your manager."
        ),
        "primary_primitives": ["planning", "attention"],
    },
    {
        "task_id": "gmail_filter_architect",
        "title": "Filter Architect",
        "difficulty": "hard",
        "env_id": "gmail",
        "instruction_template": (
            "Create email filters: (1) route billing emails from the billing domain to the "
            "'Billing' label, (2) route payroll keyword emails to the 'Payroll' label, and "
            "(3) forward emails from the executive to their assistant. Do not modify or delete "
            "the existing newsletter filter."
        ),
        "primary_primitives": ["attention", "constraint_satisfaction"],
        "start_path": "/settings",
    },
    {
        "task_id": "gmail_contact_cleanup",
        "title": "Contact Cleanup",
        "difficulty": "medium",
        "env_id": "gmail",
        "instruction_template": (
            "Clean up your contacts: delete contacts not contacted in over 30 days, but keep "
            "contacts contacted within 30 days. Also add a missing contact found in your inbox "
            "who is not yet in your contacts list."
        ),
        "primary_primitives": ["attention", "constraint_satisfaction"],
    },
    {
        "task_id": "gmail_priority_escalation",
        "title": "Priority Escalation",
        "difficulty": "hard",
        "env_id": "gmail",
        "instruction_template": (
            "Find all unread emails from VIP contacts. Reply to the oldest unread VIP email "
            "with a status update. Star all unread VIP emails."
        ),
        "primary_primitives": ["attention", "exploration"],
    },
    {
        "task_id": "gmail_morning_triage_extended",
        "title": "Morning Triage Extended",
        "difficulty": "hard",
        "env_id": "gmail",
        "instruction_template": (
            "Process your morning inbox: reply to urgent emails (deadline/sign-off requests), "
            "forward the forwarding-target email to the specified colleague, archive FYI-only "
            "and promotional emails. Do not reply to FYI decoy emails that look urgent but "
            "are informational only."
        ),
        "primary_primitives": ["planning", "attention"],
    },
    {
        "task_id": "gmail_meeting_negotiation",
        "title": "Meeting Negotiation",
        "difficulty": "hard",
        "env_id": "gmail",
        "instruction_template": (
            "Coordinate a meeting: find the one time slot that works for all attendees by "
            "reading their availability emails. Reply to the venue coordinator with the "
            "confirmed time and room name."
        ),
        "primary_primitives": ["memory", "constraint_satisfaction"],
    },
    {
        "task_id": "gmail_incident_escalation",
        "title": "Incident Escalation",
        "difficulty": "hard",
        "env_id": "gmail",
        "instruction_template": (
            "Handle an incident: read the alert thread to find the error code and on-call "
            "engineer. Forward the alert to the on-call engineer with the error code. Reply "
            "to the manager's status request with the incident summary."
        ),
        "primary_primitives": ["memory", "attention"],
    },
    {
        "task_id": "gmail_delegation_routing",
        "title": "Delegation Routing",
        "difficulty": "medium",
        "env_id": "gmail",
        "instruction_template": (
            "Route emails to the right people: forward the budget question to the CFO, the "
            "technical issue to the CTO, and the customer complaint to the support lead. "
            "Do not forward the decoy email that doesn't need routing."
        ),
        "primary_primitives": ["attention", "constraint_satisfaction"],
    },
    {
        "task_id": "gmail_data_compilation",
        "title": "Data Compilation",
        "difficulty": "hard",
        "env_id": "gmail",
        "instruction_template": (
            "Compile department budget numbers: find the correct budget figure from each "
            "department's email (across tabs and pages). Ignore decoy emails with outdated "
            "or draft numbers. Reply to the executive with all three correct figures."
        ),
        "primary_primitives": ["memory", "exploration"],
    },
    {
        "task_id": "gmail_subscription_cleanup",
        "title": "Subscription Cleanup",
        "difficulty": "medium",
        "env_id": "gmail",
        "instruction_template": (
            "Clean up subscriptions: unsubscribe from (delete) promotional newsletters, "
            "keep the one newsletter matching your preferred topic, and report spam emails. "
            "Do not delete personal emails or update-category emails."
        ),
        "primary_primitives": ["attention", "constraint_satisfaction"],
    },
    {
        "task_id": "gmail_vacation_preparation",
        "title": "Vacation Preparation",
        "difficulty": "hard",
        "env_id": "gmail",
        "instruction_template": (
            "Prepare for vacation: enable the vacation responder with the provided message, "
            "forward pending items to your backup colleague, and reply to your boss confirming "
            "the handoff is complete."
        ),
        "primary_primitives": ["planning", "memory"],
        "start_path": "/settings",
    },
    {
        "task_id": "gmail_contact_audit",
        "title": "Contact Audit",
        "difficulty": "medium",
        "env_id": "gmail",
        "instruction_template": (
            "Audit your contacts: remove stale contacts (no activity in 30+ days), keep "
            "near-threshold contacts, and add new contacts discovered in recent emails."
        ),
        "primary_primitives": ["attention", "constraint_satisfaction"],
    },
    {
        "task_id": "gmail_thread_archaeology",
        "title": "Thread Archaeology",
        "difficulty": "hard",
        "env_id": "gmail",
        "instruction_template": (
            "Dig through an old email thread to find: the current assignee, the manager who "
            "approved the change, and the deadline. Reply to the thread with these details. "
            "Watch out for reassignment emails that change the original assignee."
        ),
        "primary_primitives": ["memory", "exploration"],
    },
    {
        "task_id": "gmail_filter_overhaul",
        "title": "Filter Overhaul",
        "difficulty": "hard",
        "env_id": "gmail",
        "instruction_template": (
            "Fix and create email filters: repair the broken filter (wrong domain), create "
            "a keyword-based filter for a new label, and set up an auto-archive filter for "
            "a specific domain. Set up forwarding for a specific sender."
        ),
        "primary_primitives": ["attention", "constraint_satisfaction"],
        "start_path": "/settings",
    },
    {
        "task_id": "gmail_budget_reconciliation",
        "title": "Budget Reconciliation",
        "difficulty": "hard",
        "env_id": "gmail",
        "instruction_template": (
            "Reconcile budget figures: compare each department's email against the summary "
            "email. Identify which numbers in the summary are wrong, find the correct values "
            "from the department emails, and reply to the summary author with corrections."
        ),
        "primary_primitives": ["memory", "constraint_satisfaction"],
    },
    {
        "task_id": "gmail_label_workflow_setup",
        "title": "Label Workflow Setup",
        "difficulty": "medium",
        "env_id": "gmail",
        "instruction_template": (
            "Set up label workflows: apply the 'Client' label to emails from the client "
            "domain, and apply the 'Project Review' label to project review emails. Do not "
            "label the wrong review email or the non-review email."
        ),
        "primary_primitives": ["attention", "constraint_satisfaction"],
    },
    {
        "task_id": "gmail_phishing_investigation",
        "title": "Phishing Investigation",
        "difficulty": "hard",
        "env_id": "gmail",
        "instruction_template": (
            "Investigate potential phishing: identify emails with spoofed sender domains "
            "(mismatched display name vs actual address). Report phishing emails and confirm "
            "legitimate ones. Forward the phishing report to the security team."
        ),
        "primary_primitives": ["attention", "verification"],
    },
    {
        "task_id": "gmail_new_hire_setup",
        "title": "New Hire Setup",
        "difficulty": "medium",
        "env_id": "gmail",
        "instruction_template": (
            "Set up as a new hire: add contacts from welcome emails, update your display "
            "density setting to 'compact', change default reply behavior to 'reply all', "
            "and reply to the team introduction email with your intro phrase. Do not use "
            "Reply All on the CC'd welcome email."
        ),
        "primary_primitives": ["planning", "attention"],
        "start_path": "/settings",
    },
    {
        "task_id": "gmail_quarterly_closeout",
        "title": "Quarterly Closeout",
        "difficulty": "hard",
        "env_id": "gmail",
        "instruction_template": (
            "Perform quarterly inbox closeout: star important emails (board/renewal), archive "
            "FYI-only emails, delete promotional newsletters, report spam, and create a filter "
            "for the vendor domain. Remove stale contacts and keep active ones."
        ),
        "primary_primitives": ["planning", "exploration"],
    },
]

# Index by task_id
GMAIL_TASK_INDEX: dict[str, dict] = {t["task_id"]: t for t in GMAIL_TASKS}

# Combined index for all environments
TASK_INDEX: dict[str, dict] = {**GMAIL_TASK_INDEX}
