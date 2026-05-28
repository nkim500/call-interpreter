from livekit.agents import Agent

from agent.prompts import INTERPRETER_INSTRUCTIONS


class Interpreter(Agent):
    """
    Bilingual Spanish-English phone interpreter.

    Holds only the prompt. The voice model (OpenAI Realtime, or in the future a
    pipelined Deepgram + LLM + ElevenLabs setup) is configured one level up in
    the AgentSession, so we can swap models without touching this class.
    """

    def __init__(self) -> None:
        super().__init__(instructions=INTERPRETER_INSTRUCTIONS)
