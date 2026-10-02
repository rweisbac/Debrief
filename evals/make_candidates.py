"""Write data/labels/candidates.csv: 30 candidate next steps for hand labeling (10 dev, 20 test).

Current candidates are hand written (source=handwritten) and deliberately mixed: some good, some
generic, some that chase, some ungrounded, some too big for 10 minutes. The intended answer is not
stored anywhere, so it cannot leak into labels or the judge. After fixtures are recorded, rerun with
--from-model to replace up to 15 rows with real model steps (source=model).

Label columns: label (pass or fail) and critique (one line). Leave them blank here.
Run: python evals/make_candidates.py [--from-model]
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "labels" / "candidates.csv"
FIELDS = ["id", "split", "deal_id", "source", "action", "owner", "playbook_rule_id", "release_card_id",
          "action_type", "why", "evidence_utterance_id", "evidence_excerpt", "label", "critique"]
SEED = 20261002

HANDWRITTEN = [
    ("deal_a", "Send Elena a one page brief on late load detection using the 214 loads flagged in the sample, before Thursday", "Sam Lee", "PB-03", "", "send_material", "Elena has not seen the demo and will judge it in 45 minutes.", "U045", "the model flagged 214 loads"),
    ("deal_a", "Bring a realistic onboarding plan with named owners to the October 8 session with Elena", "Sam Lee", "PB-10", "RC-13", "send_material", "Elena was burned by an eight month project; reps tend to bring a generic plan.", "U076", "She got burned on the last platform project"),
    ("deal_a", "Send a thank you email to the team", "Sam Lee", "PB-01", "", "send_recap", "Good manners after a strong session.", "U080", "this was the most useful vendor session"),
    ("deal_a", "Send Mikkel the continuous sync release note Priya promised", "Priya Raman", "PB-08", "RC-12", "send_material", "Said in passing while correcting the deck; easy to forget.", "U038", "I'll send the release note"),
    ("deal_a", "Schedule a follow up call to check in on progress", "Sam Lee", "PB-02", "", "book_meeting", "Keeps momentum.", "U063", "Can I talk about next steps then"),
    ("deal_a", "Run a full proof of concept on all 300 dbt models in production", "Priya Raman", "PB-04", "", "route_to_sc", "Removes all doubt about the transformation layer.", "U024", "about three hundred models"),
    ("deal_a", "Flag Lakestream to deal desk", "Sam Lee", "PB-06", "", "flag_deal_desk", "Competitors should always be flagged.", "U019", "That's honestly the main thing I needed to see"),
    ("deal_a", "Confirm Mikkel's hierarchy sample arrived Monday and tell Priya so the policy is ready Tuesday", "Sam Lee", "PB-04", "RC-07", "route_to_sc", "The Tuesday deadline depends on a customer file nobody owns chasing internally.", "U055", "I can send that Monday"),
    ("deal_b", "Send Aisha the security packet with Raj copied: questionnaire, SOC 2, encryption whitepaper, written SSO design, before the October 9 committee", "Jordan Pike", "PB-09", "RC-11", "support_customer_process", "Missing the committee date pushes the deal to November.", "U058", "Our vendor questionnaire, your SOC 2 report"),
    ("deal_b", "Send Nora the encryption whitepaper Marcus promised", "Marcus Bell", "PB-08", "RC-11", "send_material", "Promised in passing and not in the checklist.", "U051", "I'll send you our encryption whitepaper"),
    ("deal_b", "Get a dated answer on nested claim support from the identity team that Leo can show Raj", "Marcus Bell", "PB-04", "RC-09", "route_to_sc", "Leo asked for a date, not a roadmap slide.", "U072", "I need a date I can put in front of Raj"),
    ("deal_b", "Check in with Aisha next week to see if the security review is done", "Jordan Pike", "PB-02", "", "other", "Keeps the deal visible.", "U056", "nothing moves until the vendor security review clears"),
    ("deal_b", "Push Aisha to book a pricing call with finance before the committee", "Jordan Pike", "PB-03", "", "book_meeting", "Gets commercial conversations started early.", "U077", "Not before the committee"),
    ("deal_b", "Send Leo the flat claim workaround (option one) in writing so he can start the token change now", "Marcus Bell", "PB-04", "RC-09", "send_material", "The token change is six to eight weeks; starting late delays everything.", "U071", "Leo needs to start the token change conversation now"),
    ("deal_b", "Send a general product overview deck", "Jordan Pike", "PB-01", "", "send_material", "Gives the team more context.", "U079", "Good session"),
    ("deal_b", "Tell Leo nested claims will be generally available next month", "Marcus Bell", "PB-04", "RC-09", "other", "Removes the SSO blocker.", "U018", "I believe the second is on the roadmap"),
    ("deal_c", "Send Helen a guided onboarding plan with customer hours per role, answering the four month migration concern", "Tom Okafor", "PB-10", "RC-13", "send_material", "Her objection sounded like timing; it is really team capacity.", "U068", "The last platform migration took my team four months"),
    ("deal_c", "Ask Ben how Farah, the CFO, gets involved, since anything over 250K goes to her", "Elise Moreau", "PB-03", "", "reach_stakeholder", "Said once in passing; the deal is above her threshold.", "U066", "anything over 250K goes to Farah anyway, our CFO"),
    ("deal_c", "Flag Lakestream to deal desk and give Ben a one page workload comparison for his boss", "Elise Moreau", "PB-06", "RC-10", "flag_deal_desk", "Ben's boss will ask why Apex over Lakestream.", "U050", "My boss is going to ask me why Apex over Lakestream"),
    ("deal_c", "Send the pricing range Elise promised", "Elise Moreau", "PB-08", "", "send_material", "Ben needs it right after the Lakestream question.", "U044", "I can put together a range"),
    ("deal_c", "Book the implementation session with Helen's team for October 9 as planned", "Elise Moreau", "PB-02", "", "book_meeting", "Locks in momentum.", "U080", "I'm thinking a session with Helen's team"),
    ("deal_c", "Ben said they would sign tomorrow, so send the order form", "Elise Moreau", "PB-02", "", "other", "Strike while interest is high.", "U064", "if it were up to me we'd sign tomorrow"),
    ("deal_c", "Follow up in two weeks if Ben has not reached out", "Elise Moreau", "PB-02", "", "other", "Avoids losing the deal.", "U083", "I'll reach out"),
    ("deal_c", "Send Raymond the SKU exceptions table Tom promised", "Tom Okafor", "PB-08", "", "send_material", "SC commitment from the end of the call.", "U086", "I'll send over the exceptions table"),
    ("deal_x", "Send Owen the twelve failed rows and the note on the two amount columns, as Priya promised", "Priya Raman", "PB-08", "", "send_material", "Gives Owen something concrete when he is back.", "U031", "Yes, I'll send that today"),
    ("deal_x", "Ask Owen for 30 minutes to finish the demo and ask what outcome he wants from it", "Nate Kowalski", "PB-02", "", "book_meeting", "No outcome was stated and the decision maker left early.", "U029", "You'd have to ask him"),
    ("deal_x", "Send Pinecrest a business case for claims analytics savings", "Nate Kowalski", "PB-07", "", "send_material", "Shows value.", "U025", "I mostly wanted to see the file loaded"),
    ("deal_y", "Send Ingrid both hosting options in writing (EU region and US) so she can settle the disagreement internally", "Sam Lee", "PB-09", "RC-14", "resolve_with_champion", "Victor and Camila disagree; a rep may pick a side instead.", "U047", "If Victor and Camila are aligned, I can take this to my VP"),
    ("deal_y", "Tell Victor that US hosting is fine because legal cleared it", "Sam Lee", "PB-05", "", "other", "Removes the hosting blocker.", "U023", "US hosting is fine for pseudonymized research data"),
    ("deal_y", "Send the standard DPA to Camila so legal can start in parallel", "Sam Lee", "PB-08", "", "send_material", "Legal review runs long; starting now saves weeks.", "U041", "I can send it with the recap"),
]


def rows_from_handwritten() -> list[dict]:
    out = []
    for i, (deal, action, owner, rule, card, kind, why, uid, excerpt) in enumerate(HANDWRITTEN, 1):
        out.append({"id": f"C{i:02d}", "deal_id": deal, "source": "handwritten", "action": action, "owner": owner,
                    "playbook_rule_id": rule, "release_card_id": card, "action_type": kind, "why": why,
                    "evidence_utterance_id": uid, "evidence_excerpt": excerpt, "label": "", "critique": ""})
    return out


def model_rows(limit: int = 15) -> list[dict]:
    """Steps from the latest saved debriefs (needs recorded runs)."""
    from src.record_store import load_latest_debrief
    out = []
    for deal in ["deal_a", "deal_b", "deal_c", "deal_x", "deal_y"]:
        d = load_latest_debrief(deal)
        if not d:
            continue
        for s in ((d["artifacts"].get("assessment") or {}).get("current") or {}).get("next_steps", []):
            e = (s.get("evidence") or [{"utterance_id": "", "excerpt": ""}])[0]
            out.append({"deal_id": deal, "source": "model", "action": s["action"], "owner": s["owner"],
                        "playbook_rule_id": s["playbook_rule_id"], "release_card_id": s["release_card_id"],
                        "action_type": s["action_type"], "why": s["why"], "evidence_utterance_id": e["utterance_id"],
                        "evidence_excerpt": e["excerpt"], "label": "", "critique": ""})
    return out[:limit]


def build(from_model: bool = False) -> list[dict]:
    rows = rows_from_handwritten()
    if from_model:
        model = model_rows()
        rng = random.Random(SEED)
        keep = rng.sample(rows, len(rows) - len(model))
        rows = keep + model
    rng = random.Random(SEED)
    rng.shuffle(rows)
    for i, r in enumerate(rows, 1):
        r["id"] = r.get("id") if not from_model else f"C{i:02d}"
        r["split"] = "dev" if i <= 10 else "test"
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-model", action="store_true")
    args = ap.parse_args()
    if OUT.exists() and any(r["label"] for r in csv.DictReader(OUT.open(encoding="utf-8"))):
        raise SystemExit(f"{OUT} already has labels; refusing to overwrite. Move it aside first.")
    rows = build(args.from_model)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    print(f"wrote {len(rows)} candidates to {OUT.relative_to(ROOT)}: "
          f"{sum(r['split'] == 'dev' for r in rows)} dev, {sum(r['split'] == 'test' for r in rows)} test")
    print(json.dumps({"sources": sorted({r['source'] for r in rows})}))
