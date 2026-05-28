"""Pre-flight health check + circuit breaker for the pipelined mode.

preflight_choose_mode pings the three pipelined providers. If any is
unreachable, the requested mode silently downgrades to 'realtime'.

attach_circuit_breaker counts consecutive same-component turn failures
and fires on_trip after 2 in a row, ending the session politely.
"""

import logging
import os
from dataclasses import dataclass
from typing import Callable

import httpx

logger = logging.getLogger(__name__)

_PREFLIGHT_TIMEOUT_S = 3.0


def preflight_choose_mode(requested: str) -> str:
    """Return the mode that should actually be used.

    If requested == 'realtime', no pings happen.
    If requested == 'pipelined', ping each provider; downgrade to 'realtime'
    if any returns False (unreachable, auth error, etc.). The reason is logged.
    """
    if requested != "pipelined":
        return requested

    checks = {
        "deepgram": _ping_deepgram,
        "anthropic": _ping_anthropic,
        "elevenlabs": _ping_elevenlabs,
    }
    failures = [name for name, ping in checks.items() if not ping()]
    if failures:
        logger.warning(
            "preflight: downgrading pipelined -> realtime; failed: %s",
            ", ".join(failures),
        )
        return "realtime"
    return "pipelined"


def _ping_deepgram() -> bool:
    """GET /v1/projects with the API key — auth-only smoke check."""
    key = os.getenv("DEEPGRAM_API_KEY", "")
    if not key:
        return False
    try:
        r = httpx.get(
            "https://api.deepgram.com/v1/projects",
            headers={"Authorization": f"Token {key}"},
            timeout=_PREFLIGHT_TIMEOUT_S,
        )
        return r.status_code < 500 and r.status_code != 401
    except httpx.HTTPError:
        return False


def _ping_anthropic() -> bool:
    """POST /v1/messages with max_tokens=1 — cheapest possible auth+up check (~$0.001)."""
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        return False
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "ping"}],
            },
            timeout=_PREFLIGHT_TIMEOUT_S,
        )
        return r.status_code < 500 and r.status_code != 401
    except httpx.HTTPError:
        return False


def _ping_elevenlabs() -> bool:
    """GET /v1/user — auth-only smoke check, no quota burn."""
    key = os.getenv("ELEVEN_API_KEY", "")
    if not key:
        return False
    try:
        r = httpx.get(
            "https://api.elevenlabs.io/v1/user",
            headers={"xi-api-key": key},
            timeout=_PREFLIGHT_TIMEOUT_S,
        )
        return r.status_code < 500 and r.status_code != 401
    except httpx.HTTPError:
        return False


@dataclass
class _BreakerState:
    component: str | None = None
    count: int = 0
    tripped: bool = False


_CIRCUIT_BREAKER_THRESHOLD = 2

# Map from ErrorEvent.error.type to the human-readable component label.
_ERROR_TYPE_TO_COMPONENT = {
    "stt_error": "stt",
    "llm_error": "llm",
    "tts_error": "tts",
    "realtime_model_error": "realtime",
    "interruption_detection_error": "interruption",
}


def attach_circuit_breaker(session, on_trip: Callable[[str], None]) -> None:
    """Subscribe to real AgentSession events and trip after THRESHOLD
    consecutive same-component failures.

    Events subscribed:
      - ``error`` — the real LiveKit ErrorEvent. The component is identified
        from ``event.error.type`` which is one of ``"stt_error"``,
        ``"llm_error"``, or ``"tts_error"``. If the error payload doesn't
        carry a recognisable type (e.g. RealtimeModelError or an unexpected
        exception), the component is labelled ``"unknown"`` and counted as
        its own bucket.
      - ``conversation_item_added`` (role="assistant") — a successfully
        completed assistant reply signals a clean turn; resets the counter.

    on_trip is called with the offending component name ("stt"|"llm"|"tts"|
    "unknown"). Caller is responsible for ending the session — we just signal.
    """
    state = _BreakerState()

    def _on_error(ev) -> None:
        if state.tripped:
            return
        error_obj = ev.error if hasattr(ev, "error") else ev
        error_type = getattr(error_obj, "type", None)
        component = _ERROR_TYPE_TO_COMPONENT.get(error_type, "unknown")

        if state.component == component:
            state.count += 1
        else:
            state.component = component
            state.count = 1
        if state.count >= _CIRCUIT_BREAKER_THRESHOLD:
            state.tripped = True
            # Once tripped, suppression is permanent — caller is expected
            # to end the session, so the breaker doesn't need to reset.
            logger.warning("circuit breaker tripped on component=%s", component)
            on_trip(component)

    def _on_conversation_item_added(ev) -> None:
        item = ev.item if hasattr(ev, "item") else None
        if item is not None and hasattr(item, "role") and item.role == "assistant":
            # A clean assistant turn — reset the consecutive-error counter.
            state.component = None
            state.count = 0

    session.on("error", _on_error)
    session.on("conversation_item_added", _on_conversation_item_added)
