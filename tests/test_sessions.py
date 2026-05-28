"""Tests for the build_session factory.

The factory returns a configured AgentSession for the requested mode.
We test mode dispatch and that the returned object is the right shape;
deep model behavior is validated by live calls, not unit tests.
"""

from livekit.agents import AgentSession

from agent.sessions import build_session


def test_build_session_realtime_returns_agent_session():
    session = build_session("realtime")
    assert isinstance(session, AgentSession)


def test_build_session_realtime_uses_realtime_model():
    """Sanity check that the realtime path constructs a Realtime LLM,
    not a chat LLM. Confirms we didn't wire it up wrong."""
    from livekit.plugins.openai.realtime import RealtimeModel

    session = build_session("realtime")
    assert isinstance(session.llm, RealtimeModel)


def test_build_session_pipelined_returns_agent_session(monkeypatch):
    """Pipelined session has all four model-layer components attached.

    We don't load Silero's actual VAD model in the unit test (it would
    download a file on first run); we patch VAD.load to a MagicMock instead.
    The Deepgram, Anthropic, and ElevenLabs SDKs accept arbitrary keys at
    construction (auth is checked on the first network call), so fake env
    values are sufficient here.
    """
    from unittest.mock import MagicMock
    from livekit.plugins import anthropic, deepgram, elevenlabs, silero

    monkeypatch.setattr(silero.VAD, "load", lambda *a, **kw: MagicMock())
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ELEVEN_API_KEY", "test-key")

    session = build_session("pipelined")
    assert isinstance(session, AgentSession)
    assert isinstance(session.stt, deepgram.STT)
    assert isinstance(session.llm, anthropic.LLM)
    assert isinstance(session.tts, elevenlabs.TTS)
    assert session.vad is not None  # MagicMock from the monkeypatch — class identity isn't useful here


def test_build_session_unknown_mode_raises():
    import pytest

    with pytest.raises(ValueError, match="unknown INTERPRETER_MODE"):
        build_session("garbage")
