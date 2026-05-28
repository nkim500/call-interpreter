"""Factory for AgentSession instances, one builder per INTERPRETER_MODE."""

from livekit.agents import AgentSession
from livekit.plugins import openai

# Default ElevenLabs voice ID. The starting value below is "Rachel" (a
# multilingual voice that handles Spanish reasonably). Once you've heard
# it on a live call, swap to a clearly Mexican Spanish voice from the
# ElevenLabs library if the default sounds off. Voice selection is one
# line; the plan's correctness doesn't depend on which voice you pick.
_DEFAULT_ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"


def build_session(mode: str) -> AgentSession:
    """Return an AgentSession configured for the requested mode.

    Modes:
      - "realtime": single-hop OpenAI Realtime (v1).
      - "pipelined": Deepgram STT + Claude LLM + ElevenLabs TTS + Silero VAD.

    Raises ValueError for any other mode.
    """
    if mode == "realtime":
        return _build_realtime_session()
    if mode == "pipelined":
        return _build_pipelined_session()
    raise ValueError(f"unknown INTERPRETER_MODE: {mode!r}")


def _build_realtime_session() -> AgentSession:
    return AgentSession(
        llm=openai.realtime.RealtimeModel(voice="coral"),
    )


def _build_pipelined_session() -> AgentSession:
    # Imports intentionally local — keeps the realtime-only path free of pipelined deps.
    from livekit.plugins import anthropic, deepgram, elevenlabs, silero

    return AgentSession(
        stt=deepgram.STT(model="nova-2-general", language="multi"),
        llm=anthropic.LLM(model="claude-sonnet-4-6"),
        tts=elevenlabs.TTS(voice_id=_DEFAULT_ELEVENLABS_VOICE_ID),
        vad=silero.VAD.load(),
        turn_detection="vad",
    )
