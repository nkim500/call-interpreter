from livekit.agents import Agent

from agent.interpreter import Interpreter
from agent.prompts import INTERPRETER_INSTRUCTIONS


def test_interpreter_is_an_agent():
    interp = Interpreter()
    assert isinstance(interp, Agent)


def test_interpreter_uses_interpreter_instructions():
    interp = Interpreter()
    # Agent stores its instructions; we check that ours were passed through.
    assert INTERPRETER_INSTRUCTIONS in interp.instructions
