"""Tests for preflight_choose_mode and attach_circuit_breaker.

Pre-flight pings each pipelined provider at session start; if any are
unreachable, the requested mode silently downgrades from "pipelined" to
"realtime". Circuit breaker counts consecutive failures and trips after 2.

_FakeSessionForBreaker fires the real event names that attach_circuit_breaker
subscribes to:
  - "error"                     — failure signal (ErrorEvent-like namespace)
  - "conversation_item_added"   — success signal (assistant ChatMessage)

Component is identified from event.error.type ("stt_error"|"llm_error"|
"tts_error").  Unrecognised types map to "unknown".
"""

from unittest.mock import patch


class _FakeErrorEvent:
    """Minimal stand-in for LiveKit ErrorEvent."""

    def __init__(self, error_type: str):
        self.error = _FakeError(error_type)


class _FakeError:
    def __init__(self, type_str: str):
        self.type = type_str


class _FakeAssistantItem:
    role = "assistant"
    text_content = "reply"
    metrics = {}


class _FakeConversationItemAddedEvent:
    def __init__(self):
        self.item = _FakeAssistantItem()


class _FakeSessionForBreaker:
    """Stand-in that exposes on('error'/'conversation_item_added', cb)
    interface that attach_circuit_breaker subscribes to."""

    def __init__(self):
        self._handlers: dict = {}

    def on(self, event_name: str, callback):
        self._handlers[event_name] = callback

    def _fire(self, event_name: str, ev):
        handler = self._handlers.get(event_name)
        if handler is not None:
            handler(ev)

    def fire_failure(self, component: str):
        # Map component label back to the error type string.
        type_map = {"stt": "stt_error", "llm": "llm_error", "tts": "tts_error"}
        error_type = type_map.get(component, component)
        self._fire("error", _FakeErrorEvent(error_type))

    def fire_error(self, error_type: str):
        """Fire an error event directly by error_type string (no component mapping)."""
        self._fire("error", _FakeErrorEvent(error_type))

    def fire_success(self):
        self._fire("conversation_item_added", _FakeConversationItemAddedEvent())


def test_preflight_returns_realtime_unchanged():
    """When the requested mode is already 'realtime', no pings happen."""
    from agent.resilience import preflight_choose_mode

    chosen = preflight_choose_mode("realtime")
    assert chosen == "realtime"


def test_preflight_returns_pipelined_when_all_providers_healthy():
    from agent.resilience import preflight_choose_mode

    with patch("agent.resilience._ping_deepgram", return_value=True), \
         patch("agent.resilience._ping_anthropic", return_value=True), \
         patch("agent.resilience._ping_elevenlabs", return_value=True):
        chosen = preflight_choose_mode("pipelined")

    assert chosen == "pipelined"


def test_preflight_downgrades_to_realtime_on_provider_failure(caplog):
    """If any pipelined provider ping fails, the chosen mode is realtime.
    The reason gets logged so we know which provider was the cause."""
    from agent.resilience import preflight_choose_mode

    with patch("agent.resilience._ping_deepgram", return_value=True), \
         patch("agent.resilience._ping_anthropic", return_value=False), \
         patch("agent.resilience._ping_elevenlabs", return_value=True):
        with caplog.at_level("WARNING"):
            chosen = preflight_choose_mode("pipelined")

    assert chosen == "realtime"
    assert "anthropic" in caplog.text


def test_preflight_logs_all_failed_providers(caplog):
    from agent.resilience import preflight_choose_mode

    with patch("agent.resilience._ping_deepgram", return_value=False), \
         patch("agent.resilience._ping_anthropic", return_value=False), \
         patch("agent.resilience._ping_elevenlabs", return_value=True):
        with caplog.at_level("WARNING"):
            preflight_choose_mode("pipelined")

    assert "deepgram" in caplog.text
    assert "anthropic" in caplog.text


def test_circuit_breaker_does_not_trip_on_single_failure():
    """One failure isn't enough — the user might just have a noisy line."""
    from agent.resilience import attach_circuit_breaker

    tripped = []
    session = _FakeSessionForBreaker()
    attach_circuit_breaker(session, on_trip=lambda c: tripped.append(c))

    session.fire_failure(component="stt")
    assert tripped == []


def test_circuit_breaker_trips_on_two_consecutive_same_component_failures():
    from agent.resilience import attach_circuit_breaker

    tripped = []
    session = _FakeSessionForBreaker()
    attach_circuit_breaker(session, on_trip=lambda c: tripped.append(c))

    session.fire_failure(component="llm")
    session.fire_failure(component="llm")
    assert tripped == ["llm"]


def test_circuit_breaker_resets_on_successful_turn():
    """A success between two failures resets the counter — not a trip."""
    from agent.resilience import attach_circuit_breaker

    tripped = []
    session = _FakeSessionForBreaker()
    attach_circuit_breaker(session, on_trip=lambda c: tripped.append(c))

    session.fire_failure(component="tts")
    session.fire_success()
    session.fire_failure(component="tts")
    assert tripped == []


def test_circuit_breaker_counts_per_component():
    """Failures in different components don't accumulate together."""
    from agent.resilience import attach_circuit_breaker

    tripped = []
    session = _FakeSessionForBreaker()
    attach_circuit_breaker(session, on_trip=lambda c: tripped.append(c))

    session.fire_failure(component="stt")
    session.fire_failure(component="llm")
    assert tripped == []  # one stt + one llm = no trip


def test_circuit_breaker_only_fires_on_trip_once_even_after_more_failures():
    """Once tripped, additional failures don't fire on_trip again."""
    from agent.resilience import attach_circuit_breaker

    tripped = []
    session = _FakeSessionForBreaker()
    attach_circuit_breaker(session, on_trip=lambda c: tripped.append(c))

    session.fire_failure(component="llm")
    session.fire_failure(component="llm")  # trips here
    session.fire_failure(component="llm")  # ignored
    session.fire_failure(component="stt")  # also ignored
    assert tripped == ["llm"]


def test_circuit_breaker_unknown_error_type_uses_unknown_component():
    """Errors with genuinely unrecognised type map to 'unknown'."""
    from agent.resilience import attach_circuit_breaker

    tripped = []
    session = _FakeSessionForBreaker()
    attach_circuit_breaker(session, on_trip=lambda c: tripped.append(c))

    # Fire two errors with a truly unrecognised type string.
    session.fire_failure(component="some_future_error_type")  # not in the map
    session.fire_failure(component="some_future_error_type")
    assert tripped == ["unknown"]


def test_circuit_breaker_realtime_model_error_maps_to_realtime_component():
    """Realtime mode's primary failure type should be labeled 'realtime', not 'unknown'."""
    from agent.resilience import attach_circuit_breaker

    tripped = []
    session = _FakeSessionForBreaker()
    attach_circuit_breaker(session, on_trip=lambda c: tripped.append(c))

    session.fire_error(error_type="realtime_model_error")
    session.fire_error(error_type="realtime_model_error")
    assert tripped == ["realtime"]
