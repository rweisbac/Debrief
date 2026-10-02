"""Nudges and loop closure. Deterministic, no model calls.

Rules:
- no customer touch 24 hours after the demo: gentle reminder to the AE
- no customer touch 48 hours after the demo: stronger reminder to the AE plus a coaching prompt for the manager
- an SC commitment past its due date: reminder to the SC
- waiting_on_customer: no-touch reminders are suppressed and replaced by one check-in on the customer's
  dependency ("what does their process need from us"), never a chase
- at most 1 nudge per deal per business day, only between 08:00 and 18:00 in the deal's local time,
  only on business days
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

QUIET_START, QUIET_END = 8, 18


@dataclass
class Nudge:
    kind: str  # no_touch_24h, no_touch_48h, sc_commitment_past_due, dependency_check_in
    deal_id: str
    messages: list[dict]  # each {"role", "recipient", "text"}

    @property
    def text(self) -> str:
        return " ".join(m["text"] for m in self.messages)


@dataclass
class DealNudgeState:
    deal_id: str
    account: str
    deal_state: str
    demo_end: datetime  # timezone aware, local to the deal
    ae: str
    sc: str
    manager: str
    top_step: str = ""
    dependency: str = ""
    customer_touches: list[datetime] = field(default_factory=list)
    sc_commitments: list[dict] = field(default_factory=list)  # {"what", "due" (ISO or ""), "done": bool}
    nudges_sent: list[tuple[datetime, str]] = field(default_factory=list)  # (when, kind)


def in_send_window(now_local: datetime) -> bool:
    return now_local.weekday() < 5 and QUIET_START <= now_local.hour < QUIET_END


def evaluate(deal: DealNudgeState, now: datetime) -> list[Nudge]:
    """Return at most one nudge for this deal at this moment."""
    local = now.astimezone(deal.demo_end.tzinfo)
    if not in_send_window(local):
        return []
    if any(sent.astimezone(deal.demo_end.tzinfo).date() == local.date() for sent, _ in deal.nudges_sent):
        return []
    sent_kinds = {k for _, k in deal.nudges_sent}
    hours = (now - deal.demo_end).total_seconds() / 3600
    touched = any(t > deal.demo_end for t in deal.customer_touches)
    waiting = deal.deal_state == "waiting_on_customer"

    if not touched and not waiting:
        if hours >= 48 and "no_touch_48h" not in sent_kinds:
            return [Nudge("no_touch_48h", deal.deal_id, [
                {"role": "ae", "recipient": deal.ae,
                 "text": f"Two days since the {deal.account} demo and no customer touch yet. "
                         + (f"Top step: {deal.top_step} " if deal.top_step else "")
                         + "The recap draft is ready to review and send."},
                {"role": "manager", "recipient": deal.manager,
                 "text": f"Coaching prompt for {deal.ae} on {deal.account}: ask what the customer is waiting on "
                         f"and whether the top step still fits. Touch counts can reflect deal quality, so start "
                         f"with the deal, not the activity."}])]
        if 24 <= hours < 48 and "no_touch_24h" not in sent_kinds:
            return [Nudge("no_touch_24h", deal.deal_id, [
                {"role": "ae", "recipient": deal.ae,
                 "text": f"No customer touch since the {deal.account} demo. The recap draft is ready: "
                         f"one tap to review and send."}])]

    for c in deal.sc_commitments:
        if c.get("done") or not c.get("due"):
            continue
        due = date.fromisoformat(c["due"])
        key = f"sc_commitment_past_due:{c['what']}"
        if local.date() > due and key not in sent_kinds:
            return [Nudge(key, deal.deal_id, [
                {"role": "sc", "recipient": deal.sc,
                 "text": f"For {deal.account}: \"{c['what']}\" was due {due.isoformat()}. Send it, or tell "
                         f"{deal.ae} the new date so the customer hears it from us."}])]

    if waiting and hours >= 24 and "dependency_check_in" not in sent_kinds:
        dep = deal.dependency or "their internal process"
        return [Nudge("dependency_check_in", deal.deal_id, [
            {"role": "ae", "recipient": deal.ae,
             "text": f"{deal.account} is waiting on: {dep}. Is there anything that process needs from us? "
                     + (f"Suggested: {deal.top_step}" if deal.top_step else "")
                     + " No need to ask them for a status update."}])]
    return []


def loop_closure_message(account: str, outcome: str, extraction: dict, sc: str) -> str:
    """Short note to the SC when a deal is marked advanced or stalled: outcome, and which objections
    and answers mattered."""
    lines = [f"{account} was marked {outcome}."]
    mattered = [o for o in extraction.get("objections", []) if o.get("answer_given")]
    if mattered:
        lines.append("What mattered from your demo:")
        for o in mattered[:3]:
            lines.append(f"- {o['summary']} ({o['status'].replace('_', ' ')}): {o['answer_given']}")
    sc_commitments = [c for c in extraction.get("commitments", []) if c.get("who") == sc]
    if sc_commitments:
        lines.append("Your commitments on this deal: " + "; ".join(c["what"] for c in sc_commitments) + ".")
    lines.append(f"Thanks, {sc.split()[0]}.")
    return "\n".join(lines)
