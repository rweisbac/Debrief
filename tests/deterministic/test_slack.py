import pytest

from src import blockkit
from src.adapters import CompositeNotifier, FileNotifier, SlackError, SlackNotifier, make_notifier

PAYLOAD = {"text": "Debrief ready for Acme.", "blocks": [
    {"type": "header", "text": {"type": "plain_text", "text": "Debrief: Acme"}},
    {"type": "actions", "elements": []}]}


class Recorder:
    def __init__(self, reply=None):
        self.bodies, self.reply = [], reply or {"ok": True, "ts": "1.2"}

    def __call__(self, body):
        self.bodies.append(body)
        return self.reply


def test_dm_goes_to_mapped_user_without_name_prefix():
    rec = Recorder()
    n = SlackNotifier("xoxb-test", users={"Sam Lee": "U111"}, post=rec)
    n.send("Sam Lee", "ae", "d", "card_ready", PAYLOAD)
    assert rec.bodies[0]["channel"] == "U111"
    assert rec.bodies[0]["text"] == "Debrief ready for Acme."


def test_unmapped_user_falls_back_to_channel_with_name():
    rec = Recorder()
    n = SlackNotifier("xoxb-test", channel="C999", users={"Sam Lee": "U111"}, post=rec)
    n.send("Priya Raman", "sc", "d", "card_ready", PAYLOAD)
    assert rec.bodies[0]["channel"] == "C999"
    assert rec.bodies[0]["text"].startswith("For Priya Raman (SC):")


def test_buttons_are_dropped_and_app_link_added():
    rec = Recorder()
    SlackNotifier("t", channel="C1", app_url="http://app.example", post=rec).send("A", "ae", "d", "k", PAYLOAD)
    blocks = rec.bodies[0]["blocks"]
    assert not any(b["type"] == "actions" for b in blocks)
    assert "http://app.example" in blocks[-1]["text"]["text"]


def test_customer_role_is_refused():
    with pytest.raises(ValueError):
        SlackNotifier("t", channel="C1", post=Recorder()).send("A", "customer", "d", "k", PAYLOAD)


def test_slack_error_raises_without_leaking_token():
    n = SlackNotifier("xoxb-secret", channel="C1", post=Recorder({"ok": False, "error": "channel_not_found"}))
    with pytest.raises(SlackError) as e:
        n.send("A", "ae", "d", "k", PAYLOAD)
    assert "channel_not_found" in str(e.value) and "xoxb-secret" not in str(e.value)


def test_composite_writes_file_even_when_slack_fails(tmp_path):
    def boom(body):
        raise OSError("network down")
    comp = CompositeNotifier(FileNotifier(tmp_path / "o.jsonl"), SlackNotifier("t", channel="C1", post=boom))
    msg = comp.send("A", "ae", "d", "k", PAYLOAD)
    assert msg["slack"]["ok"] is False and "network down" in msg["slack"]["error"]
    assert len(comp.read_all()) == 1


def test_make_notifier_is_file_only_without_token(monkeypatch):
    monkeypatch.delenv("DEBRIEF_SLACK_BOT_TOKEN", raising=False)
    assert isinstance(make_notifier(), FileNotifier)


def test_make_notifier_uses_slack_with_token(monkeypatch):
    monkeypatch.setenv("DEBRIEF_SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("DEBRIEF_SLACK_CHANNEL", "C1")
    assert isinstance(make_notifier(), CompositeNotifier)


def test_sc_card_shows_only_the_scs_items():
    import json
    from src.adapters import FileCRMSource, FileGongSource
    from src import service
    rec = json.loads((service.SAMPLES_DIR / "deal_a.json").read_text())
    crm = FileCRMSource().deal("deal_a")
    card = blockkit.sc_card(rec, FileGongSource().transcript("deal_a"), crm, [
        {"what": "Send the release note", "due": "2026-10-06", "done": False},
        {"what": "Already shipped", "due": "", "done": True}])
    text = json.dumps(card)
    assert "Send the release note" in text and "Already shipped" not in text
    assert "Make sure Mikkel" in text  # step owned by the SC
    assert "Send Elena a one page brief" not in text  # AE-owned step
