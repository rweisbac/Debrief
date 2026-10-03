"""Web confirm card, Slack interactions and CRM write-back. No network: Slack calls go to a fake."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from src import capture, config, slack_actions
from src.adapters import FileCRMWriter


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite3")
    monkeypatch.setenv("DEBRIEF_SAMPLES", "1")
    monkeypatch.setattr(FileCRMWriter, "__init__", lambda self, path=tmp_path / "crm.jsonl": setattr(self, "path", path))
    from src.web import app
    return TestClient(app)


def test_card_shows_sample_scored_by_real_code(client):
    r = client.get("/api/capture/deal_a")
    assert r.status_code == 200
    card = r.json()
    assert card["source"] == "sample" and "Not generated from the call" in card["sample_label"]
    modes = {f["field"]: f["mode"] for f in card["fields"]}
    assert modes["next_step"] == "auto" or "Spot check" in next(f["reason"] for f in card["fields"]
                                                                if f["field"] == "next_step")
    assert modes["champion_status"] == "ask"  # judgment field during the AE's first confirms
    ns = next(f for f in card["fields"] if f["field"] == "next_step")
    assert ns["quotes"][0]["text"].startswith("Thursday October 8th")  # rendered from the transcript


def test_no_basis_field_asks(client):
    card = client.get("/api/capture/deal_b").json()
    ns = next(f for f in card["fields"] if f["field"] == "next_step")
    assert ns["mode"] == "ask" and ns["confidence"] == 0.0


def test_confirm_stores_labels_writes_crm_and_returns_payoff(client, tmp_path):
    card = client.get("/api/capture/deal_a").json()
    r = client.post("/api/capture/deal_a/confirm", json={
        "capture_id": card["capture_id"], "seconds": 18.4,
        "values": {"top_risk": {"value": "competitor", "note": "x", "bogus": "dropped"}}})
    assert r.status_code == 200
    out = r.json()
    assert out["session"]["corrected"] == ["top_risk"]
    assert "bogus" not in out["session"]["final"]["top_risk"]
    crm_rows = [json.loads(line) for line in (tmp_path / "crm.jsonl").read_text().splitlines()]
    assert crm_rows[-1]["fields"]["NextStep"].startswith("45 minute session")
    assert crm_rows[-1]["fields"]["Top_Risk__c"] == "competitor"
    pay = out["payoff"]
    assert pay["available"] and pay["next_steps"] and pay["recap"]["body"]
    names = {s["name"]: s for s in pay["stakeholders"]}
    assert names["Dana Ortiz"]["stance"] == "supportive"
    assert names["Elena Varga"]["present"] is False and "BP-05" in names["Elena Varga"]["next_touch"]
    m = client.get("/metrics").json()
    assert m["measured"]["sessions"] == 1 and m["simulated"]["sessions"] == 0


def test_unknown_or_bad_deal(client):
    assert client.get("/api/capture/nope").status_code == 404
    assert client.get("/api/capture/BAD-ID").status_code == 400


def test_simulator_endpoint_clamps(client):
    r = client.get("/api/simulate", params={"threshold": 5}).json()
    assert r["threshold"] == 1.0


# Slack

def _signed(body: bytes, secret: str, ts: int | None = None) -> dict:
    ts = str(ts or int(time.time()))
    sig = "v0=" + hmac.new(secret.encode(), b"v0:" + ts.encode() + b":" + body, hashlib.sha256).hexdigest()
    return {"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": sig,
            "Content-Type": "application/x-www-form-urlencoded"}


def test_slack_signature_required(client, monkeypatch):
    monkeypatch.setenv("DEBRIEF_SLACK_SIGNING_SECRET", "s3cret")
    body = urlencode({"payload": json.dumps({"type": "block_actions", "actions": []})}).encode()
    assert client.post("/slack/interactions", content=body, headers=_signed(body, "wrong")).status_code == 401
    assert client.post("/slack/interactions", content=body,
                       headers=_signed(body, "s3cret", int(time.time()) - 600)).status_code == 401
    assert client.post("/slack/interactions", content=body, headers=_signed(body, "s3cret")).status_code == 200


class FakeSlack(slack_actions.SlackAPI):
    def __init__(self):
        self.sent = []
        super().__init__(token="x", post=lambda url, body, auth: self.sent.append((url, body)) or {"ok": True})


def _action(action_id, **extra):
    return {"type": "block_actions", "response_url": "https://hooks.slack.test/r", "trigger_id": "t1",
            "container": {"channel_id": "C1", "message_ts": "111.1"},
            "actions": [{"action_id": action_id, **extra}]}


def test_slack_select_edit_then_confirm(client, tmp_path):
    cid = "deal_a-cap-sample"
    api = FakeSlack()
    slack_actions.handle(_action(f"cap_sel|{cid}|top_risk|value", selected_option={"value": "competitor"}),
                         api, now=1000.0)
    url, redraw = api.sent[-1]
    assert url == "https://hooks.slack.test/r" and redraw["replace_original"]
    assert any("Edited" in json.dumps(b) for b in redraw["blocks"])
    slack_actions.handle(_action(f"cap_edit|{cid}|next_step"), api, now=1003.0)
    url, body = api.sent[-1]
    assert url.endswith("views.open") and body["view"]["callback_id"] == "cap_edit"
    slack_actions.handle(_action(f"cap_confirm|{cid}"), api, now=1012.5)
    url, done = api.sent[-1]
    assert done["blocks"][0]["text"]["text"].startswith("Confirmed:")
    session = capture.session_for(cid)
    assert session["seconds_to_complete"] == 12.5
    assert {l["field"] for l in session["labels"] if l["was_corrected"]} == {"top_risk"}


def test_slack_modal_save_stores_edit(client):
    cid = "deal_a-cap-sample"
    api = FakeSlack()
    payload = {"type": "view_submission", "view": {
        "callback_id": "cap_edit", "private_metadata": json.dumps({"capture_id": cid, "field": "next_step"}),
        "state": {"values": {"value": {"value": {"type": "plain_text_input", "value": "Session with Elena"}},
                             "date": {"date": {"type": "datepicker", "selected_date": "2026-10-08"}}}}}}
    assert slack_actions.handle(payload, api, now=50.0) == {"response_action": "clear"}
    assert slack_actions._draft(cid)["edits"]["next_step"] == {"value": "Session with Elena", "date": "2026-10-08"}


def test_slack_step_buttons_log_events(client):
    from src import events
    api = FakeSlack()
    slack_actions.handle(_action("dismiss_0_no_time", value=json.dumps({"deal_id": "deal_a", "step": 0,
                                                                        "reason": "no_time"})), api)
    slack_actions.handle(_action("act_1", value=json.dumps({"deal_id": "deal_a", "step": 1, "action": "send_material"})), api)
    names = [e["name"] for e in events.list_events("deal_a")]
    assert "step_dismissed" in names and "step_action_taken" in names


def test_posted_message_keeps_buttons_only_when_interactive():
    from src import blockkit
    payload = {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "x"}}, {"type": "actions", "elements": []}]}
    assert len(blockkit.slack_safe(payload, "", interactive=True)) == 2
    assert all(b["type"] != "actions" for b in blockkit.slack_safe(payload, ""))
