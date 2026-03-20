from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from .models.gmail import Attachment, Contact, Email, FilterRule, GmailSettings, Label
from .tasks import TASK_INDEX


def derive_seed(*parts: str | int) -> int:
    joined = "::".join(str(part) for part in parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


class Seeder:
    """Deterministic Faker-backed generator with per-environment dispatch."""

    def __init__(self, seed: int):
        self.seed = seed
        self.rng = random.Random(seed)
        try:
            from faker import Faker
            self.fake = Faker()
        except ImportError:
            self.fake = _FallbackFaker(seed)
        self.fake.seed_instance(seed)

    def generate(self, env_id: str, task_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        if env_id != "gmail":
            raise KeyError(f"Unsupported environment for seeding: {env_id}")
        task_def = TASK_INDEX[task_id]
        generator = GmailSeeder(self.seed, self.fake, self.rng)
        return generator.generate(task_def)


class GmailSeeder:
    def __init__(self, seed: int, fake, rng: random.Random):
        self.seed = seed
        self.fake = fake
        self.rng = rng
        self.now = datetime.now(timezone.utc)
        self._counters: dict[str, int] = {}
        self.owner_name = "Avery Quinn"
        self.owner_email = "avery.quinn@webagentbench.test"

    def generate(self, task_def: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        task_id = task_def["task_id"]
        base = self._base_state(task_id)
        generator = getattr(self, f"_seed_{task_id}", None)
        if generator is None:
            raise KeyError(f"No Gmail seed generator for task {task_id}")
        targets = generator(base)
        self._add_generic_distractors(base, count=40)
        base["emails"] = sorted(base["emails"], key=lambda email: email.timestamp, reverse=True)
        base["contacts"] = sorted(
            base["contacts"],
            key=lambda contact: contact.name.lower(),
        )
        return base, targets

    def _base_state(self, task_id: str) -> dict[str, Any]:
        labels = [
            Label(id="label_inbox", name="inbox", color="#202124", system=True),
            Label(id="label_starred", name="starred", color="#fbbc04", system=True),
            Label(id="label_snoozed", name="snoozed", color="#5f6368", system=True),
            Label(id="label_important", name="important", color="#d93025", system=True),
            Label(id="label_sent", name="sent", color="#188038", system=True),
            Label(id="label_scheduled", name="scheduled", color="#5f6368", system=True, show_in_label_list="show_if_unread"),
            Label(id="label_drafts", name="drafts", color="#5f6368", system=True),
            Label(id="label_allmail", name="all mail", color="#5f6368", system=True, show_in_label_list="hide"),
            Label(id="label_spam", name="spam", color="#5f6368", system=True, show_in_label_list="hide"),
            Label(id="label_trash", name="trash", color="#d93025", system=True),
            Label(id="label_promotions", name="promotions", color="#f9ab00", system=True),
            Label(id="label_updates", name="updates", color="#1a73e8", system=True),
            Label(id="label_vip", name="VIP", color="#e37400"),
        ]
        contacts = [self._contact(is_vip=False) for _ in range(10)]
        return {
            "env_id": "gmail",
            "task_id": task_id,
            "owner_name": self.owner_name,
            "owner_email": self.owner_email,
            "emails": [],
            "drafts": [],
            "sent": [],
            "deleted": [],
            "contacts": contacts,
            "labels": labels,
            "filters": [],
            "settings": GmailSettings(
                id="settings_gmail",
                signature="Avery Quinn\nOperations Lead",
                forwarding_address="",
                display_density="comfortable",
                vacation_responder_enabled=False,
                auto_advance="newer",
                language="English (US)",
                input_tools_enabled=True,
                right_to_left=False,
                max_page_size=50,
                undo_send_seconds=5,
                default_reply_behavior="reply",
                hover_actions_enabled=True,
                send_and_archive=False,
                default_text_style="Sans Serif",
            ),
        }

    def _first_name(self, name: str) -> str:
        return name.split()[0]

    def _format_email_body(self, *paragraphs: str, signoff_name: str | None = None) -> str:
        body = "\n\n".join(paragraph.strip() for paragraph in paragraphs if paragraph.strip())
        if signoff_name:
            body = f"{body}\n\nThanks,\n{signoff_name}"
        return body

    def _bullet_lines(self, items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items)

    def _initiative_name(self) -> str:
        prefixes = [
            "Atlas",
            "Northstar",
            "Summit",
            "Harbor",
            "Beacon",
            "Lattice",
            "Signal",
            "Cedar",
        ]
        nouns = [
            "launch review",
            "vendor recovery plan",
            "staffing sync",
            "operations readout",
            "forecast refresh",
            "policy review",
            "board prep",
            "customer rollout",
        ]
        return f"{self.rng.choice(prefixes)} {self.rng.choice(nouns)}"

    def _generic_email_body(self, sender_name: str) -> str:
        first_name = self._first_name(sender_name)
        update_openers = [
            "Sharing the latest notes before tomorrow's check-in.",
            "Passing along the current draft so you have it in one place.",
            "Sending a quick status update from today's working session.",
            "I pulled the loose ends into one note for easier review.",
        ]
        middle_notes = [
            "The open items are mostly ownership questions rather than scope changes.",
            "Nothing looks blocked right now, but we still need one decision on timing.",
            "The team is aligned on the main path and only needs confirmation on the follow-up items.",
            "Most of the edits were minor, with one budget line still waiting on approval.",
        ]
        closers = [
            "No response needed unless you want anything reordered.",
            "If you want, I can turn this into a cleaner summary before the meeting.",
            "Happy to consolidate comments if more feedback comes in.",
            "Let me know if you want the spreadsheet version as well.",
        ]
        return self._format_email_body(
            self.rng.choice(update_openers),
            f"{self.rng.choice(middle_notes)} {self.rng.choice(closers)}",
            signoff_name=first_name,
        )

    def _seed_gmail_thread_detective(self, base: dict[str, Any]) -> dict[str, Any]:
        sender_name = self.fake.name()
        sender_email = self._email_for_name(sender_name, domain="vertexlab.test")
        other_sender_name = self.fake.name()
        other_sender_email = self._email_for_name(other_sender_name, domain="calendarhub.test")
        sender_first = self._first_name(sender_name)
        other_sender_first = self._first_name(other_sender_name)
        # CC a team lead on scheduling emails to create a Reply All trap (IR-4)
        cc_name = self.fake.name()
        cc_email = self._email_for_name(cc_name, domain="vertexlab.test")
        # 5 meeting times with 4 conflicts — prevents count-based elimination (SW-1.3)
        meeting_times = ["9:00 AM", "10:00 AM", "11:00 AM", "2:30 PM", "4:00 PM"]
        correct_index = self.rng.randrange(len(meeting_times))
        correct_time = meeting_times[correct_index]
        wrong_times = [time for index, time in enumerate(meeting_times) if index != correct_index]
        initiative_name = self._initiative_name()
        calendar_subject = f"Calendar conflicts for the {initiative_name}"
        option_notes = [
            "That slot would let us finalize the owner list before the design walkthrough starts.",
            "I can keep that window clear if we want to use it for the full agenda.",
            "That time works on my end and still leaves room for a short follow-up with finance.",
            "I could make that slot work if we want the review done before end-of-day wrap-up.",
            "That would give us a clean hour before the operations wrap-up at end of day.",
        ]
        conflict_reasons = self.rng.sample(
            [
                "standing finance review",
                "candidate interview panel",
                "facilities walkthrough",
                "vendor contract call",
                "customer escalation sync",
                "legal review hold",
                "quarterly planning block",
                "executive budget sync",
            ],
            k=len(wrong_times),
        )

        thread_ids: list[str] = []
        for index, meeting_time in enumerate(meeting_times):
            thread_id = self._id("thread")
            thread_ids.append(thread_id)
            sent_at = self.now - timedelta(days=6 - index, hours=2 * index)
            base["emails"].append(
                self._email(
                    from_name=sender_name,
                    from_addr=sender_email,
                    subject=f"Could we hold {meeting_time} for the {initiative_name}?",
                    body=self._format_email_body(
                        (
                            f"Hi Avery, could we use {meeting_time} for the {initiative_name}? "
                            f"{option_notes[index]}"
                        ),
                        (
                            "If that time is difficult on your side, I can keep circulating options, "
                            "but I wanted to send the cleanest windows first."
                        ),
                        signoff_name=sender_first,
                    ),
                    timestamp=sent_at,
                    thread_id=thread_id,
                    labels=["inbox", "VIP"],
                    cc=[cc_email],
                )
            )
        most_recent_thread_id = thread_ids[-1]
        conflict_lines = [
            f"{meeting_time}: already blocked by the {reason}"
            for meeting_time, reason in zip(wrong_times, conflict_reasons, strict=False)
        ]
        # Real calendar email — pushed to page 2 (SW-1.1) and in Updates tab (IR-1)
        base["emails"].append(
            self._email(
                from_name=other_sender_name,
                from_addr=other_sender_email,
                subject=calendar_subject,
                body=self._format_email_body(
                    (
                        f"I checked the proposed times from {sender_first} against the operating calendar "
                        f"for the {initiative_name}. The following options already have immovable holds:"
                    ),
                    self._bullet_lines(conflict_lines),
                    (
                        "I have not placed anything on your calendar yet because I wanted to send the "
                        "conflicts first."
                    ),
                    signoff_name=other_sender_first,
                ),
                timestamp=self.now - timedelta(days=7),
                thread_id=self._id("thread"),
                labels=["inbox", "updates", "important"],
            )
        )
        # Decoy calendar email — outdated data, only 2 conflicts (SW-1.2)
        decoy_conflict_lines = self.rng.sample(conflict_lines, k=2)
        base["emails"].append(
            self._email(
                from_name=other_sender_name,
                from_addr=other_sender_email,
                subject=f"Preliminary calendar notes for the {initiative_name}",
                body=self._format_email_body(
                    (
                        f"Quick preliminary note — I saw a couple of possible conflicts on the operating "
                        f"calendar for the {initiative_name}:"
                    ),
                    self._bullet_lines(decoy_conflict_lines),
                    (
                        "I will send a full conflict check once I can verify the rest. This is only "
                        "an early heads-up."
                    ),
                    signoff_name=other_sender_first,
                ),
                timestamp=self.now - timedelta(days=9),
                thread_id=self._id("thread"),
                labels=["inbox", "updates"],
                is_read=True,
            )
        )
        for _ in range(2):
            base["emails"].append(
                self._email(
                    from_name=sender_name,
                    from_addr=sender_email,
                    subject=f"{self._initiative_name().title()} notes",
                    body=self._generic_email_body(sender_name),
                    timestamp=self.now - timedelta(days=self.rng.randint(6, 12)),
                    thread_id=self._id("thread"),
                    labels=["inbox"],
                    is_read=True,
                )
            )
        self._ensure_contact(base, sender_name, sender_email, is_vip=True)
        self._ensure_contact(base, other_sender_name, other_sender_email)
        self._ensure_contact(base, cc_name, cc_email)
        return {
            "sender_name": sender_name,
            "sender_email": sender_email,
            "other_sender_name": other_sender_name,
            "other_sender_email": other_sender_email,
            "calendar_subject": calendar_subject,
            "correct_time": correct_time,
            "wrong_times": wrong_times,
            "most_recent_thread_id": most_recent_thread_id,
        }

    def _seed_gmail_inbox_triage_protocol(self, base: dict[str, Any]) -> dict[str, Any]:
        invoice_sender_name = self.fake.name()
        invoice_sender_email = self._email_for_name(invoice_sender_name, domain="billingdesk.test")
        invoice_decoy_sender_name = self.fake.name()
        invoice_decoy_sender_email = self._email_for_name(invoice_decoy_sender_name, domain="billingdesk.test")
        promo_sender_name = self.fake.company()
        promo_sender_email = self._email_for_name(promo_sender_name, domain="promooffers.test")
        security_sender_name = "Security Operations"
        security_sender_email = "alerts@secureops.test"
        travel_sender_name = self.fake.name()
        travel_sender_email = self._email_for_name(travel_sender_name, domain="traveldesk.test")
        travel_decoy_sender_name = self.fake.name()
        travel_decoy_sender_email = self._email_for_name(travel_decoy_sender_name, domain="traveldesk.test")
        onboarding_sender_name = "People Operations"
        onboarding_sender_email = "onboarding@peopleops.test"
        escalation_email = "sec-escalations@webagentbench.test"
        confirmation_phrase = "I have completed the onboarding checklist."
        invoice_label = "Finance Review"
        travel_label = "Travel Follow-up"

        invoice_email = self._email(
            from_name=invoice_sender_name,
            from_addr=invoice_sender_email,
            subject="Invoice 8842 needs approval",
            body=self._format_email_body(
                (
                    "Attached is invoice 8842 covering the Denver freight overage, badge reprints, "
                    "and on-site support from last week's event."
                ),
                (
                    "Accounts payable asked whether you can review it before Friday so the vendor stays "
                    "on normal payment terms."
                ),
                signoff_name=self._first_name(invoice_sender_name),
            ),
            timestamp=self.now - timedelta(days=2, hours=4),
            thread_id=self._id("thread"),
            labels=["inbox"],
            attachments=[self._attachment("invoice-8842.pdf", "application/pdf", "pdf")],
        )
        promo_email = self._email(
            from_name=promo_sender_name,
            from_addr=promo_sender_email,
            subject="Weekend bundle discount ends tonight",
            body=self._format_email_body(
                (
                    "This weekend only: bundle pricing on office seating, monitor arms, and conference "
                    "room accessories."
                ),
                (
                    "The storefront discount expires at midnight and includes free shipping on any order "
                    "above the corporate minimum."
                ),
                signoff_name=promo_sender_name,
            ),
            timestamp=self.now - timedelta(days=1, hours=3),
            thread_id=self._id("thread"),
            labels=["inbox", "promotions"],
        )
        security_email = self._email(
            from_name=security_sender_name,
            from_addr=security_sender_email,
            subject="Security alert: suspicious OAuth token",
            body=self._format_email_body(
                (
                    "A new OAuth token labeled 'Calendar Bridge' was issued from an unrecognized macOS "
                    "device at 03:14 UTC."
                ),
                (
                    "We have not revoked it yet because the workflow owner may still confirm it as valid, "
                    "but the activity should go through the normal incident path if it is unexpected."
                ),
                signoff_name="Security Operations",
            ),
            timestamp=self.now - timedelta(hours=11),
            thread_id=self._id("thread"),
            labels=["inbox", "important"],
        )
        travel_email = self._email(
            from_name=travel_sender_name,
            from_addr=travel_sender_email,
            subject="Travel request for Denver leadership offsite",
            body=self._format_email_body(
                (
                    "Can you confirm the hotel block and flight cap for next week's Denver leadership "
                    "offsite?"
                ),
                (
                    "The venue needs the rooming list on Monday, and finance asked whether ground "
                    "transportation should stay under the same trip code."
                ),
                signoff_name=self._first_name(travel_sender_name),
            ),
            timestamp=self.now - timedelta(days=6, hours=2),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )
        # CC HR team on onboarding email to create Reply All trap (IR-4)
        hr_cc_email = "hr-team@peopleops.test"
        onboarding_email = self._email(
            from_name=onboarding_sender_name,
            from_addr=onboarding_sender_email,
            subject="Complete your onboarding checklist",
            body=self._format_email_body(
                (
                    "Reply once your laptop setup, MFA enrollment, payroll forms, and badge pickup are "
                    "all complete so I can close the onboarding ticket."
                ),
                "If anything is still blocked, include the missing item in your response.",
                signoff_name="People Operations",
            ),
            timestamp=self.now - timedelta(days=7, hours=1),
            thread_id=self._id("thread"),
            labels=["inbox", "important"],
            cc=[hr_cc_email],
        )
        invoice_decoy_email = self._email(
            from_name=invoice_decoy_sender_name,
            from_addr=invoice_decoy_sender_email,
            subject="Invoice 8842 cover sheet and remittance note",
            body=self._format_email_body(
                (
                    "Sharing the remittance note and cover sheet for invoice 8842 before we close the "
                    "weekly vendor packet."
                ),
                (
                    "No approval needed on this one yet. I mainly wanted you to have the support file "
                    "in case finance asks for the remittance address."
                ),
                signoff_name=self._first_name(invoice_decoy_sender_name),
            ),
            timestamp=self.now - timedelta(days=2, hours=2),
            thread_id=self._id("thread"),
            labels=["inbox"],
            attachments=[self._attachment("invoice-8842-cover.pdf", "application/pdf", "pdf")],
        )
        security_followup_email = self._email(
            from_name=security_sender_name,
            from_addr=security_sender_email,
            subject="Security alert follow-up: Calendar Bridge token already revoked",
            body=self._format_email_body(
                (
                    "Following up on the earlier Calendar Bridge token alert. The token has already been "
                    "revoked on our side and the issuing device was removed from the allow list."
                ),
                "No additional incident routing is needed unless the device reappears in the audit log.",
                signoff_name="Security Operations",
            ),
            timestamp=self.now - timedelta(hours=5),
            thread_id=self._id("thread"),
            labels=["inbox", "updates"],
            is_read=True,
        )
        travel_decoy_email = self._email(
            from_name=travel_decoy_sender_name,
            from_addr=travel_decoy_sender_email,
            subject="Travel request for Denver leadership dinner",
            body=self._format_email_body(
                (
                    "Can you confirm whether the Denver dinner guest list should use the same travel code "
                    "as the leadership offsite?"
                ),
                "The restaurant needs the final count before I send the transportation confirmation.",
                signoff_name=self._first_name(travel_decoy_sender_name),
            ),
            timestamp=self.now - timedelta(days=3, hours=1),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )
        base["emails"].extend(
            [
                invoice_email,
                promo_email,
                security_email,
                travel_email,
                onboarding_email,
                invoice_decoy_email,
                security_followup_email,
                travel_decoy_email,
            ]
        )
        self._ensure_contact(base, invoice_sender_name, invoice_sender_email)
        self._ensure_contact(base, travel_sender_name, travel_sender_email)
        self._ensure_contact(base, onboarding_sender_name, onboarding_sender_email)
        self._ensure_contact(base, security_sender_name, security_sender_email, is_vip=True)
        return {
            "escalation_email": escalation_email,
            "confirmation_phrase": confirmation_phrase,
            "invoice_email_id": invoice_email.id,
            "promo_email_id": promo_email.id,
            "security_email_id": security_email.id,
            "travel_email_id": travel_email.id,
            "onboarding_email_id": onboarding_email.id,
            "invoice_decoy_email_id": invoice_decoy_email.id,
            "security_followup_email_id": security_followup_email.id,
            "travel_decoy_email_id": travel_decoy_email.id,
        }

    def _seed_gmail_filter_architect(self, base: dict[str, Any]) -> dict[str, Any]:
        billing_domain = "billing-vendors.test"
        billing_label = "Billing Vendors"
        payroll_keyword = "Payroll Exception"
        payroll_label = "Payroll"
        exec_sender_name = self.fake.name()
        exec_sender_email = self._email_for_name(exec_sender_name, domain="boardoffice.test")
        exec_forward_email = "chief-of-staff@webagentbench.test"

        # Pre-existing filter that must not be deleted (SW-3.1)
        existing_filter = FilterRule(
            id=self._id("filter"),
            name="Newsletter archive",
            query="from:@newsletters.test",
            from_addresses=["*@newsletters.test"],
            archive=True,
            mark_read=True,
        )
        base["filters"].append(existing_filter)

        base["emails"].extend(
            [
                # Billing email in Updates tab (IR-1)
                self._email(
                    from_name="Northwind Billing Operations",
                    from_addr=f"accounts@{billing_domain}",
                    subject="Invoice packet for March freight reconciliation",
                    body=self._format_email_body(
                        (
                            "Sending the March freight reconciliation packet for the warehouse transfer "
                            "and rush shipping charges."
                        ),
                        (
                            "The supporting worksheet is attached on our side; I can resend line-item "
                            "detail if you need it."
                        ),
                        signoff_name="Northwind Billing",
                    ),
                    timestamp=self.now - timedelta(days=2),
                    thread_id=self._id("thread"),
                    labels=["inbox", "updates"],
                ),
                self._email(
                    from_name="Payroll Systems",
                    from_addr="payroll@operations.test",
                    subject=f"{payroll_keyword} for March cycle",
                    body=self._format_email_body(
                        (
                            "The March payroll run flagged a withholding mismatch that still needs manual "
                            "review before payroll closes."
                        ),
                        (
                            "I left the exception open until someone confirms whether the state code should "
                            "be corrected or overridden."
                        ),
                        signoff_name="Payroll Systems",
                    ),
                    timestamp=self.now - timedelta(days=1, hours=5),
                    thread_id=self._id("thread"),
                    labels=["inbox", "important"],
                ),
                self._email(
                    from_name=exec_sender_name,
                    from_addr=exec_sender_email,
                    subject="Board packet follow-up",
                    body=self._format_email_body(
                        (
                            "Sending a marked-up board packet draft with a few notes on sequencing for the "
                            "Monday prep."
                        ),
                        (
                            "I may continue sending revisions from this address over the next week, so keep "
                            "an eye on anything related to the prep memo."
                        ),
                        signoff_name=self._first_name(exec_sender_name),
                    ),
                    timestamp=self.now - timedelta(hours=9),
                    thread_id=self._id("thread"),
                    labels=["inbox"],
                ),
            ]
        )
        self._ensure_contact(base, exec_sender_name, exec_sender_email, is_vip=True)
        return {
            "billing_domain": billing_domain,
            "billing_label": billing_label,
            "payroll_keyword": payroll_keyword,
            "payroll_label": payroll_label,
            "exec_sender_name": exec_sender_name,
            "exec_sender_email": exec_sender_email,
            "exec_forward_email": exec_forward_email,
            "existing_filter_id": existing_filter.id,
        }

    def _seed_gmail_contact_cleanup(self, base: dict[str, Any]) -> dict[str, Any]:
        stale_contact_a = self._contact(
            name=self.fake.name(),
            email=self.fake.email(domain="stale.test"),
            last_contacted_at=self.now - timedelta(days=45),
        )
        stale_contact_b = self._contact(
            name=self.fake.name(),
            email=self.fake.email(domain="archive.test"),
            last_contacted_at=self.now - timedelta(days=61),
        )
        keep_contact = self._contact(
            name=self.fake.name(),
            email=self.fake.email(domain="activepartner.test"),
            last_contacted_at=self.now - timedelta(days=5),
        )
        missing_contact_name = self.fake.name()
        missing_contact_legacy_email = self._email_for_name(missing_contact_name, domain="legacymailer.test")
        missing_contact_email = self._email_for_name(missing_contact_name, domain="recentmailer.test")
        missing_contact_subject = "March planning follow-up"
        contact_note = "Added after March planning thread."

        # Near-threshold decoys: 20-29 days, should NOT be deleted (SW-2.2)
        near_threshold_contact = self._contact(
            name=self.fake.name(),
            email=self.fake.email(domain="nearthreshold.test"),
            last_contacted_at=self.now - timedelta(days=25),
        )
        near_threshold_contact_b = self._contact(
            name=self.fake.name(),
            email=self.fake.email(domain="borderline.test"),
            last_contacted_at=self.now - timedelta(days=28),
        )
        base["contacts"].extend([
            stale_contact_a, stale_contact_b, keep_contact,
            near_threshold_contact, near_threshold_contact_b,
        ])
        base["emails"].extend(
            [
                self._email(
                    from_name=missing_contact_name,
                    from_addr=missing_contact_legacy_email,
                    subject="Alias check before March planning",
                    body=self._format_email_body(
                        (
                            "This older alias is still forwarding for now, but I am moving contract and "
                            "planning notes over to the newer mailbox this week."
                        ),
                        "You can ignore this one once the March thread is wrapped.",
                        signoff_name=self._first_name(missing_contact_name),
                    ),
                    timestamp=self.now - timedelta(days=6, hours=2),
                    thread_id=self._id("thread"),
                    labels=["inbox"],
                    is_read=True,
                ),
                self._email(
                    from_name=missing_contact_name,
                    from_addr=missing_contact_email,
                    subject=missing_contact_subject,
                    body=self._format_email_body(
                        (
                            "Good talking during the March planning thread. Could you add this address to "
                            "the vendor planning loop going forward?"
                        ),
                        (
                            "I usually send contract redlines from here, so it would help to have it saved "
                            "instead of relying on the older alias."
                        ),
                        signoff_name=self._first_name(missing_contact_name),
                    ),
                    timestamp=self.now - timedelta(days=1, hours=4),
                    thread_id=self._id("thread"),
                    labels=["inbox"],
                ),
                self._email(
                    from_name=keep_contact.name,
                    from_addr=keep_contact.email,
                    subject="Weekly checkpoint",
                    body=self._format_email_body(
                        (
                            "Sending the weekly checkpoint and revised venue shortlist from today's ops "
                            "review."
                        ),
                        (
                            "The timeline still looks fine on my side, but I wanted to keep the thread warm "
                            "before next week's decision meeting."
                        ),
                        signoff_name=self._first_name(keep_contact.name),
                    ),
                    timestamp=self.now - timedelta(days=3),
                    thread_id=self._id("thread"),
                    labels=["inbox"],
                ),
            ]
        )
        return {
            "stale_contact_id_a": stale_contact_a.id,
            "stale_contact_id_b": stale_contact_b.id,
            "missing_contact_name": missing_contact_name,
            "missing_contact_email": missing_contact_email,
            "missing_contact_subject": missing_contact_subject,
            "contact_note": contact_note,
            "keep_contact_name": keep_contact.name,
            "keep_contact_id": keep_contact.id,
            "near_threshold_contact_id": near_threshold_contact.id,
        }

    def _seed_gmail_priority_escalation(self, base: dict[str, Any]) -> dict[str, Any]:
        vip_contacts = [
            self._contact(is_vip=True, company="Executive Office"),
            self._contact(is_vip=True, company="Executive Office"),
            self._contact(is_vip=True, company="Executive Office"),
        ]
        future_vip_name = self.fake.name()
        future_vip_email = self._email_for_name(future_vip_name, domain="vipfuture.test")
        status_phrase = "Status update: I am actively on it."
        vip_email_ids: list[str] = []
        urgency_topics = [
            "vendor recovery timeline",
            "board deck edits",
            "staffing backfill status",
            "budget reforecast",
            "customer launch blocker",
        ]

        # Target VIP emails pushed further back for pagination (SW-5.2)
        for offset, contact in enumerate(vip_contacts):
            base["contacts"].append(contact)
            topic = urgency_topics[offset]
            email = self._email(
                from_name=contact.name,
                from_addr=contact.email,
                subject=f"Need an update on the {topic}",
                body=self._format_email_body(
                    (
                        f"Can you send me a short status note on the {topic}? I want to know whether "
                        "anything is blocked before close of business."
                    ),
                    (
                        "A concise reply is fine. I mainly need to know whether the work is moving and "
                        "where the next dependency sits."
                    ),
                    signoff_name=self._first_name(contact.name),
                ),
                timestamp=self.now - timedelta(days=12 - offset, hours=offset),
                thread_id=self._id("thread"),
                labels=["inbox", "VIP"],
                is_read=False,
            )
            vip_email_ids.append(email.id)
            base["emails"].append(email)

        # NEWER unread VIP email from first VIP contact — agent must find OLDEST (SW-5.1)
        base["emails"].append(
            self._email(
                from_name=vip_contacts[0].name,
                from_addr=vip_contacts[0].email,
                subject="Quick follow-up on the vendor recovery timeline",
                body=self._format_email_body(
                    "One more question on the vendor recovery timeline before tomorrow's exec sync.",
                    "If the risk posture changed after the last draft, I need to know whether procurement has already been looped in.",
                    signoff_name=self._first_name(vip_contacts[0].name),
                ),
                timestamp=self.now - timedelta(days=2, hours=2),
                thread_id=self._id("thread"),
                labels=["inbox", "VIP"],
                is_read=False,
            )
        )
        # Read VIP email — should NOT be starred or replied to
        base["emails"].append(
            self._email(
                from_name=vip_contacts[0].name,
                from_addr=vip_contacts[0].email,
                subject="Circling back on last week's board prep",
                body=self._format_email_body(
                    "Thanks for the earlier notes. The revised draft looks cleaner now.",
                    "No action needed from you on this one unless the numbers move again.",
                    signoff_name=self._first_name(vip_contacts[0].name),
                ),
                timestamp=self.now - timedelta(days=1, hours=6),
                thread_id=self._id("thread"),
                labels=["inbox", "VIP"],
                is_read=True,
            )
        )
        # Name confuser: similar name to first VIP, NOT a VIP, has unread email (SW-5.3)
        confuser_first = self._first_name(vip_contacts[0].name)
        confuser_name = f"{confuser_first} {self.fake.name().split()[-1]}"
        confuser_email = self._email_for_name(confuser_name, domain="confuser.test")
        confuser_contact = self._contact(
            name=confuser_name,
            email=confuser_email,
            is_vip=False,
            company="External Vendor",
        )
        base["contacts"].append(confuser_contact)
        base["emails"].append(
            self._email(
                from_name=confuser_name,
                from_addr=confuser_email,
                subject="Update on the vendor timeline",
                body=self._format_email_body(
                    "Wanted to share the latest vendor timeline revision before the review.",
                    "Let me know if anything looks off on your side.",
                    signoff_name=confuser_first,
                ),
                timestamp=self.now - timedelta(days=3),
                thread_id=self._id("thread"),
                labels=["inbox"],
                is_read=False,
            )
        )
        # Future VIP email
        base["emails"].append(
            self._email(
                from_name=future_vip_name,
                from_addr=future_vip_email,
                subject="Future priority escalation",
                body=self._format_email_body(
                    (
                        "I will be stepping into the executive sponsor role next quarter and will likely "
                        "send a few requests directly once the transition starts."
                    ),
                    "No action needed yet. I just wanted to introduce the address early.",
                    signoff_name=self._first_name(future_vip_name),
                ),
                timestamp=self.now - timedelta(days=1, hours=1),
                thread_id=self._id("thread"),
                labels=["inbox"],
            )
        )
        return {
            "vip_count": len(vip_email_ids),
            "vip_email_ids": vip_email_ids,
            "status_phrase": status_phrase,
            "future_vip_email": future_vip_email,
        }

    def _seed_gmail_morning_triage_extended(self, base: dict[str, Any]) -> dict[str, Any]:
        # --- Urgent A: end-of-day deadline ---
        urgent_a_name = self.fake.name()
        urgent_a_email = self._email_for_name(urgent_a_name, domain="vertexlab.test")
        urgent_a = self._email(
            from_name=urgent_a_name,
            from_addr=urgent_a_email,
            subject="Contract review before close of business",
            body=self._format_email_body(
                "I need this reviewed before end of day. The vendor is expecting our sign-back by tomorrow morning.",
                "Please prioritize this over the other items on your plate today.",
                signoff_name=self._first_name(urgent_a_name),
            ),
            timestamp=self.now - timedelta(hours=3),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        # --- Urgent B: needs sign-off ---
        urgent_b_name = self.fake.name()
        urgent_b_email = self._email_for_name(urgent_b_name, domain="procurement.test")
        urgent_b = self._email(
            from_name=urgent_b_name,
            from_addr=urgent_b_email,
            subject="Procurement approval — needs your sign-off",
            body=self._format_email_body(
                "The procurement order is ready to go but needs your sign-off before we proceed.",
                "Finance will not release the PO without your confirmation on file.",
                signoff_name=self._first_name(urgent_b_name),
            ),
            timestamp=self.now - timedelta(hours=5),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        # --- FYI decoy: looks urgent but is FYI only ---
        fyi_decoy_name = self.fake.name()
        fyi_decoy_email = self._email_for_name(fyi_decoy_name, domain="vertexlab.test")
        fyi_decoy = self._email(
            from_name=fyi_decoy_name,
            from_addr=fyi_decoy_email,
            subject="Urgent: Updated project timeline",
            body=self._format_email_body(
                "FYI only — no action needed from you. The project timeline was updated yesterday and I wanted you to have the latest version.",
                "Everything is on track and the team is handling the remaining items.",
                signoff_name=self._first_name(fyi_decoy_name),
            ),
            timestamp=self.now - timedelta(hours=4),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        # --- Promo: newsletter in Promotions tab ---
        promo_name = self.fake.company()
        promo_email = self._email_for_name(promo_name, domain="newsletters.test")
        promo = self._email(
            from_name=promo_name,
            from_addr=promo_email,
            subject="Weekly industry digest — top stories this week",
            body=self._format_email_body(
                "This week's top stories in operations and supply chain management.",
                "Unsubscribe at any time by clicking the link at the bottom of this email.",
                signoff_name=promo_name,
            ),
            timestamp=self.now - timedelta(hours=6),
            thread_id=self._id("thread"),
            labels=["inbox", "promotions"],
        )

        # --- FYI: general update in Primary ---
        fyi_name = self.fake.name()
        fyi_email_addr = self._email_for_name(fyi_name, domain="teamupdates.test")
        fyi = self._email(
            from_name=fyi_name,
            from_addr=fyi_email_addr,
            subject="Facilities update — no action needed",
            body=self._format_email_body(
                "Quick update: the office HVAC maintenance has been completed ahead of schedule.",
                "No action needed on your end. Just keeping you in the loop.",
                signoff_name=self._first_name(fyi_name),
            ),
            timestamp=self.now - timedelta(hours=7),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        # --- Forward target: loop in a colleague ---
        forward_sender_name = self.fake.name()
        forward_sender_email = self._email_for_name(forward_sender_name, domain="partners.test")
        colleague_name = self.fake.name()
        colleague_email = self._email_for_name(colleague_name, domain="engineering.test")
        forward_target = self._email(
            from_name=forward_sender_name,
            from_addr=forward_sender_email,
            subject="Integration spec needs engineering input",
            body=self._format_email_body(
                f"Could you please loop in {colleague_name} from engineering? They worked on the original integration spec and would know the current constraints.",
                "I think we can finalize the API contract once they weigh in on the rate limits.",
                signoff_name=self._first_name(forward_sender_name),
            ),
            timestamp=self.now - timedelta(hours=8),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        # --- Reply A: project update with CC (Reply All trap) ---
        reply_sender_name = self.fake.name()
        reply_sender_email = self._email_for_name(reply_sender_name, domain="projectmgmt.test")
        cc_a1 = self._email_for_name(self.fake.name(), domain="projectmgmt.test")
        cc_a2 = self._email_for_name(self.fake.name(), domain="projectmgmt.test")
        reply_phrase_a = "project update"
        reply_a = self._email(
            from_name=reply_sender_name,
            from_addr=reply_sender_email,
            subject=f"{self._initiative_name()} — project update",
            body=self._format_email_body(
                "Here is the latest project update. We are on track for the milestone next week.",
                "Let me know if any of the deliverables need to be reprioritized.",
                signoff_name=self._first_name(reply_sender_name),
            ),
            timestamp=self.now - timedelta(hours=9),
            thread_id=self._id("thread"),
            labels=["inbox"],
            cc=[cc_a1, cc_a2],
        )

        # --- Reply B: confirmation request ---
        reply_b_sender_name = self.fake.name()
        reply_b_sender_email = self._email_for_name(reply_b_sender_name, domain="logistics.test")
        reply_b = self._email(
            from_name=reply_b_sender_name,
            from_addr=reply_b_sender_email,
            subject="Shipment confirmation needed",
            body=self._format_email_body(
                "Could you confirm receipt of the Q1 shipment manifest?",
                "The warehouse team needs your acknowledgment before they release the next batch.",
                signoff_name=self._first_name(reply_b_sender_name),
            ),
            timestamp=self.now - timedelta(hours=10),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        base["emails"].extend([
            urgent_a, urgent_b, fyi_decoy, promo, fyi,
            forward_target, reply_a, reply_b,
        ])
        self._ensure_contact(base, urgent_a_name, urgent_a_email)
        self._ensure_contact(base, urgent_b_name, urgent_b_email)
        self._ensure_contact(base, forward_sender_name, forward_sender_email)
        self._ensure_contact(base, reply_sender_name, reply_sender_email)
        self._ensure_contact(base, reply_b_sender_name, reply_b_sender_email)
        self._ensure_contact(base, colleague_name, colleague_email)

        return {
            "urgent_a_id": urgent_a.id,
            "urgent_b_id": urgent_b.id,
            "fyi_decoy_id": fyi_decoy.id,
            "promo_id": promo.id,
            "fyi_id": fyi.id,
            "forward_id": forward_target.id,
            "forward_to_email": colleague_email,
            "reply_a_id": reply_a.id,
            "reply_sender_name": reply_sender_name,
            "reply_phrase_a": reply_phrase_a,
            "reply_b_id": reply_b.id,
            "reply_b_sender_name": reply_b_sender_name,
        }

    def _seed_gmail_meeting_negotiation(self, base: dict[str, Any]) -> dict[str, Any]:
        meeting_name = self._initiative_name()
        organizer_name = self.fake.name()
        organizer_email = self._email_for_name(organizer_name, domain="executive.test")

        # Five attendees with availability
        all_time_slots = [
            "Monday 9:00 AM", "Monday 2:00 PM",
            "Tuesday 10:00 AM", "Tuesday 3:00 PM",
            "Wednesday 11:00 AM", "Wednesday 1:00 PM",
            "Thursday 9:30 AM", "Thursday 2:30 PM",
            "Friday 10:00 AM", "Friday 4:00 PM",
        ]
        correct_time = self.rng.choice(all_time_slots)
        other_slots = [s for s in all_time_slots if s != correct_time]

        attendee_names: list[str] = []
        attendee_emails: list[str] = []
        domains = ["sales.test", "marketing.test", "finance.test", "ops.test", "product.test"]

        for i in range(5):
            name = self.fake.name()
            email = self._email_for_name(name, domain=domains[i])
            attendee_names.append(name)
            attendee_emails.append(email)

            # Each attendee has the correct_time plus 2-3 other random slots
            personal_others = self.rng.sample(other_slots, k=self.rng.randint(2, 3))
            available_slots = [correct_time] + personal_others
            self.rng.shuffle(available_slots)

            slot_lines = [f"{slot}" for slot in available_slots]
            base["emails"].append(
                self._email(
                    from_name=name,
                    from_addr=email,
                    subject=f"Re: {meeting_name} — my availability",
                    body=self._format_email_body(
                        f"Here are the times that work for me for the {meeting_name} meeting:",
                        self._bullet_lines(slot_lines),
                        "Let me know once a time is confirmed.",
                        signoff_name=self._first_name(name),
                    ),
                    timestamp=self.now - timedelta(days=2, hours=i * 2),
                    thread_id=self._id("thread"),
                    labels=["inbox"],
                )
            )
            self._ensure_contact(base, name, email)

        # Venue email — in Updates tab
        room_name = self.rng.choice(["Cascade Room", "Summit Hall", "Harbor Suite", "Cedar Boardroom"])
        venue_coordinator_name = self.fake.name()
        venue_coordinator_email = self._email_for_name(venue_coordinator_name, domain="facilities.test")

        # Room available at the correct_time plus one other slot
        venue_other_slot = self.rng.choice(other_slots)
        venue_availability = [correct_time, venue_other_slot]
        self.rng.shuffle(venue_availability)

        base["emails"].append(
            self._email(
                from_name=venue_coordinator_name,
                from_addr=venue_coordinator_email,
                subject=f"Room availability for {meeting_name}",
                body=self._format_email_body(
                    f"The {room_name} is available at the following times next week:",
                    self._bullet_lines(venue_availability),
                    "Please confirm which slot you would like to reserve and I will block the calendar.",
                    signoff_name=self._first_name(venue_coordinator_name),
                ),
                timestamp=self.now - timedelta(days=1, hours=6),
                thread_id=self._id("thread"),
                labels=["inbox", "updates"],
            )
        )
        self._ensure_contact(base, venue_coordinator_name, venue_coordinator_email)
        self._ensure_contact(base, organizer_name, organizer_email)

        return {
            "meeting_name": meeting_name,
            "organizer_email": organizer_email,
            "attendee_emails": attendee_emails,
            "correct_time": correct_time,
            "room_name": room_name,
        }

    def _seed_gmail_incident_escalation(self, base: dict[str, Any]) -> dict[str, Any]:
        alert_system_name = "System Alerts"
        alert_system_email = "alerts@monitoring.test"
        error_code = "ERR-5021"
        oncall_name = self.fake.name()
        oncall_email = self._email_for_name(oncall_name, domain="engineering.test")
        status_phrase = "I am actively triaging the incident."

        # Alert thread — 3 messages in same thread
        alert_thread_id = self._id("thread")
        alert_subject = "CRITICAL: Service degradation on payment gateway"

        # Message 1: initial alert (oldest)
        alert_msg_1 = self._email(
            from_name=alert_system_name,
            from_addr=alert_system_email,
            subject=alert_subject,
            body=self._format_email_body(
                "Automated alert: Payment gateway latency has exceeded 5000ms threshold.",
                "Multiple transaction failures detected across regions US-East and EU-West. Immediate investigation required.",
                signoff_name="Monitoring System",
            ),
            timestamp=self.now - timedelta(hours=4),
            thread_id=alert_thread_id,
            labels=["inbox", "updates"],
        )

        # Message 2: engineer mentions error code
        engineer_name = self.fake.name()
        engineer_email = self._email_for_name(engineer_name, domain="engineering.test")
        alert_msg_2 = self._email(
            from_name=engineer_name,
            from_addr=engineer_email,
            subject=f"Re: {alert_subject}",
            body=self._format_email_body(
                f"I checked the logs and the root cause appears to be error code {error_code} from the payment processor API.",
                "The circuit breaker tripped after the third consecutive timeout. We need to coordinate with the on-call engineer.",
                signoff_name=self._first_name(engineer_name),
            ),
            timestamp=self.now - timedelta(hours=3, minutes=30),
            thread_id=alert_thread_id,
            labels=["inbox", "updates"],
        )

        # Message 3: team member mentions on-call
        team_member_name = self.fake.name()
        team_member_email = self._email_for_name(team_member_name, domain="engineering.test")
        alert_msg_3 = self._email(
            from_name=team_member_name,
            from_addr=team_member_email,
            subject=f"Re: {alert_subject}",
            body=self._format_email_body(
                f"The on-call engineer for this rotation is {oncall_name} at {oncall_email}.",
                "They should have pager access and can roll back the gateway config if needed.",
                signoff_name=self._first_name(team_member_name),
            ),
            timestamp=self.now - timedelta(hours=3),
            thread_id=alert_thread_id,
            labels=["inbox", "updates"],
        )

        # Resolved follow-up — different thread, should NOT be forwarded
        resolved_alert = self._email(
            from_name=alert_system_name,
            from_addr=alert_system_email,
            subject="RESOLVED: Service degradation on payment gateway",
            body=self._format_email_body(
                "The payment gateway latency has returned to normal levels.",
                "All regions are reporting healthy response times. No further action required.",
                signoff_name="Monitoring System",
            ),
            timestamp=self.now - timedelta(hours=1),
            thread_id=self._id("thread"),
            labels=["inbox", "updates"],
            is_read=True,
        )

        # Manager thread — asking about incident status, CC'd to leadership
        manager_name = self.fake.name()
        manager_email = self._email_for_name(manager_name, domain="leadership.test")
        leadership_cc = [
            self._email_for_name(self.fake.name(), domain="leadership.test"),
            self._email_for_name(self.fake.name(), domain="leadership.test"),
            self._email_for_name(self.fake.name(), domain="leadership.test"),
        ]
        manager_thread_id = self._id("thread")
        manager_msg = self._email(
            from_name=manager_name,
            from_addr=manager_email,
            subject="Payment gateway incident — status check",
            body=self._format_email_body(
                "I saw the alert about the payment gateway degradation. Can you confirm you are handling this?",
                "The executive team needs a status update as soon as possible.",
                signoff_name=self._first_name(manager_name),
            ),
            timestamp=self.now - timedelta(hours=2, minutes=30),
            thread_id=manager_thread_id,
            labels=["inbox"],
            cc=leadership_cc,
        )

        incident_ids = [alert_msg_1.id, alert_msg_2.id, alert_msg_3.id]

        base["emails"].extend([
            alert_msg_1, alert_msg_2, alert_msg_3,
            resolved_alert, manager_msg,
        ])
        self._ensure_contact(base, alert_system_name, alert_system_email)
        self._ensure_contact(base, engineer_name, engineer_email)
        self._ensure_contact(base, team_member_name, team_member_email)
        self._ensure_contact(base, oncall_name, oncall_email)
        self._ensure_contact(base, manager_name, manager_email)

        return {
            "alert_id": alert_msg_1.id,
            "oncall_email": oncall_email,
            "error_code": error_code,
            "manager_email_id": manager_msg.id,
            "manager_name": manager_name,
            "status_phrase": status_phrase,
            "incident_ids": incident_ids,
            "alert_system_email": alert_system_email,
            "resolved_alert_id": resolved_alert.id,
        }

    def _seed_gmail_delegation_routing(self, base: dict[str, Any]) -> dict[str, Any]:
        # CFO target
        cfo_name = self.fake.name()
        cfo_email = self._email_for_name(cfo_name, domain="finance.test")

        # CTO target
        cto_name = self.fake.name()
        cto_email = self._email_for_name(cto_name, domain="engineering.test")

        # Support lead target
        support_lead_name = self.fake.name()
        support_lead_email = self._email_for_name(support_lead_name, domain="support.test")

        # Manager to BCC
        manager_name = self.fake.name()
        manager_email = self._email_for_name(manager_name, domain="leadership.test")

        # Budget question
        budget_sender_name = self.fake.name()
        budget_sender_email = self._email_for_name(budget_sender_name, domain="operations.test")
        budget_email = self._email(
            from_name=budget_sender_name,
            from_addr=budget_sender_email,
            subject="Q2 budget allocation question",
            body=self._format_email_body(
                f"We have a question about the Q2 budget allocation for the vendor program. I think the CFO should weigh in — {cfo_name} ({cfo_email}) would know whether the variance is within the approved range.",
                "Can you route this to the right person?",
                signoff_name=self._first_name(budget_sender_name),
            ),
            timestamp=self.now - timedelta(hours=4),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        # Technical issue
        tech_sender_name = self.fake.name()
        tech_sender_email = self._email_for_name(tech_sender_name, domain="operations.test")
        tech_email = self._email(
            from_name=tech_sender_name,
            from_addr=tech_sender_email,
            subject="API rate limiting issue on staging",
            body=self._format_email_body(
                f"We are hitting rate limits on the staging API. The CTO's team needs to review this — please forward to {cto_name} ({cto_email}) so they can adjust the throttle configuration.",
                "This is blocking the QA cycle for the next release.",
                signoff_name=self._first_name(tech_sender_name),
            ),
            timestamp=self.now - timedelta(hours=5),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        # Customer complaint
        complaint_sender_name = self.fake.name()
        complaint_sender_email = self._email_for_name(complaint_sender_name, domain="customers.test")
        complaint_email = self._email(
            from_name=complaint_sender_name,
            from_addr=complaint_sender_email,
            subject="Unresolved billing dispute — customer escalation",
            body=self._format_email_body(
                f"A customer has escalated a billing dispute that has been open for two weeks. This needs support lead review — please forward to {support_lead_name} ({support_lead_email}).",
                "The customer is threatening to cancel their contract if we do not resolve this by end of week.",
                signoff_name=self._first_name(complaint_sender_name),
            ),
            timestamp=self.now - timedelta(hours=2),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        # Decoy: looks like it needs forwarding but does not
        decoy_sender_name = self.fake.name()
        decoy_sender_email = self._email_for_name(decoy_sender_name, domain="crossteam.test")
        decoy_email = self._email(
            from_name=decoy_sender_name,
            from_addr=decoy_sender_email,
            subject="Cross-team alignment — Q2 planning",
            body=self._format_email_body(
                "Sharing the cross-team alignment doc for Q2 planning. No action needed — this is just for your awareness.",
                "The working group already signed off on the proposal last Friday.",
                signoff_name=self._first_name(decoy_sender_name),
            ),
            timestamp=self.now - timedelta(hours=6),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        all_ids = [budget_email.id, tech_email.id, complaint_email.id]

        base["emails"].extend([budget_email, tech_email, complaint_email, decoy_email])
        self._ensure_contact(base, budget_sender_name, budget_sender_email)
        self._ensure_contact(base, tech_sender_name, tech_sender_email)
        self._ensure_contact(base, complaint_sender_name, complaint_sender_email)
        self._ensure_contact(base, cfo_name, cfo_email)
        self._ensure_contact(base, cto_name, cto_email)
        self._ensure_contact(base, support_lead_name, support_lead_email)
        self._ensure_contact(base, manager_name, manager_email)

        return {
            "budget_id": budget_email.id,
            "tech_id": tech_email.id,
            "complaint_id": complaint_email.id,
            "decoy_id": decoy_email.id,
            "cfo_email": cfo_email,
            "cto_email": cto_email,
            "support_lead_email": support_lead_email,
            "manager_email": manager_email,
            "all_ids": all_ids,
        }

    def _seed_gmail_data_compilation(self, base: dict[str, Any]) -> dict[str, Any]:
        exec_name = self.fake.name()
        exec_email = self._email_for_name(exec_name, domain="executive.test")

        dept_names = ["Engineering", "Marketing", "Operations"]
        dept_domains = ["engineering.test", "marketing.test", "operations.test"]
        numbers = ["$142,500", "$89,000", "$215,750"]
        wrong_numbers = ["$138,200", "$91,500"]

        dept_head_names: list[str] = []
        dept_emails: list[str] = []

        # Dept A: Primary tab
        dept_a_name = self.fake.name()
        dept_a_email = self._email_for_name(dept_a_name, domain=dept_domains[0])
        dept_head_names.append(dept_a_name)
        dept_emails.append(dept_a_email)
        base["emails"].append(
            self._email(
                from_name=dept_a_name,
                from_addr=dept_a_email,
                subject=f"Q1 figures — {dept_names[0]}",
                body=self._format_email_body(
                    f"Here are the Q1 budget figures for {dept_names[0]}.",
                    f"Total Q1 spend: {numbers[0]}",
                    "Let me know if you need a breakdown by cost center.",
                    signoff_name=self._first_name(dept_a_name),
                ),
                timestamp=self.now - timedelta(days=2, hours=3),
                thread_id=self._id("thread"),
                labels=["inbox"],
            )
        )

        # Dept B: Updates tab
        dept_b_name = self.fake.name()
        dept_b_email = self._email_for_name(dept_b_name, domain=dept_domains[1])
        dept_head_names.append(dept_b_name)
        dept_emails.append(dept_b_email)
        base["emails"].append(
            self._email(
                from_name=dept_b_name,
                from_addr=dept_b_email,
                subject=f"Q1 figures — {dept_names[1]}",
                body=self._format_email_body(
                    f"Attached are the Q1 budget numbers for {dept_names[1]}.",
                    f"Our total Q1 spend came in at {numbers[1]}.",
                    "Happy to walk through the details on our next call.",
                    signoff_name=self._first_name(dept_b_name),
                ),
                timestamp=self.now - timedelta(days=3, hours=5),
                thread_id=self._id("thread"),
                labels=["inbox", "updates"],
            )
        )

        # Dept C: old email (10+ days ago, will be on page 2+)
        dept_c_name = self.fake.name()
        dept_c_email = self._email_for_name(dept_c_name, domain=dept_domains[2])
        dept_head_names.append(dept_c_name)
        dept_emails.append(dept_c_email)
        base["emails"].append(
            self._email(
                from_name=dept_c_name,
                from_addr=dept_c_email,
                subject=f"Q1 figures — {dept_names[2]}",
                body=self._format_email_body(
                    f"Sending the Q1 budget summary for {dept_names[2]}.",
                    f"Final Q1 number: {numbers[2]}",
                    "This includes the warehouse expansion costs that were approved in January.",
                    signoff_name=self._first_name(dept_c_name),
                ),
                timestamp=self.now - timedelta(days=12, hours=2),
                thread_id=self._id("thread"),
                labels=["inbox"],
                is_read=True,
            )
        )

        # Decoy emails with wrong numbers from similar departments
        decoy_a_name = self.fake.name()
        decoy_a_email = self._email_for_name(decoy_a_name, domain="engineering.test")
        base["emails"].append(
            self._email(
                from_name=decoy_a_name,
                from_addr=decoy_a_email,
                subject="Q1 preliminary estimates — Engineering (DRAFT)",
                body=self._format_email_body(
                    "These are preliminary estimates only — please do not use for the final report.",
                    f"Draft estimate: {wrong_numbers[0]}",
                    "The final numbers will come from the department head directly.",
                    signoff_name=self._first_name(decoy_a_name),
                ),
                timestamp=self.now - timedelta(days=5, hours=1),
                thread_id=self._id("thread"),
                labels=["inbox"],
                is_read=True,
            )
        )

        decoy_b_name = self.fake.name()
        decoy_b_email = self._email_for_name(decoy_b_name, domain="marketing.test")
        base["emails"].append(
            self._email(
                from_name=decoy_b_name,
                from_addr=decoy_b_email,
                subject="Q1 reforecast — Marketing (superseded)",
                body=self._format_email_body(
                    "Ignore this earlier reforecast — the final numbers were sent separately by the department head.",
                    f"Outdated figure: {wrong_numbers[1]}",
                    signoff_name=self._first_name(decoy_b_name),
                ),
                timestamp=self.now - timedelta(days=7, hours=3),
                thread_id=self._id("thread"),
                labels=["inbox"],
                is_read=True,
            )
        )

        self._ensure_contact(base, exec_name, exec_email)
        for name, email in zip(dept_head_names, dept_emails):
            self._ensure_contact(base, name, email)

        return {
            "exec_email": exec_email,
            "dept_emails": dept_emails,
            "dept_a_name": dept_a_name,
            "dept_b_name": dept_b_name,
            "dept_c_name": dept_c_name,
            "number_a": numbers[0],
            "number_b": numbers[1],
            "number_c": numbers[2],
            "wrong_numbers": wrong_numbers,
        }

    def _seed_gmail_subscription_cleanup(self, base: dict[str, Any]) -> dict[str, Any]:
        newsletter_domain_a = "weeklydigest.test"
        newsletter_domain_b = "techinsights.test"
        personal_email = "avery.personal@personal-mail.test"
        good_newsletter_topic = "AI in supply chain management"

        # 4 newsletter emails in Promotions tab
        promo_ids: list[str] = []
        newsletter_senders = [
            ("Weekly Digest", f"editor@{newsletter_domain_a}", "Your weekly operations roundup"),
            ("Tech Insights", f"newsletter@{newsletter_domain_b}", "New trends in enterprise tooling"),
            ("Market Watch", "alerts@marketwatch.test", "Industry benchmarks for Q1"),
            ("Supply Chain Today", "news@supplychain.test", f"How AI is transforming supply chain management"),
        ]
        good_newsletter_id: str | None = None
        for idx, (sender_name, sender_addr, subject) in enumerate(newsletter_senders):
            body_text = (
                f"This week we cover the latest developments in operations and technology. "
                f"Featured: {subject.lower()}."
            )
            if "supply chain" in subject.lower():
                body_text = (
                    f"In this issue: a deep dive into {good_newsletter_topic}. We explore how modern "
                    "logistics teams are using machine learning to optimize inventory forecasting and "
                    "reduce waste across regional distribution centers."
                )
            email = self._email(
                from_name=sender_name,
                from_addr=sender_addr,
                subject=subject,
                body=self._format_email_body(body_text, signoff_name=sender_name),
                timestamp=self.now - timedelta(days=2, hours=idx * 3),
                thread_id=self._id("thread"),
                labels=["inbox", "promotions"],
            )
            promo_ids.append(email.id)
            if "supply chain" in subject.lower():
                good_newsletter_id = email.id
            base["emails"].append(email)

        # 2 automated notification emails in Updates tab
        update_ids: list[str] = []
        update_senders = [
            ("CI Build System", "builds@ci-pipeline.test", "Build #4821 completed successfully"),
            ("Monitoring Alerts", "noreply@statuspage.test", "Weekly uptime report — all services green"),
        ]
        for idx, (sender_name, sender_addr, subject) in enumerate(update_senders):
            email = self._email(
                from_name=sender_name,
                from_addr=sender_addr,
                subject=subject,
                body=self._format_email_body(
                    f"Automated notification: {subject}.",
                    "This is an automated message. No reply is necessary.",
                    signoff_name=sender_name,
                ),
                timestamp=self.now - timedelta(days=1, hours=idx * 4),
                thread_id=self._id("thread"),
                labels=["inbox", "updates"],
            )
            update_ids.append(email.id)
            base["emails"].append(email)

        # 2 spam emails with suspicious subjects
        spam_ids: list[str] = []
        spam_entries = [
            ("Prize Center", "winner@free-prizes.test", "You've won a free laptop! Claim now!"),
            ("Rewards Hub", "gifts@reward-center.test", "Claim your $500 gift card now — act fast!"),
        ]
        for idx, (sender_name, sender_addr, subject) in enumerate(spam_entries):
            email = self._email(
                from_name=sender_name,
                from_addr=sender_addr,
                subject=subject,
                body=self._format_email_body(
                    f"Congratulations! {subject} Click the link below to redeem your reward.",
                    "This offer expires in 24 hours. Do not miss out!",
                    signoff_name=sender_name,
                ),
                timestamp=self.now - timedelta(days=1, hours=idx * 2 + 1),
                thread_id=self._id("thread"),
                labels=["inbox", "promotions"],
            )
            spam_ids.append(email.id)
            base["emails"].append(email)

        return {
            "promo_ids": promo_ids,
            "update_ids": update_ids,
            "good_newsletter_id": good_newsletter_id,
            "good_newsletter_topic": good_newsletter_topic,
            "personal_email": personal_email,
            "spam_ids": spam_ids,
            "newsletter_domain_a": newsletter_domain_a,
            "newsletter_domain_b": newsletter_domain_b,
        }

    def _seed_gmail_vacation_preparation(self, base: dict[str, Any]) -> dict[str, Any]:
        vacation_message = "I am out of office until March 21. For urgent matters, contact my backup."
        ooo_note = "OOO until March 21"
        boss_name = self.fake.name()
        boss_email = self._email_for_name(boss_name, domain="executive.test")
        backup_name = self.fake.name()
        backup_email = self._email_for_name(backup_name, domain="ops-backup.test")

        # Pending A: vendor proposal
        pending_a_sender = self.fake.name()
        pending_a_email = self._email_for_name(pending_a_sender, domain="vendors.test")
        pending_a = self._email(
            from_name=pending_a_sender,
            from_addr=pending_a_email,
            subject="Vendor proposal for Q2 office supplies",
            body=self._format_email_body(
                "Attached is the vendor proposal for Q2 office supplies. Could you review the pricing and "
                "confirm whether we should move forward?",
                "Please follow up when you're back — I know you have a lot on your plate before vacation.",
                signoff_name=self._first_name(pending_a_sender),
            ),
            timestamp=self.now - timedelta(days=2, hours=3),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        # Pending B: timeline email with CC (Reply All trap)
        pending_b_sender = self.fake.name()
        pending_b_email = self._email_for_name(pending_b_sender, domain="projectmgmt.test")
        cc_b1 = self._email_for_name(self.fake.name(), domain="projectmgmt.test")
        cc_b2 = self._email_for_name(self.fake.name(), domain="projectmgmt.test")
        pending_b = self._email(
            from_name=pending_b_sender,
            from_addr=pending_b_email,
            subject="Project timeline for the infrastructure rollout",
            body=self._format_email_body(
                "Here is the updated timeline for the infrastructure rollout. Can you confirm you are "
                "aligned on the milestones?",
                "I need to follow up when you're back on the resource allocation for phase 2.",
                signoff_name=self._first_name(pending_b_sender),
            ),
            timestamp=self.now - timedelta(days=1, hours=6),
            thread_id=self._id("thread"),
            labels=["inbox"],
            cc=[cc_b1, cc_b2],
        )

        # Pending C: attendance confirmation
        pending_c_sender = self.fake.name()
        pending_c_email = self._email_for_name(pending_c_sender, domain="events.test")
        pending_c = self._email(
            from_name=pending_c_sender,
            from_addr=pending_c_email,
            subject="Confirm attendance for the leadership retreat",
            body=self._format_email_body(
                "Please confirm whether you will attend the leadership retreat on March 25.",
                "We need final headcounts by end of week.",
                signoff_name=self._first_name(pending_c_sender),
            ),
            timestamp=self.now - timedelta(days=1, hours=2),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        # The return_ids are pending_a and pending_b (they mention "follow up when you're back")
        return_ids = [pending_a.id, pending_b.id]

        base["emails"].extend([pending_a, pending_b, pending_c])
        self._ensure_contact(base, pending_a_sender, pending_a_email)
        self._ensure_contact(base, pending_b_sender, pending_b_email)
        self._ensure_contact(base, pending_c_sender, pending_c_email)
        self._ensure_contact(base, boss_name, boss_email, is_vip=True)
        self._ensure_contact(base, backup_name, backup_email)

        return {
            "vacation_message": vacation_message,
            "ooo_note": ooo_note,
            "boss_email": boss_email,
            "backup_email": backup_email,
            "pending_a_sender": pending_a_sender,
            "pending_a_id": pending_a.id,
            "pending_b_sender": pending_b_sender,
            "pending_b_id": pending_b.id,
            "pending_c_sender": pending_c_sender,
            "pending_c_id": pending_c.id,
            "return_ids": return_ids,
        }

    def _seed_gmail_contact_audit(self, base: dict[str, Any]) -> dict[str, Any]:
        # 4 stale contacts (35-60 days since last contact)
        stale_contacts = []
        stale_days = [35, 42, 50, 60]
        for days in stale_days:
            contact = self._contact(
                name=self.fake.name(),
                email=self.fake.email(domain="oldvendor.test"),
                last_contacted_at=self.now - timedelta(days=days),
            )
            stale_contacts.append(contact)

        # 2 near-threshold contacts (22-28 days, should NOT be deleted)
        near_threshold_a = self._contact(
            name=self.fake.name(),
            email=self.fake.email(domain="recentpartner.test"),
            last_contacted_at=self.now - timedelta(days=22),
        )
        near_threshold_b = self._contact(
            name=self.fake.name(),
            email=self.fake.email(domain="borderline.test"),
            last_contacted_at=self.now - timedelta(days=28),
        )

        # 1 keep contact (5 days, explicitly named in instruction)
        keep_contact = self._contact(
            name=self.fake.name(),
            email=self.fake.email(domain="activeteam.test"),
            last_contacted_at=self.now - timedelta(days=5),
        )

        base["contacts"].extend(
            stale_contacts + [near_threshold_a, near_threshold_b, keep_contact]
        )

        # 2 emails from people NOT in contacts
        new_contact_a_name = self.fake.name()
        new_a_email = self._email_for_name(new_contact_a_name, domain="newpartner.test")
        new_contact_b_name = self.fake.name()
        new_b_email = self._email_for_name(new_contact_b_name, domain="consultant.test")

        base["emails"].extend([
            self._email(
                from_name=new_contact_a_name,
                from_addr=new_a_email,
                subject="Partnership opportunity — Q2 logistics",
                body=self._format_email_body(
                    f"Hi Avery, my name is {new_contact_a_name} and I work at NewPartner Logistics. "
                    "I would love to discuss a potential partnership for Q2.",
                    f"You can reach me at {new_a_email} or on my direct line.",
                    signoff_name=self._first_name(new_contact_a_name),
                ),
                timestamp=self.now - timedelta(days=1, hours=3),
                thread_id=self._id("thread"),
                labels=["inbox"],
            ),
            self._email(
                from_name=new_contact_b_name,
                from_addr=new_b_email,
                subject="Consulting engagement follow-up",
                body=self._format_email_body(
                    f"Hi Avery, this is {new_contact_b_name} from the consulting engagement last month. "
                    "I wanted to follow up on the deliverables we discussed.",
                    f"My email is {new_b_email} — feel free to add me to your contacts for future correspondence.",
                    signoff_name=self._first_name(new_contact_b_name),
                ),
                timestamp=self.now - timedelta(days=2, hours=5),
                thread_id=self._id("thread"),
                labels=["inbox"],
            ),
        ])

        return {
            "stale_1_id": stale_contacts[0].id,
            "stale_2_id": stale_contacts[1].id,
            "stale_3_id": stale_contacts[2].id,
            "stale_4_id": stale_contacts[3].id,
            "near_id": near_threshold_a.id,
            "keep_contact_name": keep_contact.name,
            "new_contact_a_name": new_contact_a_name,
            "new_contact_b_name": new_contact_b_name,
            "new_a_email": new_a_email,
            "new_b_email": new_b_email,
        }

    def _seed_gmail_thread_archaeology(self, base: dict[str, Any]) -> dict[str, Any]:
        thread_subject = f"{self._initiative_name()} action items"
        thread_id = self._id("thread")
        assignee_name = self.fake.name()
        assignee_email = self._email_for_name(assignee_name, domain="teamlead.test")
        manager_name = self.fake.name()
        manager_email = self._email_for_name(manager_name, domain="management.test")
        wrong_person_name = self.fake.name()
        wrong_person_email = self._email_for_name(wrong_person_name, domain="crossteam.test")
        deadline = "March 20"

        # Generate 5 different senders for the thread messages
        sender_names = [self.fake.name() for _ in range(5)]
        sender_emails = [
            self._email_for_name(n, domain="projectteam.test") for n in sender_names
        ]

        # Message 1 (oldest): initial discussion
        msg_1 = self._email(
            from_name=sender_names[0],
            from_addr=sender_emails[0],
            subject=thread_subject,
            body=self._format_email_body(
                f"Kicking off the discussion on the {thread_subject}. We need to identify owners for "
                "each deliverable and set clear deadlines.",
                "I will send a follow-up once we hear back from everyone.",
                signoff_name=self._first_name(sender_names[0]),
            ),
            timestamp=self.now - timedelta(days=5, hours=10),
            thread_id=thread_id,
            labels=["inbox"],
        )

        # Message 2: mentions the deadline
        msg_2 = self._email(
            from_name=sender_names[1],
            from_addr=sender_emails[1],
            subject=f"Re: {thread_subject}",
            body=self._format_email_body(
                f"The key deliverable needs to be completed by {deadline}. That is our hard deadline "
                "from the steering committee.",
                "We should make sure whoever owns this has enough runway to finish on time.",
                signoff_name=self._first_name(sender_names[1]),
            ),
            timestamp=self.now - timedelta(days=4, hours=8),
            thread_id=thread_id,
            labels=["inbox"],
        )

        # Message 3: assigns action item to assignee
        msg_3 = self._email(
            from_name=sender_names[2],
            from_addr=sender_emails[2],
            subject=f"Re: {thread_subject}",
            body=self._format_email_body(
                f"I think {assignee_name} should take point on this. They have the most context on the "
                "integration work and can coordinate with the vendor directly.",
                f"Their email is {assignee_email} if you need to reach out.",
                signoff_name=self._first_name(sender_names[2]),
            ),
            timestamp=self.now - timedelta(days=3, hours=6),
            thread_id=thread_id,
            labels=["inbox"],
        )

        # Message 4: mentions manager for visibility
        msg_4 = self._email(
            from_name=sender_names[3],
            from_addr=sender_emails[3],
            subject=f"Re: {thread_subject}",
            body=self._format_email_body(
                f"Loop in {manager_name} for visibility — they should be aware of the timeline and "
                "resource commitment.",
                f"Their address is {manager_email}.",
                signoff_name=self._first_name(sender_names[3]),
            ),
            timestamp=self.now - timedelta(days=2, hours=4),
            thread_id=thread_id,
            labels=["inbox"],
        )

        # Message 5: side discussion with WRONG person mentioned (confuser)
        msg_5 = self._email(
            from_name=sender_names[4],
            from_addr=sender_emails[4],
            subject=f"Re: {thread_subject}",
            body=self._format_email_body(
                f"By the way, {wrong_person_name} mentioned they might have bandwidth to help with "
                "the secondary tasks, but I do not think they should own the main action item.",
                f"Their address is {wrong_person_email} if needed for the side tasks.",
                signoff_name=self._first_name(sender_names[4]),
            ),
            timestamp=self.now - timedelta(days=1, hours=8),
            thread_id=thread_id,
            labels=["inbox"],
        )

        # Message 6 (newest, auto-expanded): general follow-up, no critical info
        msg_6 = self._email(
            from_name=sender_names[0],
            from_addr=sender_emails[0],
            subject=f"Re: {thread_subject}",
            body=self._format_email_body(
                "Just bumping this thread to keep it visible. Can someone confirm ownership and next "
                "steps so we can close the planning phase?",
                "I will check back at the end of the week if I do not hear anything.",
                signoff_name=self._first_name(sender_names[0]),
            ),
            timestamp=self.now - timedelta(hours=6),
            thread_id=thread_id,
            labels=["inbox"],
        )

        base["emails"].extend([msg_1, msg_2, msg_3, msg_4, msg_5, msg_6])
        for name, email in zip(sender_names, sender_emails):
            self._ensure_contact(base, name, email)
        self._ensure_contact(base, assignee_name, assignee_email)
        self._ensure_contact(base, manager_name, manager_email)
        self._ensure_contact(base, wrong_person_name, wrong_person_email)

        return {
            "thread_subject": thread_subject,
            "thread_email_id": msg_6.id,
            "assignee_email": assignee_email,
            "assignee_name": assignee_name,
            "manager_email": manager_email,
            "manager_name": manager_name,
            "deadline": deadline,
            "wrong_person_email": wrong_person_email,
        }

    def _seed_gmail_filter_overhaul(self, base: dict[str, Any]) -> dict[str, Any]:
        correct_domain = "billing-services.test"
        wrong_domain = "wrong-billing.test"
        billing_label = "Billing"
        keyword = "Security Advisory"
        keyword_label = "Security"
        archive_domain = "marketing-blasts.test"
        forward_sender_name = self.fake.name()
        forward_sender = self._email_for_name(forward_sender_name, domain="executive.test")
        forward_to = "chief-of-staff@webagentbench.test"

        # Pre-seed 3 existing filters
        broken_filter = FilterRule(
            id=self._id("filter"),
            name="Billing auto-archive",
            query=f"from:@{wrong_domain}",
            from_addresses=[f"*@{wrong_domain}"],
            archive=True,
            add_labels=["Billing"],
        )
        good_filter_a = FilterRule(
            id=self._id("filter"),
            name="Newsletter archive",
            query="from:@newsletters.test",
            from_addresses=["*@newsletters.test"],
            archive=True,
            mark_read=True,
        )
        good_filter_b = FilterRule(
            id=self._id("filter"),
            name="Team notifications star",
            query="from:@teamnotify.test",
            from_addresses=["*@teamnotify.test"],
            star=True,
        )
        base["filters"].extend([broken_filter, good_filter_a, good_filter_b])

        # Emails in inbox matching the patterns the new filters should catch
        base["emails"].extend([
            # Billing email from the correct domain
            self._email(
                from_name="Billing Services",
                from_addr=f"invoices@{correct_domain}",
                subject="March invoice batch ready for review",
                body=self._format_email_body(
                    "The March invoice batch is ready. Please review and approve before end of week.",
                    signoff_name="Billing Services",
                ),
                timestamp=self.now - timedelta(days=1, hours=3),
                thread_id=self._id("thread"),
                labels=["inbox", "updates"],
            ),
            # Another billing email from correct domain
            self._email(
                from_name="Billing Services",
                from_addr=f"statements@{correct_domain}",
                subject="Q1 billing statement",
                body=self._format_email_body(
                    "Your Q1 billing statement is attached for your records.",
                    signoff_name="Billing Services",
                ),
                timestamp=self.now - timedelta(days=3, hours=2),
                thread_id=self._id("thread"),
                labels=["inbox", "updates"],
            ),
            # Security advisory email
            self._email(
                from_name="Security Team",
                from_addr="security@infosec.test",
                subject=f"{keyword}: Critical vulnerability in authentication module",
                body=self._format_email_body(
                    "A critical vulnerability has been identified in the authentication module. "
                    "Please review the attached advisory and apply patches within 48 hours.",
                    signoff_name="Security Team",
                ),
                timestamp=self.now - timedelta(hours=8),
                thread_id=self._id("thread"),
                labels=["inbox"],
            ),
            # Marketing blast emails
            self._email(
                from_name="Marketing Automation",
                from_addr=f"campaigns@{archive_domain}",
                subject="Spring campaign results — weekly digest",
                body=self._format_email_body(
                    "Here is the weekly digest of spring campaign performance metrics.",
                    signoff_name="Marketing Automation",
                ),
                timestamp=self.now - timedelta(days=1, hours=7),
                thread_id=self._id("thread"),
                labels=["inbox", "promotions"],
            ),
            self._email(
                from_name="Marketing Automation",
                from_addr=f"updates@{archive_domain}",
                subject="New lead scoring model deployed",
                body=self._format_email_body(
                    "The updated lead scoring model is now live in the CRM dashboard.",
                    signoff_name="Marketing Automation",
                ),
                timestamp=self.now - timedelta(days=2, hours=5),
                thread_id=self._id("thread"),
                labels=["inbox", "promotions"],
            ),
            # Email from the executive to forward
            self._email(
                from_name=forward_sender_name,
                from_addr=forward_sender,
                subject="Board prep materials — confidential",
                body=self._format_email_body(
                    "Sharing the board prep materials ahead of next week's meeting. Please keep these "
                    "confidential and route through my chief of staff.",
                    signoff_name=self._first_name(forward_sender_name),
                ),
                timestamp=self.now - timedelta(hours=4),
                thread_id=self._id("thread"),
                labels=["inbox"],
            ),
        ])

        self._ensure_contact(base, forward_sender_name, forward_sender, is_vip=True)

        return {
            "broken_filter_id": broken_filter.id,
            "correct_domain": correct_domain,
            "wrong_domain": wrong_domain,
            "billing_label": billing_label,
            "keyword": keyword,
            "keyword_label": keyword_label,
            "archive_domain": archive_domain,
            "forward_sender": forward_sender,
            "forward_to": forward_to,
            "good_filter_a_id": good_filter_a.id,
            "good_filter_b_id": good_filter_b.id,
        }

    # ── Task 11 ─────────────────────────────────────────────────────────
    def _seed_gmail_budget_reconciliation(self, base: dict[str, Any]) -> dict[str, Any]:
        dept_a_name = self.fake.name()
        dept_b_name = self.fake.name()
        dept_c_name = self.fake.name()
        summary_author_name = self.fake.name()

        dept_a_email = self._email_for_name(dept_a_name, domain="engineering.test")
        dept_b_email = self._email_for_name(dept_b_name, domain="marketing.test")
        dept_c_email = self._email_for_name(dept_c_name, domain="operations.test")
        summary_author_email = self._email_for_name(summary_author_name, domain="finance.test")

        cfo_email = "cfo@executive.test"
        board_cc = [cfo_email, "board-a@executive.test", "board-b@executive.test"]

        dept_a_dept = "Engineering"
        dept_b_dept = "Marketing"
        dept_c_dept = "Operations"

        # Department emails with correct figures
        dept_a_email_obj = self._email(
            from_name=dept_a_name,
            from_addr=dept_a_email,
            subject=f"Q1 {dept_a_dept} budget figures",
            body=self._format_email_body(
                f"Here are the final Q1 numbers for {dept_a_dept}.",
                f"Total spend: $142,500. This covers salaries, tooling, and infrastructure.",
                signoff_name=self._first_name(dept_a_name),
            ),
            timestamp=self.now - timedelta(days=3, hours=4),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )
        dept_b_email_obj = self._email(
            from_name=dept_b_name,
            from_addr=dept_b_email,
            subject=f"Q1 {dept_b_dept} budget figures",
            body=self._format_email_body(
                f"Attached are the Q1 {dept_b_dept} figures as requested.",
                f"Our total for the quarter: $89,000. Includes campaign spend, events, and agency fees.",
                signoff_name=self._first_name(dept_b_name),
            ),
            timestamp=self.now - timedelta(days=3, hours=2),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )
        dept_c_email_obj = self._email(
            from_name=dept_c_name,
            from_addr=dept_c_email,
            subject=f"Q1 {dept_c_dept} budget figures",
            body=self._format_email_body(
                f"Q1 {dept_c_dept} numbers below.",
                f"Total: $215,750. Covers facilities, logistics, and vendor contracts.",
                signoff_name=self._first_name(dept_c_name),
            ),
            timestamp=self.now - timedelta(days=3, hours=1),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        # Summary email with 2 wrong numbers (Reply All trap via CC)
        summary_email = self._email(
            from_name=summary_author_name,
            from_addr=summary_author_email,
            subject="Q1 Budget Summary — please verify",
            body=self._format_email_body(
                "I compiled the Q1 figures from all three departments. Please review:",
                (
                    f"- {dept_a_dept}: $142,500\n"
                    f"- {dept_b_dept}: $98,000\n"
                    f"- {dept_c_dept}: $205,750"
                ),
                "Let me know if anything looks off before I send the final version to the board.",
                signoff_name=self._first_name(summary_author_name),
            ),
            timestamp=self.now - timedelta(days=2, hours=6),
            thread_id=self._id("thread"),
            labels=["inbox"],
            cc=board_cc,
        )

        base["emails"].extend([
            dept_a_email_obj, dept_b_email_obj, dept_c_email_obj, summary_email,
        ])
        self._ensure_contact(base, dept_a_name, dept_a_email)
        self._ensure_contact(base, dept_b_name, dept_b_email)
        self._ensure_contact(base, dept_c_name, dept_c_email)
        self._ensure_contact(base, summary_author_name, summary_author_email)

        dept_ids = [dept_a_email_obj.id, dept_b_email_obj.id, dept_c_email_obj.id]
        all_budget_ids = dept_ids + [summary_email.id]

        return {
            "dept_a_name": dept_a_name,
            "dept_a_dept": dept_a_dept,
            "dept_b_name": dept_b_name,
            "dept_b_dept": dept_b_dept,
            "dept_c_name": dept_c_name,
            "dept_c_dept": dept_c_dept,
            "summary_author_name": summary_author_name,
            "summary_author_email": summary_author_email,
            "summary_id": summary_email.id,
            "dept_ids": dept_ids,
            "all_budget_ids": all_budget_ids,
            "correct_value_1": "$89,000",
            "correct_value_2": "$215,750",
            "wrong_values": ["$98,000", "$205,750"],
        }

    # ── Task 12 ─────────────────────────────────────────────────────────
    def _seed_gmail_label_workflow_setup(self, base: dict[str, Any]) -> dict[str, Any]:
        client_domain = "client.test"
        client_a_name = self.fake.name()
        client_b_name = self.fake.name()
        client_a_email = self._email_for_name(client_a_name, domain=client_domain)
        client_b_email = self._email_for_name(client_b_name, domain=client_domain)

        # 2 client emails
        client_email_a = self._email(
            from_name=client_a_name,
            from_addr=client_a_email,
            subject="Client deliverable feedback",
            body=self._format_email_body(
                "We reviewed the latest deliverable and have a few notes.",
                "Overall the direction looks good. A couple of items need adjustment before sign-off.",
                signoff_name=self._first_name(client_a_name),
            ),
            timestamp=self.now - timedelta(days=2, hours=3),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )
        client_email_b = self._email(
            from_name=client_b_name,
            from_addr=client_b_email,
            subject="Client contract renewal",
            body=self._format_email_body(
                "Sending the updated contract terms for review.",
                "Please confirm the revised pricing before end of week.",
                signoff_name=self._first_name(client_b_name),
            ),
            timestamp=self.now - timedelta(days=1, hours=5),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        # 3 emails with "review" in subject (2 legit, 1 wrong)
        review_a_name = self.fake.name()
        review_a_email = self._email_for_name(review_a_name, domain="internal.test")
        review_email_a = self._email(
            from_name=review_a_name,
            from_addr=review_a_email,
            subject="Code review for sprint 12",
            body=self._format_email_body(
                "The code review for sprint 12 is ready.",
                "Please take a look at the pull requests when you have a chance.",
                signoff_name=self._first_name(review_a_name),
            ),
            timestamp=self.now - timedelta(days=3, hours=1),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        review_b_name = self.fake.name()
        review_b_email = self._email_for_name(review_b_name, domain="internal.test")
        review_email_b = self._email(
            from_name=review_b_name,
            from_addr=review_b_email,
            subject="Design review notes",
            body=self._format_email_body(
                "Sharing the design review notes from yesterday's session.",
                "The team agreed on the main layout changes and the color palette.",
                signoff_name=self._first_name(review_b_name),
            ),
            timestamp=self.now - timedelta(days=2, hours=7),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        # Wrong review — leisure book review, should NOT keep Needs Review
        wrong_review_name = self.fake.name()
        wrong_review_email = self._email_for_name(wrong_review_name, domain="personal.test")
        wrong_review_subject = "Book review for leisure reading club"
        wrong_review_email_obj = self._email(
            from_name=wrong_review_name,
            from_addr=wrong_review_email,
            subject=wrong_review_subject,
            body=self._format_email_body(
                "Here is my review of the book we discussed at the leisure reading club.",
                "I thought the narrative arc was strong but the ending felt rushed.",
                signoff_name=self._first_name(wrong_review_name),
            ),
            timestamp=self.now - timedelta(days=4, hours=2),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        # A non-review email that should never get Needs Review label
        non_review_name = self.fake.name()
        non_review_email_addr = self._email_for_name(non_review_name, domain="logistics.test")
        non_review_email_obj = self._email(
            from_name=non_review_name,
            from_addr=non_review_email_addr,
            subject="Shipping schedule update",
            body=self._format_email_body(
                "The shipping schedule has been updated for next week.",
                "All items are on track for delivery by Friday.",
                signoff_name=self._first_name(non_review_name),
            ),
            timestamp=self.now - timedelta(days=1, hours=2),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        base["emails"].extend([
            client_email_a, client_email_b,
            review_email_a, review_email_b, wrong_review_email_obj,
            non_review_email_obj,
        ])

        client_email_ids = [client_email_a.id, client_email_b.id]
        # All project emails: client emails + real review emails + wrong review (all have "review" in subject)
        project_email_ids = client_email_ids + [
            review_email_a.id, review_email_b.id, wrong_review_email_obj.id,
        ]

        return {
            "client_domain": client_domain,
            "client_email_ids": client_email_ids,
            "wrong_review_subject": wrong_review_subject,
            "wrong_review_id": wrong_review_email_obj.id,
            "correct_non_review_id": non_review_email_obj.id,
            "project_email_ids": project_email_ids,
        }

    # ── Task 13 ─────────────────────────────────────────────────────────
    def _seed_gmail_phishing_investigation(self, base: dict[str, Any]) -> dict[str, Any]:
        security_team_email = "security-team@company.test"
        phishing_domain = "phishing-domain.test"

        # Legit A
        legit_a = self._email(
            from_name="IT Department",
            from_addr="it-support@company.test",
            subject="Security patch ready for deployment",
            body=self._format_email_body(
                "The latest security patch is ready for deployment. Please review the attached documentation.",
                "We will proceed with the rollout on Monday unless there are objections.",
                signoff_name="IT Department",
            ),
            timestamp=self.now - timedelta(days=1, hours=6),
            thread_id=self._id("thread"),
            labels=["inbox"],
            is_read=False,
            attachments=[self._attachment("security-update.pdf", "application/pdf", "pdf")],
        )

        # Legit B
        legit_b = self._email(
            from_name="HR Team",
            from_addr="hr@company.test",
            subject="Updated benefits guide for Q2",
            body=self._format_email_body(
                "Please find the updated benefits guide for Q2 attached.",
                "The main changes are to the dental and vision plans. Open enrollment closes Friday.",
                signoff_name="HR Team",
            ),
            timestamp=self.now - timedelta(days=1, hours=4),
            thread_id=self._id("thread"),
            labels=["inbox"],
            is_read=False,
            attachments=[self._attachment("benefits-guide.pdf", "application/pdf", "pdf")],
        )

        # Phishing A — name says "IT Department" but address is phishing domain
        phishing_subject_a = "URGENT: Critical security update required"
        phishing_a = self._email(
            from_name="IT Department",
            from_addr=f"it.support@{phishing_domain}",
            subject=phishing_subject_a,
            body=self._format_email_body(
                "Your account has been flagged for a critical security vulnerability.",
                "Please download and run the attached update immediately to secure your workstation.",
                signoff_name="IT Support Team",
            ),
            timestamp=self.now - timedelta(hours=8),
            thread_id=self._id("thread"),
            labels=["inbox"],
            is_read=False,
            attachments=[self._attachment("urgent-update.exe", "application/octet-stream", "executable")],
        )

        # Phishing B — name says "Payroll" but address is phishing domain
        phishing_subject_b = "Your salary review is ready"
        phishing_b = self._email(
            from_name="Payroll",
            from_addr=f"payroll@{phishing_domain}",
            subject=phishing_subject_b,
            body=self._format_email_body(
                "Your annual salary review has been completed. Please open the attached file to see the details.",
                "This is a time-sensitive document. Respond within 24 hours to confirm.",
                signoff_name="Payroll Department",
            ),
            timestamp=self.now - timedelta(hours=6),
            thread_id=self._id("thread"),
            labels=["inbox"],
            is_read=False,
            attachments=[self._attachment("salary-review.zip", "application/zip", "archive")],
        )

        base["emails"].extend([legit_a, legit_b, phishing_a, phishing_b])

        phishing_ids = [phishing_a.id, phishing_b.id]
        legit_ids = [legit_a.id, legit_b.id]

        return {
            "phishing_ids": phishing_ids,
            "legit_ids": legit_ids,
            "security_team_email": security_team_email,
            "phishing_subject_a": phishing_subject_a,
            "phishing_subject_b": phishing_subject_b,
            "phishing_domain": phishing_domain,
        }

    # ── Task 14 ─────────────────────────────────────────────────────────
    def _seed_gmail_new_hire_setup(self, base: dict[str, Any]) -> dict[str, Any]:
        team_list_email = "eng-team@company.test"
        manager_email = "manager@company.test"
        hiring_manager_email = "hiring-manager@company.test"
        intro_phrase = "Thanks for the warm welcome! Looking forward to working with the team."

        company_name = "Northwind Labs"

        # 3 welcome emails from team leads
        eng_lead_name = self.fake.name()
        eng_lead_email = self._email_for_name(eng_lead_name, domain="company.test")
        design_lead_name = self.fake.name()
        design_lead_email = self._email_for_name(design_lead_name, domain="company.test")
        product_lead_name = self.fake.name()
        product_lead_email = self._email_for_name(product_lead_name, domain="company.test")

        # Team CC addresses for Reply All trap (5+ addresses)
        team_cc = [
            "dev-a@company.test",
            "dev-b@company.test",
            "dev-c@company.test",
            "dev-d@company.test",
            "dev-e@company.test",
        ]

        # The main welcome email (from eng lead) — CC'd to entire team
        welcome_email = self._email(
            from_name=eng_lead_name,
            from_addr=eng_lead_email,
            subject="Welcome to the team!",
            body=self._format_email_body(
                f"Welcome! I'm {eng_lead_name}, leading engineering at {company_name}.",
                "We are excited to have you on board. Please do not hesitate to reach out if you have any questions.",
                "Looking forward to working together on the upcoming sprint.",
                signoff_name=self._first_name(eng_lead_name),
            ),
            timestamp=self.now - timedelta(hours=6),
            thread_id=self._id("thread"),
            labels=["inbox"],
            cc=team_cc,
        )

        design_welcome = self._email(
            from_name=design_lead_name,
            from_addr=design_lead_email,
            subject="Welcome from Design",
            body=self._format_email_body(
                f"Hi there! I'm {design_lead_name}, the design lead at {company_name}.",
                "Feel free to stop by the design studio on the 3rd floor anytime.",
                "We have a team lunch every Thursday — you are welcome to join.",
                signoff_name=self._first_name(design_lead_name),
            ),
            timestamp=self.now - timedelta(hours=5),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        product_welcome = self._email(
            from_name=product_lead_name,
            from_addr=product_lead_email,
            subject="Welcome from Product",
            body=self._format_email_body(
                f"Welcome aboard! I'm {product_lead_name}, heading product at {company_name}.",
                "I will set up a 1:1 with you later this week to walk you through our roadmap.",
                "In the meantime, check out the product wiki for context on our current priorities.",
                signoff_name=self._first_name(product_lead_name),
            ),
            timestamp=self.now - timedelta(hours=4),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        base["emails"].extend([welcome_email, design_welcome, product_welcome])

        new_contact_emails = [eng_lead_email, design_lead_email, product_lead_email]

        # Set display density to something other than "comfortable" so the agent has to change it
        base["settings"].display_density = "default"
        # Undo send starts at 5, agent must set to 30
        # default_reply_behavior already "reply" — change it so agent must set it
        base["settings"].default_reply_behavior = "reply_all"
        # send_and_archive already False, agent must enable

        return {
            "team_list_email": team_list_email,
            "manager_email": manager_email,
            "hiring_manager_email": hiring_manager_email,
            "intro_phrase": intro_phrase,
            "welcome_sender_name": eng_lead_name,
            "welcome_id": welcome_email.id,
            "new_contact_emails": new_contact_emails,
        }

    # ── Task 15 ─────────────────────────────────────────────────────────
    def _seed_gmail_quarterly_closeout(self, base: dict[str, Any]) -> dict[str, Any]:
        star_keyword_a = "board presentation"
        star_keyword_b = "renewal deadline"
        fyi_sender_name = self.fake.name()
        fyi_sender_email = self._email_for_name(fyi_sender_name, domain="internal.test")
        update_topic = "infrastructure migration"
        team_digest_email = "team-digest@company.test"
        vendor_domain = "acmevendor.test"
        vendor_label = "Vendor Invoices"
        new_note = "Key contact for Q2 planning."

        # --- Primary tab: 2 important + 3 FYI ---
        star_a = self._email(
            from_name=self.fake.name(),
            from_addr=self._email_for_name("star-a", domain="leadership.test"),
            subject="Preparation for the board presentation",
            body=self._format_email_body(
                f"We need to finalize the board presentation materials before Thursday.",
                "Please review the attached deck and send your comments by end of day.",
                signoff_name="Leadership",
            ),
            timestamp=self.now - timedelta(days=1, hours=3),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )
        star_b = self._email(
            from_name=self.fake.name(),
            from_addr=self._email_for_name("star-b", domain="contracts.test"),
            subject="Upcoming renewal deadline for enterprise license",
            body=self._format_email_body(
                f"Reminder: the enterprise license renewal deadline is next Friday.",
                "We need to confirm the renewal terms and budget allocation.",
                signoff_name="Contracts",
            ),
            timestamp=self.now - timedelta(days=1, hours=1),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        fyi_emails = []
        for i in range(3):
            fyi = self._email(
                from_name=fyi_sender_name,
                from_addr=fyi_sender_email,
                subject=f"FYI: Weekly status update #{i + 1}",
                body=self._format_email_body(
                    f"FYI — sharing the weekly status update #{i + 1}.",
                    "No action needed on your end. Just keeping you in the loop.",
                    signoff_name=self._first_name(fyi_sender_name),
                ),
                timestamp=self.now - timedelta(days=8 + i, hours=2),
                thread_id=self._id("thread"),
                labels=["inbox"],
            )
            fyi_emails.append(fyi)

        # --- Promotions tab: 3 newsletters + 1 spam ---
        promo_emails = []
        for i in range(3):
            newsletter = self._email(
                from_name=f"Newsletter {chr(65 + i)}",
                from_addr=f"news{i + 1}@newsletters.test",
                subject=f"Weekly digest #{i + 1}",
                body=self._format_email_body(
                    f"Here is your weekly digest #{i + 1}.",
                    "Top stories, product updates, and community highlights.",
                ),
                timestamp=self.now - timedelta(days=2 + i, hours=5),
                thread_id=self._id("thread"),
                labels=["inbox", "promotions"],
            )
            promo_emails.append(newsletter)

        spam_subject = "Exclusive prize giveaway"
        spam_email = self._email(
            from_name="Prize Center",
            from_addr="noreply@spampromo.test",
            subject=spam_subject,
            body=self._format_email_body(
                "Congratulations! You have been selected for an exclusive prize giveaway!",
                "Click below to claim your reward. Offer expires in 24 hours.",
            ),
            timestamp=self.now - timedelta(days=1, hours=8),
            thread_id=self._id("thread"),
            labels=["inbox", "promotions"],
        )

        # --- Updates tab: 2 update emails ---
        update_emails = []
        for i in range(2):
            update = self._email(
                from_name="DevOps Team",
                from_addr=f"devops{i + 1}@infra.test",
                subject=f"Infrastructure migration update — phase {i + 1}",
                body=self._format_email_body(
                    f"Update on the infrastructure migration: phase {i + 1} is complete.",
                    "All services have been migrated successfully with no downtime reported.",
                ),
                timestamp=self.now - timedelta(days=3 + i, hours=4),
                thread_id=self._id("thread"),
                labels=["inbox", "updates"],
            )
            update_emails.append(update)

        # --- Vendor email for filter domain discovery ---
        vendor_email = self._email(
            from_name="Acme Vendor Support",
            from_addr=f"support@{vendor_domain}",
            subject="Invoice #4421 — monthly service fee",
            body=self._format_email_body(
                "Please find invoice #4421 attached for the monthly service fee.",
                "Payment is due within 30 days.",
                signoff_name="Acme Vendor Support",
            ),
            timestamp=self.now - timedelta(days=5, hours=2),
            thread_id=self._id("thread"),
            labels=["inbox"],
        )

        base["emails"].extend([
            star_a, star_b, *fyi_emails, *promo_emails, spam_email,
            *update_emails, vendor_email,
        ])

        # --- Contacts ---
        stale_a = self._contact(
            name=self.fake.name(),
            email=self.fake.email(domain="stale.test"),
            last_contacted_at=self.now - timedelta(days=45),
        )
        stale_b = self._contact(
            name=self.fake.name(),
            email=self.fake.email(domain="archive.test"),
            last_contacted_at=self.now - timedelta(days=60),
        )
        active_contact = self._contact(
            name=self.fake.name(),
            email=self.fake.email(domain="active.test"),
            last_contacted_at=self.now - timedelta(days=5),
        )
        update_contact_name = self.fake.name()
        update_contact_email_addr = self._email_for_name(update_contact_name, domain="planning.test")
        update_contact = self._contact(
            name=update_contact_name,
            email=update_contact_email_addr,
            last_contacted_at=self.now - timedelta(days=10),
        )

        base["contacts"].extend([stale_a, stale_b, active_contact, update_contact])

        fyi_ids = [e.id for e in fyi_emails]
        promo_ids = [e.id for e in promo_emails]
        update_ids = [e.id for e in update_emails]

        return {
            "star_a_id": star_a.id,
            "star_b_id": star_b.id,
            "star_keyword_a": star_keyword_a,
            "star_keyword_b": star_keyword_b,
            "fyi_ids": fyi_ids,
            "fyi_sender_name": fyi_sender_name,
            "promo_ids": promo_ids,
            "spam_id": spam_email.id,
            "spam_subject": spam_subject,
            "update_ids": update_ids,
            "update_topic": update_topic,
            "team_digest_email": team_digest_email,
            "stale_a_id": stale_a.id,
            "stale_b_id": stale_b.id,
            "update_contact_name": update_contact_name,
            "update_contact_email": update_contact_email_addr,
            "new_note": new_note,
            "vendor_domain": vendor_domain,
            "vendor_label": vendor_label,
            "active_contact_id": active_contact.id,
        }

    def _add_generic_distractors(self, base: dict[str, Any], count: int) -> None:
        domains = ["updates.test", "partners.test", "community.test", "metrics.test"]
        subjects = [
            "Agenda draft for Monday check-in",
            "Customer feedback from pilot cohort",
            "Reminder on document review timing",
            "Quarterly metrics recap",
            "Notes from the partner sync",
            "Updated rollout checklist",
            "Follow-up on venue estimate",
            "Revised budget worksheet",
        ]
        for _ in range(count):
            sender_name = self.fake.name()
            sender_email = self._email_for_name(sender_name, domain=self.rng.choice(domains))
            subject = self.rng.choice(subjects)
            labels = ["inbox"]
            if self.rng.random() < 0.25:
                labels.append("updates")
            if self.rng.random() < 0.15:
                labels.append("promotions")
            base["emails"].append(
                self._email(
                    from_name=sender_name,
                    from_addr=sender_email,
                    subject=subject,
                    body=self._generic_email_body(sender_name),
                    timestamp=self.now - timedelta(days=self.rng.randint(1, 20), hours=self.rng.randint(0, 22)),
                    thread_id=self._id("thread"),
                    labels=labels,
                    is_read=self.rng.random() < 0.5,
                    attachments=(
                        [self._attachment(self.rng.choice(["notes.txt", "summary.txt", "agenda.txt"]), "text/plain", "text")]
                        if self.rng.random() < 0.2
                        else []
                    ),
                )
            )

    def _ensure_contact(self, base: dict[str, Any], name: str, email: str, is_vip: bool = False) -> None:
        if any(contact.email.lower() == email.lower() for contact in base["contacts"]):
            return
        base["contacts"].append(
            self._contact(name=name, email=email, is_vip=is_vip, last_contacted_at=self.now - timedelta(days=3))
        )

    def _contact(
        self,
        *,
        name: str | None = None,
        email: str | None = None,
        company: str | None = None,
        note: str | None = None,
        is_vip: bool = False,
        last_contacted_at: datetime | None = None,
    ) -> Contact:
        contact_name = name or self.fake.name()
        contact_email = email or self._email_for_name(contact_name)
        return Contact(
            id=self._id("contact"),
            name=contact_name,
            email=contact_email,
            company=company or self.fake.company(),
            note=note,
            is_vip=is_vip,
            source="seeded",
            last_contacted_at=last_contacted_at or (self.now - timedelta(days=self.rng.randint(1, 20))),
        )

    def _email(
        self,
        *,
        from_name: str,
        from_addr: str,
        subject: str,
        body: str,
        timestamp: datetime,
        thread_id: str,
        labels: list[str] | None = None,
        is_read: bool = False,
        attachments: list[Attachment] | None = None,
        cc: list[str] | None = None,
    ) -> Email:
        return Email(
            id=self._id("email"),
            from_name=from_name,
            from_addr=from_addr,
            to=[self.owner_email],
            cc=cc or [],
            subject=subject,
            body=body,
            timestamp=timestamp,
            is_read=is_read,
            labels=labels or ["inbox"],
            thread_id=thread_id,
            attachments=attachments or [],
        )

    def _attachment(self, filename: str, content_type: str, kind: str) -> Attachment:
        return Attachment(
            id=self._id("attachment"),
            filename=filename,
            content_type=content_type,
            size_bytes=self.rng.randint(12_000, 120_000),
            kind=kind,
        )

    def _email_for_name(self, name: str, domain: str | None = None) -> str:
        local = "".join(ch.lower() for ch in name if ch.isalnum() or ch == " ").replace(" ", ".")
        local = ".".join(part for part in local.split(".") if part) or "contact"
        domain = domain or f"{self.fake.domain_word()}.test"
        return f"{local}@{domain}"

    def _id(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}_{self._counters[prefix]}"


class _FallbackFaker:
    """Small deterministic stand-in when Faker is not installed locally."""

    _FIRST_NAMES = [
        "Avery",
        "Jordan",
        "Maya",
        "Nina",
        "Miles",
        "Priya",
        "Elena",
        "Marcus",
        "Sofia",
        "Theo",
    ]
    _LAST_NAMES = [
        "Chen",
        "Patel",
        "Garcia",
        "Nguyen",
        "Brooks",
        "Rivera",
        "Singh",
        "Kim",
        "Morris",
        "Wright",
    ]
    _COMPANIES = [
        "Northwind Labs",
        "Blue Cedar",
        "Atlas Harbor",
        "Summit Metrics",
        "Pioneer Supply",
        "Lattice Works",
    ]
    _DOMAINS = ["ops", "signal", "harbor", "northwind", "atlas", "lattice"]
    _BUSINESS_SPEAK = [
        "optimize cross-functional alignment",
        "streamline operational reporting",
        "coordinate board readiness",
        "improve vendor responsiveness",
        "stabilize the review cadence",
    ]
    _CATCH_PHRASES = [
        "Reliable systems for fast-moving teams",
        "Clear workflows, fewer surprises",
        "Signal over noise for every launch",
        "Move with confidence and precision",
    ]
    _PARAGRAPH_SENTENCES = [
        "Please review the latest draft before the afternoon check-in.",
        "I flagged the items that still need an owner.",
        "We can close the loop once the dependencies are clear.",
        "Let me know if you need the supporting spreadsheet.",
        "The timeline still works if we keep the original scope.",
    ]

    def __init__(self, seed: int):
        self.rng = random.Random(seed)

    def seed_instance(self, seed: int) -> None:
        self.rng.seed(seed)

    def name(self) -> str:
        return f"{self.rng.choice(self._FIRST_NAMES)} {self.rng.choice(self._LAST_NAMES)}"

    def company(self) -> str:
        return self.rng.choice(self._COMPANIES)

    def domain_word(self) -> str:
        return self.rng.choice(self._DOMAINS)

    def bs(self) -> str:
        return self.rng.choice(self._BUSINESS_SPEAK)

    def catch_phrase(self) -> str:
        return self.rng.choice(self._CATCH_PHRASES)

    def paragraph(self, nb_sentences: int = 3) -> str:
        return " ".join(self.rng.choice(self._PARAGRAPH_SENTENCES) for _ in range(nb_sentences))

    def email(self, domain: str | None = None) -> str:
        local = f"{self.rng.choice(self._FIRST_NAMES)}.{self.rng.choice(self._LAST_NAMES)}".lower()
        return f"{local}@{domain or f'{self.domain_word()}.test'}"
