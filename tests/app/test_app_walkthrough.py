"""Drive app.py headless with Streamlit AppTest through the full demo path. No network (sockets blocked)."""
import json

import pytest
from streamlit.testing.v1 import AppTest

from src import adapters, events, record_store


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DEBRIEF_SAMPLES", "1")
    monkeypatch.setenv("DEBRIEF_DB", str(tmp_path / "app.sqlite3"))
    monkeypatch.setattr(adapters, "VAR", tmp_path)
    monkeypatch.setattr(adapters.FileNotifier.__init__, "__defaults__", (tmp_path / "outbox.jsonl",))
    import src.config as config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.sqlite3")
    at = AppTest.from_file(str(config.ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    return at


def button(at, label):
    return next(b for b in at.button if b.label == label)


def names():
    return [e["name"] for e in events.list_events("deal_a")]


def test_every_role_renders_without_errors(app):
    for role in ["AE", "SC", "Sales manager", "CSM", "Measurement"]:
        app.sidebar.radio(key="role").set_value(role).run()
        assert not app.exception, role
        assert any("Synthetic data, fictional company." in i.value for i in app.info)


def test_sample_label_shown(app):
    assert any("Not generated from the call" in w.value for w in app.warning)


def test_full_demo_path(app, tmp_path):
    at = app
    # 1. close-the-demo checklist, filled before the call ends
    at.text_input[0].set_value("Thu Oct 8, 2pm, session with Elena Varga")
    at.text_input[1].set_value("Elena Varga, COO")
    at.text_input[2].set_value("Priya: partner policy by Tue Oct 6")
    button(at, "Save checklist").click().run()
    assert "demo_checklist_started" in names()
    # 2. demo ends, card appears
    button(at, "End demo and build the card").click().run()
    assert not at.exception
    assert {"card_generated", "card_opened"} <= set(names())
    assert names().count("demo_checklist_filled_before_call_end") == 4
    assert any("Most important" in m.value for m in at.markdown)
    # 3. why expander shows the quote rendered from the transcript
    at.toggle(key="why_deal_a_0").set_value(True).run()
    assert "step_expanded" in names()
    assert any("She is going to ask about time to value" in m.value for m in at.markdown)
    # 4. dismiss one step with a reason, act on another
    at.button(key="dis_deal_a_2_no_time").click().run()
    at.button(key="act_deal_a_0").click().run()
    dismissed = events.list_events("deal_a", "step_dismissed")
    assert dismissed[0]["reason"] == "no_time" and dismissed[0]["step"] == 2
    assert events.list_events("deal_a", "step_action_taken")[0]["step"] == 0
    # 5. edit and approve the recap, then mark it sent
    body = at.text_area(key="body_deal_a")
    body.set_value(body.value.replace("A quick recap.", "A short recap.")).run()
    at.button(key="approve_deal_a").click().run()
    approved = events.list_events("deal_a", "draft_approved")[0]
    assert 0 < approved["edit_ratio"] < 0.3
    assert "draft_edited" in names()
    at.button(key="sent_deal_a").click().run()
    assert "draft_marked_sent" in names()
    # 6. record saved
    assert record_store.load_latest_debrief("deal_a") is not None
    # 7. simulated clock: Priya's partner policy (due Oct 6) is past due on Wed Oct 7 at 12:47 local
    at.sidebar.slider(key="hours").set_value(170).run()
    nudges = events.list_events("deal_a", "nudge_sent")
    assert nudges and nudges[0]["kind"].startswith("sc_commitment_past_due")
    # 8. deal advances, SC gets the loop closing note
    at.button(key="out_deal_a_advanced").click().run()
    outbox = [json.loads(l) for l in (tmp_path / "outbox.jsonl").read_text().splitlines()]
    assert any(m["role"] == "sc" and m["kind"] == "loop_closure" for m in outbox)
    at.sidebar.radio(key="role").set_value("SC").run()
    assert any("was marked advanced" in t.value for t in at.text)
    # 9. closed won, CSM sees the handoff brief
    at.sidebar.radio(key="role").set_value("AE").run()
    at.button(key="out_deal_a_closed_won").click().run()
    at.sidebar.radio(key="role").set_value("CSM").run()
    assert any("Phase 2 preview" in m.value for m in at.markdown)
    assert "handoff_brief_viewed" in names()
    # 10. measurement tab shows events, dismiss breakdown and decision table
    at.sidebar.radio(key="role").set_value("Measurement").run()
    assert not at.exception
    assert any("Decision table" in h.value for h in at.subheader)
    assert any("synthetic example data" in c.value.lower() for c in at.caption)


def test_approve_disabled_when_needs_review(app, tmp_path):
    from src import service
    rec, _ = service.load_debrief("deal_b")
    rec = json.loads(json.dumps(rec))
    rec["artifacts"]["recap_email"]["needs_review"] = True
    rec["artifacts"]["recap_email"]["flagged"] = ["[email_promises_uncommitted] planted for the test"]
    rec["source"] = "saved"
    record_store.save_debrief("deal_b-test", "deal_b", {}, rec)
    app.sidebar.selectbox(key="deal").set_value("deal_b").run()
    button(app, "End demo and build the card").click().run()
    assert app.button(key="approve_deal_b").disabled
    assert any("Needs review" in e.value for e in app.error)
