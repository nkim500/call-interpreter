from agent.prompts import INTERPRETER_INSTRUCTIONS


def test_prompt_mentions_both_languages():
    text = INTERPRETER_INSTRUCTIONS.lower()
    assert "english" in text
    assert "spanish" in text


def test_prompt_defines_translator_role():
    text = INTERPRETER_INSTRUCTIONS.lower()
    assert "interpreter" in text or "translator" in text or "translate" in text


def test_prompt_allows_mediation():
    text = INTERPRETER_INSTRUCTIONS.lower()
    assert "clarif" in text or "repeat" in text


def test_prompt_forbids_inventing_facts():
    text = INTERPRETER_INSTRUCTIONS.lower()
    assert "invent" in text or "make up" in text or "fabricate" in text


def test_prompt_handles_meta_addresses():
    text = INTERPRETER_INSTRUCTIONS.lower()
    assert "tell him" in text or "tell her" in text or "instructions to you" in text


def test_prompt_forbids_third_person_narration():
    """Pinned by an observed live-call failure: agent narrated 'He says...'
    instead of translating in first person. Prompt must explicitly forbid this."""
    text = INTERPRETER_INSTRUCTIONS.lower()
    assert "first person" in text or "first-person" in text
    assert "narrat" in text or "he says" in text


def test_prompt_strips_meta_prefix():
    """Pinned by an observed live-call failure (2026-05-09): agent translated
    'Tell him X' literally as 'Dile que X' in Spanish, instead of stripping the
    'tell him' prefix and translating only X."""
    text = INTERPRETER_INSTRUCTIONS.lower()
    assert "strip" in text
    assert "dile que" in text
