from src import prompts
from src.config import STEP_SETTINGS

STEPS = ["extract", "assess_and_recommend", "draft_recap_email", "draft_internal_summary",
         "draft_mutual_action_plan", "verify", "judge"]


def test_every_step_has_a_prompt_and_settings():
    for step in STEPS:
        text, version = prompts.load(step)
        assert text and version.startswith("v")
        assert step in STEP_SETTINGS


def test_effort_matches_brief():
    want = {"extract": "low", "assess_and_recommend": "medium", "draft_recap_email": "low",
            "draft_internal_summary": "low", "draft_mutual_action_plan": "low", "verify": "medium"}
    assert {k: STEP_SETTINGS[k]["effort"] for k in want} == want


def test_stable_reference_contains_reference_material_in_order():
    text, _ = prompts.stable_reference()
    assert text.index("<playbook>") < text.index("<release_cards>") < text.index("<competitor_notes>")
    assert "PB-10" in text and "RC-12" in text and "Lakestream" in text


def test_prompts_do_not_ask_for_step_by_step_reasoning():
    for step in STEPS:
        text, _ = prompts.load(step)
        assert "step by step" not in text.lower() and "reasoning" not in text.lower()
