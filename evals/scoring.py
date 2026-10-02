"""Score one debrief result against gold labels. Pure functions, no model calls.

Each scorer returns dicts with an explicit pass flag and a human readable detail, so failures
can be listed in results.md exactly as they happened.
"""
from __future__ import annotations

import re

from src.rules import is_chase

SCORED_LISTS = {
    # gold key: (extraction key, match mode)
    "objections": ("objections", "utterance"),
    "commitments": ("commitments", "utterance"),
    "stakeholders": ("stakeholders", "name_or_utterance"),
    "open_items": ("open_technical_items", "utterance"),
}


def _gold_ids(item: dict) -> set[str]:
    return {e["utterance_id"] for e in item.get("evidence", [])}


def _pred_ids(item: dict) -> set[str]:
    return {e["utterance_id"].upper() for e in item.get("evidence", [])}


def _name_match(gold_name: str, pred_name: str) -> bool:
    g = gold_name.split("(")[0].strip().lower()
    p = pred_name.lower()
    if not g:
        return False
    first = g.split()[0].rstrip("'s")
    return g in p or p in g or (len(first) > 2 and first in p.split())


def match_lists(gold_items: list[dict], pred_items: list[dict], mode: str) -> dict:
    matched_gold, matched_pred = set(), set()
    for gi, g in enumerate(gold_items):
        for pi, p in enumerate(pred_items):
            hit = bool(_gold_ids(g) & _pred_ids(p))
            if mode == "name_or_utterance":
                hit = _name_match(g.get("name", ""), p.get("name", "")) or (hit and "unnamed" in g.get("name", ""))
            if hit:
                matched_gold.add(gi)
                matched_pred.add(pi)
    missed = [g.get("summary") or g.get("name") or g.get("what") for i, g in enumerate(gold_items) if i not in matched_gold]
    extra = [p.get("summary") or p.get("name") or p.get("what") for i, p in enumerate(pred_items) if i not in matched_pred]
    return {"recall": (len(matched_gold), len(gold_items)), "precision": (len(matched_pred), len(pred_items)),
            "missed": missed, "extra": extra}


def extraction_scores(gold: dict, extraction: dict) -> dict:
    return {key: match_lists(gold.get(key, []), extraction.get(pred_key, []), mode)
            for key, (pred_key, mode) in SCORED_LISTS.items()}


def _all_text(result: dict) -> str:
    """Steps plus current drafts, lowercased, for phrase checks."""
    parts = []
    arts = result.get("artifacts", {})
    for name in ("assessment", "recap_email", "internal_summary", "mutual_action_plan"):
        cur = (arts.get(name) or {}).get("current")
        if cur:
            parts.append(_flatten(cur))
    return "\n".join(parts).lower()


def _flatten(obj) -> str:
    if isinstance(obj, dict):
        return " ".join(_flatten(v) for k, v in obj.items() if k != "evidence")
    if isinstance(obj, list):
        return " ".join(_flatten(v) for v in obj)
    return str(obj)


def _steps(result: dict) -> list[dict]:
    a = (result.get("artifacts", {}).get("assessment") or {}).get("current") or {}
    return a.get("next_steps", [])


def _state(result: dict) -> str:
    a = (result.get("artifacts", {}).get("assessment") or {}).get("current") or {}
    return a.get("deal_state", "")


def _recap_text(result: dict) -> str:
    r = (result.get("artifacts", {}).get("recap_email") or {}).get("current") or {}
    return (r.get("subject", "") + "\n" + r.get("body", "")).lower()


def _map_text(result: dict) -> str:
    m = (result.get("artifacts", {}).get("mutual_action_plan") or {}).get("current") or {}
    return _flatten(m).lower()


def score_trap(trap: dict, result: dict) -> dict:
    ex = result.get("extraction") or {}
    trap_ids = {e["utterance_id"] for e in trap["evidence"]}
    check = trap["check"]
    sub: dict[str, bool] = {}
    if check == "commitment_extracted":
        terms = [t.lower() for t in trap["required_terms"]]
        sub["extracted"] = any(all(t in c["what"].lower() for t in terms) and _pred_ids(c) & trap_ids
                               for c in ex.get("commitments", []))
        sub["checklist_mismatch_flagged"] = any(m["field"] == "sc_commitment" for m in ex.get("checklist_mismatches", []))
        sub["in_recap"] = all(t in _recap_text(result) for t in terms)
        sub["in_map"] = all(t in _map_text(result) for t in terms)
        passed = sub["extracted"] and sub["in_recap"]
    elif check == "stakeholder_extracted":
        terms = trap["required_terms"]
        sub["extracted_absent"] = any(any(t.lower() in s["name"].lower() for t in terms) and not s["present"]
                                      for s in ex.get("stakeholders", []))
        eb = ((result.get("meddpicc") or {}).get("economic_buyer") or {})
        sub["meddpicc_eb_points_to_them"] = any(t.lower() in eb.get("summary", "").lower() for t in terms)
        passed = sub["extracted_absent"]
    elif check == "signal_not_overread":
        sub["state_ok"] = _state(result) not in trap.get("forbidden_deal_states", [])
        sub["not_strong_signal"] = not any(s["strength"] == "strong" and _pred_ids(s) & trap_ids
                                           for s in ex.get("buying_signals", []))
        passed = sub["state_ok"] and sub["not_strong_signal"]
    elif check == "superseded_feature":
        hits = superseded_sentences(_all_text(result), trap.get("forbidden_phrases", []))
        sub["no_superseded_phrase"] = not hits
        sub["correction_extracted"] = any(_pred_ids(c) & trap_ids for c in ex.get("corrections", []))
        passed = sub["no_superseded_phrase"]
    elif check == "exact_numbers":
        values = [n["value"] for n in ex.get("exact_numbers", [])]
        sub["extracted_exactly"] = all(any(req in v for v in values) for req in trap["required_values"])
        num_checks = [c for c in result.get("checks", []) if c["check"] == "numbers_in_source"
                      and not c.get("after_regeneration")]
        sub["drafts_numbers_grounded"] = all(c["passed"] for c in num_checks)
        passed = sub["extracted_exactly"] and sub["drafts_numbers_grounded"]
    elif check == "supports_not_chases":
        steps = _steps(result)
        top = steps[0] if steps else {}
        top_text = (top.get("action", "") + " " + top.get("why", "")).lower()
        # The type label or the right names are not enough on their own (stress gaps T6d, T6e):
        # the top step must not itself be a chase.
        sub["top_step_supports_process"] = bool(top) and not is_chase(top.get("action", ""), top.get("action_type", "")) and (
            top.get("action_type") in {"support_customer_process", "send_material"}
            or any(t.lower() in top_text for t in trap.get("required_terms", [])))
        step_text = " ".join(s["action"].lower() for s in steps)
        sub["no_chase_phrase"] = (not any(p in step_text for p in trap.get("forbidden_phrases", []))
                                  and not any(is_chase(s["action"], s.get("action_type", "")) for s in steps))
        passed = sub["top_step_supports_process"] and sub["no_chase_phrase"]
    else:
        raise ValueError(f"unknown trap check {check!r}")
    return {"id": trap["id"], "name": trap["name"], "passed": passed, "sub": sub,
            "expected": trap["expected_behavior"]}


CORRECTION_MARKERS = ("continuous", "no longer", "used to", "previously", "old ", "changed", "instead of",
                      "was hourly", "not hourly", "replaced")


def superseded_sentences(text: str, phrases: list[str]) -> list[str]:
    """Sentences that mention an old behavior without also signalling it was replaced.

    "Hourly sync: continuous sync now" is fine; "the connector syncs hourly" is not.
    """
    out = []
    for sentence in re.split(r"(?<=[.!?\n])\s+|\n", text.lower()):
        if any(p in sentence for p in phrases) and not any(m in sentence for m in CORRECTION_MARKERS):
            out.append(sentence.strip())
    return out


def score_adversarial(gold: dict, result: dict) -> dict | None:
    adv = gold.get("adversarial")
    if not adv:
        return None
    ex = result.get("extraction") or {}
    sub: dict[str, bool] = {}
    if adv["id"] == "X1":
        sub["low_information"] = _state(result) == "low_information"
        sub["max_steps"] = len(_steps(result)) <= adv["max_steps"]
        sub["no_invented_outcome"] = not (ex.get("business_outcome") or {}).get("stated", False)
        sub["no_strong_signal"] = not any(s["strength"] == "strong" for s in ex.get("buying_signals", []))
        sub["no_competitor"] = not ex.get("competitor_mentions")
        names = [c for c in result.get("checks", []) if c["check"] == "names_known"]
        sub["no_invented_people"] = all(c["passed"] for c in names)
    elif adv["id"] == "Y1":
        gold_ids = {e["utterance_id"] for c in gold["contradictions"] for e in c["evidence"]}
        sub["contradiction_flagged"] = any(_pred_ids(c) & gold_ids for c in ex.get("contradictions", []))
        sub["resolve_with_champion"] = any(s.get("action_type") == "resolve_with_champion" or "ingrid" in s["action"].lower()
                                           for s in _steps(result))
    passed = all(sub.values())
    return {"id": adv["id"], "name": "Adversarial", "passed": passed, "sub": sub, "expected": adv["expected_behavior"]}


def score_state(gold: dict, result: dict) -> dict:
    state = _state(result)
    return {"expected": gold["expected_deal_state"], "accepted": gold["accepted_deal_states"], "got": state,
            "passed": state in gold["accepted_deal_states"]}


def score_grounding(result: dict) -> dict:
    """A check that never ran is a failure, not a pass (stress gap G19)."""
    first = [c for c in result.get("checks", []) if not c.get("after_regeneration")]
    out = {}
    for name in ("evidence_resolves", "numbers_in_source", "names_known", "dates_future_business_days",
                 "no_unsupported_claims"):
        ran = [c for c in first if c["check"] == name]
        fails = [f'{c["artifact"]}: {c["detail"]}' for c in ran if not c["passed"]]
        if not ran:
            fails = ["not run: no result for this check"]
        out[name] = {"passed": not fails, "failures": fails}
    return out


def score_overclaim(result: dict) -> dict:
    """Uncommitted promises are only caught by the model verifier, so if the verifier did not run (or its
    output could not be read) this is "not run", which counts as a failure (stress gaps O1, O2).
    Deterministic savings, guarantee and ROI claims are caught by checks.no_unsupported_claims."""
    verdicts = [v for v in result.get("verifier", []) if v["check"] == "email_promises_uncommitted"
                and v["artifact"] == "recap_email" and not v.get("after_regeneration")]
    fails = [v["target"] for v in verdicts if not v["passed"]]
    claims = [c for c in result.get("checks", []) if c["check"] == "no_unsupported_claims"
              and c["artifact"] == "recap_email" and not c.get("after_regeneration") and not c["passed"]]
    fails += [", ".join(c["locations"]) for c in claims]
    final = (result.get("artifacts", {}).get("recap_email") or {})
    fixed = bool(final.get("regenerated")) and not final.get("needs_review")
    status = "not run" if not verdicts else ("pass" if not fails or fixed else "fail")
    return {"passed": status == "pass", "status": status, "first_draft_flags": fails, "verifier_ran": bool(verdicts),
            "note": "verifier based; the verifier is itself a model and is not ground truth"}


def score_steps(result: dict) -> dict:
    steps = _steps(result)
    problems = []
    if len(steps) > 3:
        problems.append(f"{len(steps)} steps")
    for i, s in enumerate(steps, 1):
        if not s.get("evidence"):
            problems.append(f"step {i} has no evidence")
        if not s.get("owner", "").strip():
            problems.append(f"step {i} has no owner")
        if not re.match(r"^PB-\d{2}$", s.get("playbook_rule_id", "").strip().upper()):
            problems.append(f"step {i} rule id {s.get('playbook_rule_id')!r}")
    chase = [c for c in result.get("checks", []) if c["check"] == "no_chase_when_waiting" and not c["passed"]]
    if chase:
        problems.append("chase step on waiting_on_customer")
    return {"passed": not problems, "problems": problems, "n_steps": len(steps)}


def fmt_count(pair: tuple[int, int]) -> str:
    return f"{pair[0]} of {pair[1]}"
