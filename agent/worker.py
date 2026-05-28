"""LiveKit worker: registers the interpreter agent, opens a session per call.

Mode is selected by INTERPRETER_MODE (realtime|pipelined). Pipelined mode
runs a pre-flight check on its providers; if any are unreachable the
session downgrades silently to realtime. A circuit breaker ends the
session politely after 2 consecutive same-component failures."""

import asyncio
import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path so `from agent.X import ...` works
# whether the worker is run as `python -m agent.worker` (project root in
# path) or as `python agent/worker.py` (the form `lk agent deploy` uses
# inside its Docker build).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
from livekit import agents  # noqa: E402
from livekit.agents import AgentServer, RoomInputOptions  # noqa: E402
from livekit.plugins import noise_cancellation  # noqa: E402

from agent.interpreter import Interpreter  # noqa: E402
from agent.logging import attach_transcript_logger  # noqa: E402
from agent.resilience import attach_circuit_breaker, preflight_choose_mode  # noqa: E402
from agent.sessions import build_session  # noqa: E402

load_dotenv(".env.local")


_GREETING = (
    "Greet both parties briefly in both languages so they know you're "
    "here to translate. Example: 'Hi, I'm here to translate. "
    "Hola, voy a traducir.' Then stop talking and wait for either "
    "party to speak."
)

_TECHNICAL_ISSUES_GOODBYE = (
    "Apologize briefly in both languages and tell both parties to hang "
    "up and call back: 'Sorry, I'm having technical issues. Please hang "
    "up and call back. Disculpa, tengo problemas técnicos. Por favor "
    "cuelga y vuelve a llamar.'"
)


server = AgentServer()


def _resolve_requested_mode() -> str:
    return os.getenv("INTERPRETER_MODE", "realtime")


@server.rtc_session(agent_name="interpreter")
async def interpreter_session(ctx: agents.JobContext) -> None:
    requested = _resolve_requested_mode()
    mode = preflight_choose_mode(requested)

    session = build_session(mode)
    attach_transcript_logger(session, mode, log_dir=os.getenv("LOG_DIR"))

    async def _polite_goodbye_and_disconnect(component: str) -> None:
        await session.generate_reply(instructions=_TECHNICAL_ISSUES_GOODBYE)
        await session.aclose()

    # The circuit breaker's on_trip is a sync callback (called from a
    # sync failure handler). We schedule the async goodbye on the running
    # event loop via create_task — fire-and-forget is correct here because
    # the session is being torn down.
    attach_circuit_breaker(
        session,
        on_trip=lambda component: asyncio.create_task(
            _polite_goodbye_and_disconnect(component)
        ),
    )

    await session.start(
        room=ctx.room,
        agent=Interpreter(),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
        ),
    )

    await session.generate_reply(instructions=_GREETING)


if __name__ == "__main__":
    agents.cli.run_app(server)
