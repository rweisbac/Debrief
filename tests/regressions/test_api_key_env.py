"""The key can live in DEBRIEF_API_KEY when the cloud environment drops ANTHROPIC_API_KEY."""
from src import config


def test_debrief_api_key_wins(monkeypatch):
    monkeypatch.setenv("DEBRIEF_API_KEY", "debrief-fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-fake")
    assert config.api_key() == "debrief-fake"


def test_falls_back_to_anthropic_api_key(monkeypatch):
    monkeypatch.delenv("DEBRIEF_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-fake")
    assert config.api_key() == "anthropic-fake"


def test_none_when_neither_set(monkeypatch):
    monkeypatch.delenv("DEBRIEF_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert config.api_key() is None
