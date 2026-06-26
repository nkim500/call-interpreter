"""Tests for attach_transcript_logger.

The logger hooks real AgentSession events (user_input_transcribed,
conversation_item_added, close) and emits one JSONL line per turn.
We test the public behavior (a JSONL line with the expected schema gets
written to stdout) using a fake session that fires synthetic events.

FakeSession mimics the real AgentSession.on(event, callback) API and
provides helper methods to fire individual events with minimal payloads.
"""

import json
import time

from agent.transcript_logger import attach_transcript_logger


class _SimpleNamespace:
    """Lightweight stand-in for Pydantic model instances."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def get(self, key, default=None):
        return getattr(self, key, default)


class FakeSession:
    """Minimal stand-in for AgentSession.

    Stores callbacks registered via on() and exposes helpers to fire
    the real event names that the rewired logging module subscribes to:
      - user_input_transcribed
      - conversation_item_added
      - close
    """

    def __init__(self):
        self._handlers: dict = {}

    def on(self, event_name: str, callback):
        self._handlers[event_name] = callback

    def _fire(self, event_name: str, ev):
        handler = self._handlers.get(event_name)
        if handler is not None:
            handler(ev)

    def fire_user_input_transcribed(self, transcript: str, is_final: bool = True):
        ev = _SimpleNamespace(
            transcript=transcript,
            is_final=is_final,
            created_at=time.time(),
        )
        self._fire("user_input_transcribed", ev)

    def fire_conversation_item_added_user(self, transcript: str, transcription_delay_s: float = 0.3):
        """Fire a conversation_item_added event for a user ChatMessage."""
        metrics = {"transcription_delay": transcription_delay_s}
        item = _SimpleNamespace(
            role="user",
            text_content=transcript,
            metrics=metrics,
        )
        ev = _SimpleNamespace(item=item, created_at=time.time())
        self._fire("conversation_item_added", ev)

    def fire_conversation_item_added_assistant(
        self,
        text: str,
        llm_ttft_s: float = 0.4,
        tts_ttfb_s: float = 0.18,
    ):
        """Fire a conversation_item_added event for an assistant ChatMessage."""
        metrics = {
            "llm_node_ttft": llm_ttft_s,
            "tts_node_ttfb": tts_ttfb_s,
        }
        item = _SimpleNamespace(
            role="assistant",
            text_content=text,
            metrics=metrics,
        )
        ev = _SimpleNamespace(item=item, created_at=time.time())
        self._fire("conversation_item_added", ev)

    def fire_close(self):
        ev = _SimpleNamespace(reason="job_shutdown")
        self._fire("close", ev)


def test_logger_writes_jsonl_to_stdout(capsys):
    session = FakeSession()
    attach_transcript_logger(session, mode="pipelined", log_dir=None)

    session.fire_user_input_transcribed("I'm in apartment 3B.")
    session.fire_conversation_item_added_user("I'm in apartment 3B.", transcription_delay_s=0.312)
    session.fire_conversation_item_added_assistant(
        "Estoy en el apartamento 3B.",
        llm_ttft_s=0.410,
        tts_ttfb_s=0.180,
    )

    captured = capsys.readouterr().out.strip()
    assert captured  # non-empty
    line = json.loads(captured)
    assert line["mode"] == "pipelined"
    assert line["heard_text"] == "I'm in apartment 3B."
    assert line["translated_text"] == "Estoy en el apartamento 3B."
    assert line["stt_ms"] == 312
    assert line["llm_first_token_ms"] == 410
    assert line["tts_first_byte_ms"] == 180
    assert line["total_turn_ms"] >= 0
    assert "ts" in line  # ISO timestamp added automatically


def test_logger_realtime_mode_has_null_per_stage_fields(capsys):
    """In realtime mode the assistant ChatMessage carries no pipeline metrics."""
    session = FakeSession()
    attach_transcript_logger(session, mode="realtime", log_dir=None)

    session.fire_user_input_transcribed("Hello.")
    # Realtime: no user ChatMessage with metrics; assistant has no llm/tts fields.
    metrics = {}  # empty — no pipeline metrics
    item = _SimpleNamespace(role="assistant", text_content=None, metrics=metrics)
    ev = _SimpleNamespace(item=item, created_at=time.time())
    session._fire("conversation_item_added", ev)

    line = json.loads(capsys.readouterr().out.strip())
    assert line["mode"] == "realtime"
    assert line["heard_text"] == "Hello."
    assert line["llm_first_token_ms"] is None
    assert line["tts_first_byte_ms"] is None
    assert line["stt_ms"] is None
    assert line["total_turn_ms"] >= 0


def test_logger_writes_jsonl_to_file_when_log_dir_set(tmp_path, capsys):
    session = FakeSession()
    attach_transcript_logger(session, mode="pipelined", log_dir=str(tmp_path))

    session.fire_user_input_transcribed("Estoy en la puerta.")
    session.fire_conversation_item_added_user("Estoy en la puerta.", transcription_delay_s=0.2)
    session.fire_conversation_item_added_assistant(
        "I'm at the door.",
        llm_ttft_s=0.3,
        tts_ttfb_s=0.15,
    )

    # Both stdout and file should have the line
    stdout_line = capsys.readouterr().out.strip()
    assert json.loads(stdout_line)["heard_text"] == "Estoy en la puerta."

    log_files = list(tmp_path.glob("turns-*.jsonl"))
    assert len(log_files) == 1
    file_line = log_files[0].read_text(encoding="utf-8").strip()
    assert json.loads(file_line)["heard_text"] == "Estoy en la puerta."


def test_logger_ignores_interim_transcripts(capsys):
    """Partial (non-final) user_input_transcribed events are silently dropped."""
    session = FakeSession()
    attach_transcript_logger(session, mode="pipelined", log_dir=None)

    # Fire an interim transcript — should NOT set heard_text.
    session.fire_user_input_transcribed("part", is_final=False)
    # Then fire the real final transcript.
    session.fire_user_input_transcribed("Complete sentence.", is_final=True)
    session.fire_conversation_item_added_assistant("La frase completa.")

    line = json.loads(capsys.readouterr().out.strip())
    assert line["heard_text"] == "Complete sentence."


def test_logger_keeps_first_user_transcript_when_two_finals_arrive(capsys):
    """Two consecutive final user transcripts before assistant reply: keep the first."""
    session = FakeSession()
    attach_transcript_logger(session, mode="pipelined", log_dir=None)

    # Fire two final user transcripts with controlled timestamps.
    ev1 = _SimpleNamespace(transcript="First.", is_final=True, created_at=1.0)
    session._fire("user_input_transcribed", ev1)
    ev2 = _SimpleNamespace(transcript="Second.", is_final=True, created_at=2.0)
    session._fire("user_input_transcribed", ev2)

    # Fire the assistant reply with a controlled turn-end timestamp.
    metrics = {"llm_node_ttft": 0.2, "tts_node_ttfb": 0.3}
    item = _SimpleNamespace(
        role="assistant",
        text_content="Hi.",
        metrics=metrics,
    )
    ev_asst = _SimpleNamespace(item=item, created_at=3.0)
    session._fire("conversation_item_added", ev_asst)

    line = json.loads(capsys.readouterr().out.strip())
    assert line["heard_text"] == "First."
    # turn_start was 1.0, turn_end was 3.0, so total should be 2000ms
    assert line["total_turn_ms"] == 2000


def test_logger_close_closes_file(tmp_path, capsys):
    """close event should flush and close the log file handle."""
    session = FakeSession()
    attach_transcript_logger(session, mode="pipelined", log_dir=str(tmp_path))

    session.fire_user_input_transcribed("Test.")
    session.fire_conversation_item_added_assistant("Prueba.")
    session.fire_close()

    # After close, the file should exist with content.
    log_files = list(tmp_path.glob("turns-*.jsonl"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    assert "Test." in content
