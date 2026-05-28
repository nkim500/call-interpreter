"""Per-turn transcript + latency logger.

Writes one JSON line per turn to stdout (always) and optionally to a
local file (when log_dir is provided). Designed for both pipelined and
realtime modes — fields that don't apply in realtime are simply None.

Event wiring (real LiveKit AgentSession events):
- ``user_input_transcribed`` → heard_text + turn-start timestamp
- ``conversation_item_added`` (role="user") → stt_ms via
  ChatMessage.metrics["transcription_delay"] (seconds → ms)
- ``conversation_item_added`` (role="assistant") → translated_text +
  llm_first_token_ms (metrics["llm_node_ttft"]) +
  tts_first_byte_ms (metrics["tts_node_ttfb"]) + turn-end (emit JSONL)
- ``close`` → flush and close the log file

Latency notes:
- stt_ms is derived from ChatMessage.metrics["transcription_delay"],
  which is the time from end-of-speech to transcript availability. This
  is the STT processing delay, not the total audio duration.
- llm_first_token_ms / tts_first_byte_ms are from the assistant
  ChatMessage.metrics["llm_node_ttft"] and ["tts_node_ttfb"], which are
  pipeline-node latencies measured by livekit-agents internally.
- total_turn_ms is derived from user_input_transcribed.created_at to
  conversation_item_added(assistant).created_at. In realtime mode,
  these timestamps are still available but the per-stage breakdowns are
  absent (llm/tts metrics are None because there is no STT→LLM→TTS
  pipeline).
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class TurnEvent:
    """One conversational turn's transcript + latency profile."""
    mode: str            # "realtime" | "pipelined"
    direction: str | None  # "en->es" | "es->en" | None when unknown
    heard_text: Optional[str]
    translated_text: Optional[str]
    stt_ms: Optional[int]
    llm_first_token_ms: Optional[int]
    tts_first_byte_ms: Optional[int]
    total_turn_ms: int


def attach_transcript_logger(session, mode: str, log_dir: Optional[str]) -> None:
    """Subscribe to real AgentSession events and write one JSONL line per turn.

    Always writes to stdout (one line per turn).
    Also writes to {log_dir}/turns-{YYYY-MM-DD}.jsonl when log_dir is set.

    Events subscribed:
      - user_input_transcribed (heard_text, turn start timer)
      - conversation_item_added (stt_ms from user message; translated_text +
        per-stage latencies + turn emit from assistant message)
      - close (file teardown)
    """
    file_handle = None
    if log_dir:
        log_path = Path(log_dir) / f"turns-{datetime.now(timezone.utc).date().isoformat()}.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handle = log_path.open("a", encoding="utf-8")

    # Accumulate state across events for the current turn.
    _state: dict = {
        "heard_text": None,
        "stt_ms": None,
        "turn_start": None,   # created_at float from user_input_transcribed
    }

    def _emit_turn(event: TurnEvent) -> None:
        record = asdict(event)
        record["ts"] = datetime.now(timezone.utc).isoformat()
        line = json.dumps(record, ensure_ascii=False)
        print(line, flush=True)
        if file_handle is not None:
            file_handle.write(line + "\n")
            file_handle.flush()

    def _on_user_input_transcribed(ev) -> None:
        # Only capture final transcripts (not interim partials).
        if not ev.is_final:
            return
        # Keep the FIRST final transcript of a turn. Subsequent finals before
        # an assistant reply (retransmit, double-emit, barge-in) are dropped
        # so the JSONL record reflects what actually started the turn.
        if _state["heard_text"] is not None:
            return
        _state["heard_text"] = ev.transcript
        _state["turn_start"] = ev.created_at

    def _on_conversation_item_added(ev) -> None:
        item = ev.item
        # item is a ChatMessage (or AgentHandoff / unknown discriminator)
        if not hasattr(item, "role"):
            return

        if item.role == "user":
            # Grab the STT processing latency from the user ChatMessage metrics.
            metrics = item.metrics if hasattr(item, "metrics") else {}
            delay = metrics.get("transcription_delay") if metrics else None
            _state["stt_ms"] = int(delay * 1000) if delay is not None else None

        elif item.role == "assistant":
            # Assistant message signals end of turn — emit the JSONL record.
            metrics = item.metrics if hasattr(item, "metrics") else {}
            llm_ttft = metrics.get("llm_node_ttft") if metrics else None
            tts_ttfb = metrics.get("tts_node_ttfb") if metrics else None

            turn_start = _state.get("turn_start")
            turn_end = ev.created_at
            total_ms = (
                int((turn_end - turn_start) * 1000)
                if turn_start is not None
                else 0
            )

            translated_text = item.text_content if hasattr(item, "text_content") else None

            turn_event = TurnEvent(
                mode=mode,
                direction=None,  # caller can override by wrapping this function
                heard_text=_state.get("heard_text"),
                translated_text=translated_text,
                stt_ms=_state.get("stt_ms"),
                llm_first_token_ms=int(llm_ttft * 1000) if llm_ttft is not None else None,
                tts_first_byte_ms=int(tts_ttfb * 1000) if tts_ttfb is not None else None,
                total_turn_ms=total_ms,
            )
            _emit_turn(turn_event)

            # Reset per-turn state for the next turn.
            _state["heard_text"] = None
            _state["stt_ms"] = None
            _state["turn_start"] = None

    def _on_close(ev) -> None:
        if file_handle is not None:
            try:
                file_handle.close()
            except Exception:
                pass

    session.on("user_input_transcribed", _on_user_input_transcribed)
    session.on("conversation_item_added", _on_conversation_item_added)
    session.on("close", _on_close)
