"""Pytest configuration for voice-agent tests."""

import pytest


@pytest.fixture(autouse=True)
def fake_openai_key(monkeypatch):
    """Set a fake OPENAI_API_KEY so SDK constructors don't raise.

    Unit tests are hermetic — no real secrets, no .env.local dependency.
    Live behaviour is validated by integration tests, not here.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
