import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone

import pytest

from src import blockkit, events, handoff, metrics, nudges, record_store
from src.chain import load_context

CT = timezone(timedelta(hours=-5))
END = datetime(2026, 9, 30, 10, 47, tzinfo=CT)  # Wednesday


def state(**kw):
    base = dict(deal_id="d", account="Halvorsen Freight", deal_state="ready_to_advance", demo_end=END, ae="Sam Lee",
                sc="Priya Raman", manager="Morgan Diaz", top_step="Send Elena a brief")
    base.update(kw)
    return nudges.DealNudgeState(**base)


def kinds(s, now):
    return [n.kind for n in nudges.evaluate(s, now)]


# Nudges with a fake clock

def test_no_nudge_before_24h():
    assert kinds(state(), END + timedelta(hours=20)) == []


def test_gentle_at_24h_and_stronger_with_manager_at_48h():
    assert kinds(state(), END + timedelta(hours=24, minutes=5)) == ["no_touch_24h"]
    n = nudges.evaluate(state(nudges_sent=[(END + timedelta(hours=24), "no_touch_24h")]), END + timedelta(hours=48, minutes=5))
    assert [x.kind for x in n] == ["no_touch_48h"]
    assert {m["role"] for m in n[0].messages} == {"ae", "manager"}
    assert "deal quality" in n[0].messages[1]["text"]


def test_touch_stops_no_touch_nudges():
    assert kinds(state(customer_touches=[END + timedelta(hours=2)]), END + timedelta(hours=30)) == []


def test_quiet_hours_and_weekend():
    assert kinds(state(), datetime(2026, 10, 1, 19, 0, tzinfo=CT)) == []   # Thursday 19:00
    assert kinds(state(), datetime(2026, 10, 1, 7, 59, tzinfo=CT)) == []   # before 08:00
    assert kinds(state(), datetime(2026, 10, 3, 11, 0, tzinfo=CT)) == []   # Saturday
    assert kinds(state(), datetime(2026, 10, 1, 8, 0, tzinfo=CT)) == []    # 21h, too early anyway
    assert kinds(state(), datetime(2026, 10, 1, 11, 0, tzinfo=CT)) == ["no_touch_24h"]


def test_quiet_hours_use_deal_local_time():
    utc_now = datetime(2026, 10, 1, 23, 30, tzinfo=timezone.utc)  # 18:30 Central
    assert kinds(state(), utc_now) == []


def test_daily_cap():
    s = state(nudges_sent=[(datetime(2026, 10, 1, 9, 0, tzinfo=CT), "no_touch_24h")],
              sc_commitments=[{"what": "Partner policy", "due": "2026-09-30", "done": False}])
    assert kinds(s, datetime(2026, 10, 1, 15, 0, tzinfo=CT)) == []
    assert kinds(s, datetime(2026, 10, 2, 9, 0, tzinfo=CT)) == ["sc_commitment_past_due:Partner policy"]


def test_sc_past_due_only_after_due_date_and_not_when_done():
    c = {"what": "Partner policy", "due": "2026-10-06", "done": False}
    touched = [END + timedelta(hours=1)]
    assert kinds(state(customer_touches=touched, sc_commitments=[c]), datetime(2026, 10, 6, 16, 0, tzinfo=CT)) == []
    assert kinds(state(customer_touches=touched, sc_commitments=[c]), datetime(2026, 10, 7, 9, 0, tzinfo=CT)) \
        == ["sc_commitment_past_due:Partner policy"]
    assert kinds(state(customer_touches=touched, sc_commitments=[dict(c, done=True)]),
                 datetime(2026, 10, 7, 9, 0, tzinfo=CT)) == []


def test_waiting_on_customer_suppresses_no_touch_and_checks_dependency():
    s = state(deal_state="waiting_on_customer", dependency="Vendor security review")
    for h in (25, 49):
        n = nudges.evaluate(s, END + timedelta(hours=h))
        assert [x.kind for x in n] == ["dependency_check_in"]
        text = n[0].text.lower()
        assert "vendor security review" in text and "status update" in text  # tells the AE not to ask for one
        s.nudges_sent.append((END + timedelta(hours=h), "dependency_check_in"))
        break
    assert kinds(s, END + timedelta(hours=73)) == []  # check-in happens once, no chasing after it


def test_loop_closure_message():
    ex = {"objections": [{"summary": "Hourly sync too slow", "status": "resolved", "answer_given": "Continuous sync"}],
          "commitments": [{"who": "Priya Raman", "what": "Partner policy"}]}
    msg = nudges.loop_closure_message("Halvorsen Freight", "advanced", ex, "Priya Raman")
    assert "marked advanced" in msg and "Continuous sync" in msg and "Partner policy" in msg


# Metrics against hand-computed examples

def test_kaplan_meier_with_censoring():
    # durations 3e, 5e, 5c, 8e, 10c, 12e. S(3)=5/6, S(5)=5/6*4/5=2/3, S(8)=2/3*2/3=4/9, S(12)=0.
    curve = metrics.kaplan_meier([3, 5, 5, 8, 10, 12], [True, True, False, True, False, True])
    assert curve == [(3, round(5 / 6, 6)), (5, round(2 / 3, 6)), (8, round(4 / 9, 6)), (12, 0.0)]
    assert metrics.km_median([3, 5, 5, 8, 10, 12], [True, True, False, True, False, True]) == 8


def test_km_median_not_reached_when_mostly_censored():
    assert metrics.km_median([4, 6, 9, 10], [True, False, False, False]) is None


def test_ratio_on_empty_base_is_none():
    assert metrics.ratio(0, 0) is None and metrics.debrief_coverage(0, 0) is None


def test_adoption_formulas():
    t0 = datetime(2026, 9, 1, 10)
    cards = [{"generated_at": t0, "opened_at": t0 + timedelta(hours=2)}, {"generated_at": t0, "opened_at": t0 + timedelta(hours=30)},
             {"generated_at": t0, "opened_at": None}, {"generated_at": t0, "opened_at": t0 + timedelta(hours=24)}]
    assert metrics.opened_within_24h(cards) == 0.5
    drafts = [{"sent": True, "edit_ratio": 0.1}, {"sent": True, "edit_ratio": 0.3}, {"sent": False, "edit_ratio": 0}]
    assert metrics.low_edit_send_rate(drafts) == 0.5
    recs = [{"generated_on": date(2026, 10, 2), "confirmed_on": date(2026, 10, 5)},   # Fri to Mon: within 1 bd
            {"generated_on": date(2026, 10, 2), "confirmed_on": date(2026, 10, 6)},
            {"generated_on": date(2026, 10, 2), "confirmed_on": None}]
    assert metrics.sc_confirmed_within_1bd(recs) == round(1 / 3, 4)
    assert metrics.step_outcomes([{"outcome": "acted"}, {"outcome": "dismissed"}, {"outcome": "ignored"},
                                  {"outcome": "acted"}]) == {"acted": 0.5, "dismissed": 0.25, "ignored": 0.25}


def test_leading_formulas():
    end = datetime(2026, 10, 1, 10)  # Thursday; 2 business days later is Monday Oct 5
    demos = [{"demo_end": end, "next_step_confirmed_on": date(2026, 10, 5)},
             {"demo_end": end, "next_step_confirmed_on": date(2026, 10, 6)},
             {"demo_end": end, "next_step_confirmed_on": None}]
    assert metrics.dated_next_step_within_2bd(demos) == round(1 / 3, 4)
    sent = datetime(2026, 10, 1, 12)
    assert metrics.recap_reply_rate_5bd([{"recap_sent_at": sent, "reply_on": date(2026, 10, 8)},
                                         {"recap_sent_at": sent, "reply_on": date(2026, 10, 9)},
                                         {"recap_sent_at": None}]) == 0.5
    assert metrics.hours_to_first_touch([{"demo_end": end, "first_touch_at": end + timedelta(hours=h)} for h in (2, 10, 30)]) == 10


def test_dismiss_reason_mapping_and_rule_boundaries():
    signals = Counter({"waiting_on_customer": 20, "no_time": 30, "not_relevant": 10, "already_done": 6})
    rows = {r["signal"]: r for r in metrics.diagnose(signals)}  # total 66
    assert rows["waiting_on_customer"]["candidate_cause"] == "b" and rows["no_time"]["candidate_cause"] == "c"
    assert rows["no_time"]["meets_rule"]                       # 30/66 = 45%, 30 events
    assert rows["waiting_on_customer"]["meets_rule"]           # 20/66 = 30.3% with exactly 20 events: both met
    assert not rows["not_relevant"]["meets_rule"]              # 10/66 = 15%
    assert rows["waiting_on_customer"]["share_of_non_actions"] == round(20 / 66, 4)


def test_rule_needs_both_share_and_count():
    rows = {r["signal"]: r for r in metrics.diagnose(Counter({"no_time": 19, "not_relevant": 1}))}
    assert rows["no_time"]["share_of_non_actions"] == 0.95 and not rows["no_time"]["meets_rule"]  # 19 < 20 events
    rows = {r["signal"]: r for r in metrics.diagnose(Counter({"no_time": 30, "not_relevant": 70}))}
    assert rows["no_time"]["meets_rule"] and rows["no_time"]["share_of_non_actions"] == 0.3   # exactly 30%


def test_win_rate_by_band_is_labeled_descriptive():
    rows = metrics.win_rate_by_tv_band([{"outcome": "won", "tv_days": 5}, {"outcome": "lost", "tv_days": 20},
                                        {"outcome": "open", "tv_days": 9}])
    assert all(r["label"] == "correlational; underpowered at 90 days" for r in rows)
    assert rows[0]["win_rate"] == 1.0 and rows[1]["win_rate"] is None


def test_decision_table_labels_thresholds_as_proposed():
    rows = metrics.decision_table({})
    assert rows and all(r["thresholds"] == "proposed, to agree with sales leadership" for r in rows)
    assert metrics.simulate_events()["label"] == "synthetic example data"


def test_every_metric_function_states_a_formula():
    import inspect
    for name, fn in inspect.getmembers(metrics, inspect.isfunction):
        if not name.startswith("_") and fn.__module__ == "src.metrics":
            assert inspect.getdoc(fn), name


# Events

def test_events_reject_unknown_and_need_dismiss_reason(tmp_path):
    db = tmp_path / "e.sqlite3"
    with pytest.raises(ValueError):
        events.log("made_up", "ae", "deal_a", db_path=db)
    with pytest.raises(ValueError):
        events.log("step_dismissed", "ae", "deal_a", db_path=db, step=0)
    events.log("step_dismissed", "ae", "deal_a", db_path=db, step=0, reason="no_time")
    assert events.list_events("deal_a", db_path=db)[0]["reason"] == "no_time"


def test_edit_ratio():
    assert events.edit_ratio("same", "same") == 0
    assert 0 < events.edit_ratio("Hi Dana, a quick recap.", "Hi Dana, a short recap.") < 0.3


# Block Kit and handoff

def sample(deal):
    return json.loads((record_store.config.ROOT / "fixtures" / "samples" / f"{deal}.json").read_text())


@pytest.mark.parametrize("deal", ["deal_a", "deal_b"])
def test_blockkit_card(deal):
    ctx = load_context(deal)
    rec = sample(deal)
    payload = blockkit.card(rec, ctx.transcript, ctx.crm)
    types = {b["type"] for b in payload["blocks"]}
    assert types <= {"header", "context", "section", "divider", "actions"}
    actions = [b for b in payload["blocks"] if b["type"] == "actions"]
    assert 1 <= len(actions) <= 3
    assert all(len(b["elements"]) == 5 for b in actions)
    text = json.dumps(payload)
    assert "Not generated from the call" in text and "Synthetic data, fictional company." in text
    for s in rec["artifacts"]["assessment"]["current"]["next_steps"]:
        quoted = ctx.transcript.get(s["evidence"][0]["utterance_id"]).text
        assert f'> \\"{quoted}\\"' in text or quoted in text  # quote text is the transcript line


def test_handoff_brief_sections_and_gaps():
    rec = sample("deal_a")
    b = handoff.brief(rec, load_context("deal_a").crm)
    assert b["label"] == "Phase 2 preview"
    assert "late load" in b["business_outcome"].lower()
    assert any("Elena Varga" in s and "not in the demo" in s for s in b["stakeholders"])
    assert any("Unknown after TV demo" in g for g in b["meddpicc_gaps"])
    assert b["suggested_first_30_days"]


def test_samples_are_labeled_and_pass_checks():
    for deal in ("deal_a", "deal_b"):
        rec = sample(deal)
        assert rec["source"] == "sample" and "Not generated from the call" in rec["sample_label"]
        assert all(c["passed"] for c in rec["checks"])
