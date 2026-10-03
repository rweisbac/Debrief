from src.config import apply_api_key_alias


def test_debrief_key_fills_anthropic_key():
    env = {"DEBRIEF_API_KEY": "k-debrief"}
    apply_api_key_alias(env)
    assert env["ANTHROPIC_API_KEY"] == "k-debrief"


def test_explicit_anthropic_key_wins():
    env = {"DEBRIEF_API_KEY": "k-debrief", "ANTHROPIC_API_KEY": "k-anthropic"}
    apply_api_key_alias(env)
    assert env["ANTHROPIC_API_KEY"] == "k-anthropic"


def test_no_keys_leaves_env_empty():
    env = {}
    apply_api_key_alias(env)
    assert "ANTHROPIC_API_KEY" not in env
