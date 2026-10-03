import json
import shutil

import pytest

from src import config, ingest
from src.adapters import DATA, FileCRMSource, FileGongSource, FileNotifier
from src.llm import LLMClient
from tests.fakes import FakeBackend, scripted_clean_run


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A data dir where deal_new is a copy of deal_a, plus an isolated database, ledger and outbox."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite3")
    data = tmp_path / "data"
    for sub in ("transcripts", "crm", "gong_activity"):
        (data / sub).mkdir(parents=True)
    ext = {"transcripts": "txt", "crm": "json", "gong_activity": "json"}
    for sub, e in ext.items():
        shutil.copy(DATA / sub / f"deal_a.{e}", data / sub / f"deal_new.{e}")
    crm_path = data / "crm" / "deal_new.json"
    crm = json.loads(crm_path.read_text())
    crm["deal_id"] = "deal_new"
    crm_path.write_text(json.dumps(crm))

    def make_llm(fb):
        return LLMClient(mode="live", backend=fb, db_path=tmp_path / "t.sqlite3", replay_dir=tmp_path / "rp",
                         redact=lambda s: s)

    return {"data": data, "tmp": tmp_path, "crm_path": crm_path, "crm": crm, "make_llm": make_llm,
            "kwargs": dict(gong=FileGongSource(data), crm_source=FileCRMSource(data),
                           notifier=FileNotifier(tmp_path / "outbox.jsonl"), ledger_path=tmp_path / "ledger.json")}


def run(env, fb, deal="deal_new"):
    return ingest.process_call(deal, llm=env["make_llm"](fb), **env["kwargs"])


def test_new_tv_transcript_makes_a_card_and_notifies_the_ae_and_sc(env):
    fb = scripted_clean_run(FakeBackend())
    r = run(env, fb)
    assert r["status"] == "done"
    assert len(fb.requests) == 6
    msgs = env["kwargs"]["notifier"].read_all()
    assert [(m["role"], m["kind"], m["recipient"]) for m in msgs] == [
        ("ae", "card_ready", env["crm"]["owner_ae"]), ("sc", "card_ready", env["crm"]["sc"])]
    ae, sc = msgs
    assert ae["payload"]["text"].startswith("Debrief ready for Halvorsen Freight. Most important:")
    assert any(b["type"] == "actions" for b in ae["payload"]["blocks"])
    assert sc["payload"]["blocks"][0]["text"]["text"].startswith("Your items:")


def test_same_transcript_is_not_run_twice(env):
    fb = scripted_clean_run(FakeBackend())
    assert run(env, fb)["status"] == "done"
    again = run(env, FakeBackend())  # an empty backend would raise if the chain ran
    assert again["status"] == "skipped"
    assert len(env["kwargs"]["notifier"].read_all()) == 2


def test_changed_transcript_runs_again(env):
    run(env, scripted_clean_run(FakeBackend()))
    path = env["data"] / "transcripts" / "deal_new.txt"
    path.write_text(path.read_text() + "\n[59:50] Sam Lee: Thanks everyone, talk soon.\n")
    r = run(env, scripted_clean_run(FakeBackend()))
    assert r["status"] == "done"


def test_non_tv_stage_is_skipped_without_model_calls(env):
    env["crm"]["stage"] = "Discovery"
    env["crm_path"].write_text(json.dumps(env["crm"]))
    fb = FakeBackend()
    assert run(env, fb)["status"] == "skipped"
    assert fb.requests == []


def test_missing_crm_or_activity_waits_and_does_not_ledger(env):
    (env["data"] / "gong_activity" / "deal_new.json").unlink()
    assert run(env, FakeBackend())["status"] == "waiting"
    assert not env["kwargs"]["ledger_path"].exists()


def test_failed_run_retries_once_then_stops(env):
    # an empty backend raises inside the chain
    first, second, third = (run(env, FakeBackend()) for _ in range(3))
    assert first["status"] == "error" and second["status"] == "error"
    assert third["status"] == "skipped"
    assert env["kwargs"]["notifier"].read_all() == []


def test_scan_once_finds_calls_from_the_source(env):
    results = ingest.scan_once(env["kwargs"]["gong"], llm=env["make_llm"](scripted_clean_run(FakeBackend())),
                               crm_source=env["kwargs"]["crm_source"], notifier=env["kwargs"]["notifier"],
                               ledger_path=env["kwargs"]["ledger_path"])
    assert [(r["deal_id"], r["status"]) for r in results] == [("deal_new", "done")]


def test_saved_card_is_marked_auto_and_logged(env):
    from src import events, record_store
    run(env, scripted_clean_run(FakeBackend()))
    assert record_store.load_latest_debrief("deal_new")["source"] == "auto"
    assert len(events.list_events("deal_new", "card_generated")) == 1


def _check(secret, body, given="s3cret"):
    raw = body.encode()
    return ingest.check_webhook("s3cret", given if secret else "", len(raw), lambda n: raw[:n])


def test_webhook_rejects_bad_secret_and_bad_body():
    ok = json.dumps({"deal_id": "deal_new"})
    assert _check(True, ok, given="wrong")[0] == 401
    assert _check(True, json.dumps({"deal_id": "../etc"}))[0] == 400
    assert _check(True, "not json")[0] == 400
    assert _check(True, json.dumps([1]))[0] == 400
    assert ingest.check_webhook("s3cret", "s3cret", ingest.MAX_BODY_BYTES + 1, lambda n: b"")[0] == 413


def test_webhook_accepts_valid_call():
    code, body, deal_id = _check(True, json.dumps({"deal_id": "deal_new"}))
    assert (code, deal_id) == (202, "deal_new")


def test_serve_refuses_to_start_without_a_secret(monkeypatch):
    monkeypatch.delenv("DEBRIEF_WEBHOOK_SECRET", raising=False)
    with pytest.raises(SystemExit):
        ingest.serve()
