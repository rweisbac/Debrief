"""Measurement plan as code. Every function states its formula in the docstring.

Nothing here claims causation. Win rate by TV band is descriptive only. All thresholds in the decision
table are proposals to agree with sales leadership, and any value computed from simulate_events() is
synthetic example data.
"""
from __future__ import annotations

import random
from collections import Counter
from datetime import date, datetime, timedelta
from statistics import median

SC_SUMMARY_BASELINE = 0.60
COHORT_BASELINE_TOUCHES = {"top_quartile": 2.3, "middle_50": 1.1, "bottom_quartile": 0.7}
CAUSE_RULE_SHARE, CAUSE_RULE_MIN_EVENTS = 0.30, 20

CAUSES = {
    "a": "AE does not know the next step",
    "b": "AE is waiting on the customer",
    "c": "AE has no capacity",
    "d": "Nobody inspects the post-demo window",
    "e": "Weak commercial judgment after TV",
    "f": "The deal is weak and there is nothing to do",
}
# Non-action signal: (reading, candidate cause it speaks to)
SIGNAL_MAP = {
    "card_unopened": ("Channel or timing: the card never reached the rep in a usable moment", "d"),
    "already_done": ("CRM lag or redundancy: the rep already knew the step", "a (evidence against)"),
    "waiting_on_customer": ("Customer dependency", "b"),
    "not_relevant": ("Recommendation quality, or a weak deal", "f"),
    "no_time": ("Capacity", "c"),
    "accepted_no_touch_3d": ("Execution: step accepted but no customer touch within 3 days", "e or d"),
}


def ratio(num: int, den: int) -> float | None:
    """num / den, or None when den is 0 (never report 0% on an empty base)."""
    return round(num / den, 4) if den else None


def add_business_days(start: date, n: int) -> date:
    """start plus n business days (Monday to Friday; holidays not modeled)."""
    d = start
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


# Adoption, 30 days

def debrief_coverage(eligible_demos: int, debriefs_generated: int) -> float | None:
    """debriefs generated / eligible TV demos."""
    return ratio(debriefs_generated, eligible_demos)


def opened_within_24h(cards: list[dict]) -> float | None:
    """cards with opened_at - generated_at <= 24h / cards generated."""
    ok = sum(1 for c in cards if c.get("opened_at") and c["opened_at"] - c["generated_at"] <= timedelta(hours=24))
    return ratio(ok, len(cards))


def checklist_filled_before_end(demos: list[dict]) -> float | None:
    """demos where all 4 checklist fields were filled before the demo end time / eligible demos."""
    return ratio(sum(1 for d in demos if d.get("checklist_complete_before_end")), len(demos))


def recap_sent_within_24h(demos: list[dict]) -> float | None:
    """demos with a recap marked sent within 24h of demo end / eligible demos."""
    ok = sum(1 for d in demos if d.get("recap_sent_at") and d["recap_sent_at"] - d["demo_end"] <= timedelta(hours=24))
    return ratio(ok, len(demos))


def sc_confirmed_within_1bd(records: list[dict]) -> float | None:
    """records confirmed by the SC by the end of the next business day / records generated.
    Baseline for comparison: SC summary doc completion of about 60% (SC_SUMMARY_BASELINE)."""
    ok = sum(1 for r in records if r.get("confirmed_on")
             and r["confirmed_on"] <= add_business_days(r["generated_on"], 1))
    return ratio(ok, len(records))


def low_edit_send_rate(drafts: list[dict], threshold: float = 0.3) -> float | None:
    """drafts sent with edit_ratio < 0.3 / drafts sent. edit_ratio = 1 - normalized Levenshtein similarity."""
    sent = [d for d in drafts if d.get("sent")]
    return ratio(sum(1 for d in sent if d["edit_ratio"] < threshold), len(sent))


def step_outcomes(steps: list[dict]) -> dict:
    """share of steps acted on, dismissed, or ignored (no action and no dismiss within 3 days)."""
    c = Counter(s["outcome"] for s in steps)
    n = len(steps)
    return {k: ratio(c.get(k, 0), n) for k in ("acted", "dismissed", "ignored")}


# Diagnostic, 30 days

def non_action_signals(steps: list[dict], cards: list[dict]) -> Counter:
    """Count non-action signals: each dismiss by reason, each unopened card, and each step accepted
    (action taken) with no customer touch within 3 days."""
    c: Counter = Counter()
    for s in steps:
        if s["outcome"] == "dismissed":
            c[s["reason"]] += 1
        elif s["outcome"] == "acted" and not s.get("customer_touch_within_3d", True):
            c["accepted_no_touch_3d"] += 1
    c["card_unopened"] += sum(1 for card in cards if not card.get("opened_at"))
    return c


def diagnose(signals: Counter) -> list[dict]:
    """Pre-declared rule: a signal's cause counts as real if it explains >= 30% of all non-actions AND has
    >= 20 events. Returns one row per signal with share and verdict."""
    total = sum(signals.values())
    rows = []
    for key, (reading, cause) in SIGNAL_MAP.items():
        n = signals.get(key, 0)
        share = ratio(n, total)
        real = bool(share is not None and share >= CAUSE_RULE_SHARE and n >= CAUSE_RULE_MIN_EVENTS)
        rows.append({"signal": key, "reading": reading, "candidate_cause": cause, "events": n,
                     "share_of_non_actions": share, "meets_rule": real})
    return rows


# Leading impact, 30 days

def dated_next_step_within_2bd(demos: list[dict]) -> float | None:
    """demos with a customer-confirmed dated next step by the end of business day 2 after the demo / demos."""
    ok = sum(1 for d in demos if d.get("next_step_confirmed_on")
             and d["next_step_confirmed_on"] <= add_business_days(d["demo_end"].date(), 2))
    return ratio(ok, len(demos))


def recap_reply_rate_5bd(demos: list[dict]) -> float | None:
    """recaps with a customer reply within 5 business days of sending / recaps sent."""
    sent = [d for d in demos if d.get("recap_sent_at")]
    ok = sum(1 for d in sent if d.get("reply_on") and d["reply_on"] <= add_business_days(d["recap_sent_at"].date(), 5))
    return ratio(ok, len(sent))


def touches_14d_by_cohort(demos: list[dict]) -> dict:
    """mean customer touches in the 14 days after the demo, per AE cohort, next to the packet baseline
    (2.3, 1.1, 0.7). Touches may reflect deal quality as much as rep behavior."""
    out = {}
    for cohort, base in COHORT_BASELINE_TOUCHES.items():
        vals = [d["touches_14d"] for d in demos if d["cohort"] == cohort]
        out[cohort] = {"baseline": base, "current": round(sum(vals) / len(vals), 2) if vals else None, "n": len(vals)}
    return out


def hours_to_first_touch(demos: list[dict]) -> float | None:
    """median hours from demo end to the first customer touch, over demos with a touch."""
    vals = [(d["first_touch_at"] - d["demo_end"]).total_seconds() / 3600 for d in demos if d.get("first_touch_at")]
    return round(median(vals), 1) if vals else None


# Impact, 90 days

def kaplan_meier(durations: list[float], observed: list[bool]) -> list[tuple[float, float]]:
    """Kaplan-Meier survival curve for days in TV. observed=False means the deal is still open
    (right-censored). S(t) = product over event times t_i <= t of (1 - d_i / n_i), where d_i deals exited
    TV at t_i and n_i deals were still in TV just before t_i. Returns [(t_i, S(t_i))]."""
    pairs = sorted(zip(durations, observed))
    at_risk = len(pairs)
    surv, curve, i = 1.0, [], 0
    while i < len(pairs):
        t = pairs[i][0]
        events = sum(1 for d, o in pairs if d == t and o)
        ties = sum(1 for d, _ in pairs if d == t)
        if events:
            surv *= 1 - events / at_risk
            curve.append((t, round(surv, 6)))
        at_risk -= ties
        i += ties
    return curve


def km_median(durations: list[float], observed: list[bool]) -> float | None:
    """smallest t with S(t) <= 0.5, or None if the curve never reaches 0.5 (median not yet observed)."""
    for t, s in kaplan_meier(durations, observed):
        if s <= 0.5:
            return t
    return None


def tv_days_by_arm(deals: list[dict], week_start: date, week_end: date) -> dict:
    """Staggered rollout by pod: among deals entering TV in [week_start, week_end], compare the KM median
    days in TV for pods already treated (rollout_week <= entry week) vs pods not yet treated. Open deals
    are right-censored at as_of. A comparison, not a causal estimate; match on segment, size band and AE
    tenure before reading it."""
    out = {}
    for arm in ("treated", "not_yet_treated"):
        rows = [d for d in deals if week_start <= d["tv_entered_at"] <= week_end
                and ((d["rollout_week"] is not None and d["rollout_week"] <= d["tv_entered_at"]) == (arm == "treated"))]
        dur = [((d["tv_exited_at"] or d["as_of"]) - d["tv_entered_at"]).days for d in rows]
        obs = [d["tv_exited_at"] is not None for d in rows]
        out[arm] = {"n": len(rows), "km_median_days": km_median(dur, obs) if rows else None}
    return out


def win_rate_by_tv_band(deals: list[dict]) -> list[dict]:
    """wins / closed deals per TV band (<7, 7 to 14, >14 days). Descriptive only, labeled
    "correlational; underpowered at 90 days". Weak deals may stall and also lose."""
    bands = {"under 7 days": (0, 7), "7 to 14 days": (7, 15), "over 14 days": (15, 10_000)}
    rows = []
    for name, (lo, hi) in bands.items():
        closed = [d for d in deals if d["outcome"] in ("won", "lost") and lo <= d["tv_days"] < hi]
        rows.append({"band": name, "closed": len(closed),
                     "win_rate": ratio(sum(d["outcome"] == "won" for d in closed), len(closed)),
                     "label": "correlational; underpowered at 90 days"})
    return rows


def decision_table(current: dict) -> list[dict]:
    """Metric, baseline, scale if, fix if, stop if, current value. All thresholds are proposals, to agree with
    sales leadership. 'current' values passed in from simulate_events() are synthetic example data."""
    p = "proposed, to agree with sales leadership"
    rows = [
        ("Debriefs opened within 24h", "none (new)", ">= 70%", "40% to 70%: check channel and timing", "< 40% after 4 weeks", "opened_24h"),
        ("Close-the-demo checklist filled before call end", "none (new)", ">= 60%", "30% to 60%: shorten or prefill", "< 30%", "checklist"),
        ("SC record confirmed within 1 business day", "60% SC doc completion", ">= 75%", "60% to 75%", "< 60% (no better than today)", "sc_confirmed"),
        ("Recap drafts sent with edit ratio < 0.3", "none (new)", ">= 50%", "20% to 50%: improve drafts", "< 20%", "low_edit"),
        ("Customer-confirmed dated next step within 2 business days", "to measure in pilot pods before rollout", "+10 points vs not-yet-treated pods", "flat", "below not-yet-treated pods", "dated_next_step"),
        ("Customer reply to recap within 5 business days", "to measure in pilot pods", "+10 points vs not-yet-treated pods", "flat", "below not-yet-treated pods", "reply_rate"),
    ]
    return [{"metric": m, "baseline": b, "scale_if": s, "fix_if": f, "stop_if": st,
             "current_value": current.get(k), "thresholds": p} for m, b, s, f, st, k in rows]


def simulate_events(seed: int = 7, n_demos: int = 60) -> dict:
    """Synthetic example data for the measurement tab. Seeded and labeled; never a result."""
    rng = random.Random(seed)
    start = datetime(2026, 8, 3, 15, 0)
    cards, steps, demos, drafts, records = [], [], [], [], []
    for i in range(n_demos):
        end = start + timedelta(days=rng.randint(0, 50), hours=rng.randint(0, 3))
        opened = end + timedelta(hours=rng.choice([1, 2, 5, 20, 30, 70])) if rng.random() < 0.8 else None
        cards.append({"generated_at": end, "opened_at": opened})
        cohort = rng.choices(["top_quartile", "middle_50", "bottom_quartile"], [1, 2, 1])[0]
        for _ in range(rng.choice([1, 2, 3])):
            outcome = rng.choices(["acted", "dismissed", "ignored"], [5, 3, 2])[0]
            steps.append({"outcome": outcome,
                          "reason": rng.choices(["already_done", "waiting_on_customer", "not_relevant", "no_time"],
                                                [3, 4, 2, 2])[0] if outcome == "dismissed" else "",
                          "customer_touch_within_3d": rng.random() < 0.7})
        sent = end + timedelta(hours=rng.choice([2, 6, 20, 40])) if rng.random() < 0.75 else None
        demos.append({"demo_end": end, "checklist_complete_before_end": rng.random() < 0.45, "recap_sent_at": sent,
                      "reply_on": (sent + timedelta(days=rng.randint(0, 8))).date() if sent and rng.random() < 0.6 else None,
                      "next_step_confirmed_on": (end + timedelta(days=rng.randint(0, 5))).date() if rng.random() < 0.55 else None,
                      "cohort": cohort, "touches_14d": max(0, round(rng.gauss({"top_quartile": 2.4, "middle_50": 1.3,
                                                                               "bottom_quartile": 0.9}[cohort], 0.6))),
                      "first_touch_at": end + timedelta(hours=rng.choice([3, 10, 26, 50])) if rng.random() < 0.85 else None})
        if sent:
            drafts.append({"sent": True, "edit_ratio": round(rng.random() * 0.6, 2)})
        gen = end.date()
        records.append({"generated_on": gen, "confirmed_on": add_business_days(gen, rng.choice([0, 1, 1, 2, 4]))
                        if rng.random() < 0.85 else None})
    signals = non_action_signals(steps, cards)
    current = {"opened_24h": opened_within_24h(cards), "checklist": checklist_filled_before_end(demos),
               "sc_confirmed": sc_confirmed_within_1bd(records), "low_edit": low_edit_send_rate(drafts),
               "dated_next_step": dated_next_step_within_2bd(demos), "reply_rate": recap_reply_rate_5bd(demos)}
    return {"label": "synthetic example data", "cards": cards, "steps": steps, "demos": demos, "drafts": drafts,
            "records": records, "signals": signals, "current": current}
