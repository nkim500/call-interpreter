def test_worker_module_imports_cleanly():
    """If imports break (e.g., LiveKit API drift), this test surfaces it fast."""
    from agent import worker  # noqa: F401


def test_worker_exposes_an_agent_server():
    from livekit.agents import AgentServer

    from agent.worker import server

    assert isinstance(server, AgentServer)


def test_worker_default_mode_is_realtime(monkeypatch):
    """If INTERPRETER_MODE is unset, the default is 'realtime'."""
    monkeypatch.delenv("INTERPRETER_MODE", raising=False)
    from agent import worker

    assert worker._resolve_requested_mode() == "realtime"


def test_worker_reads_pipelined_mode_from_env(monkeypatch):
    monkeypatch.setenv("INTERPRETER_MODE", "pipelined")
    from agent import worker

    assert worker._resolve_requested_mode() == "pipelined"
