# Roadmap

## v2 — pipelined interpreter (opt-in)

An alternative to the OpenAI Realtime speech-to-speech model: a pipelined stack
that swaps the model layer while keeping the same `Interpreter` class and prompt.

- **STT:** Deepgram Nova (multilingual)
- **LLM:** Claude Sonnet 4.6
- **TTS:** ElevenLabs
- **VAD:** Silero

Selectable at deploy time via the `INTERPRETER_MODE` env var (`realtime` is the
default; set `pipelined` to activate). To run pipelined mode, set
`DEEPGRAM_API_KEY`, `ANTHROPIC_API_KEY`, and `ELEVEN_API_KEY` in `.env.local`,
then push them to the deployed agent:

```bash
lk agent update-secrets --secrets-file .env.local --ignore-empty-secrets
lk agent deploy
```

> Note: `lk agent deploy` does not auto-read `.env.local`; secrets must be
> pushed explicitly with `update-secrets` first.

## Future work

- **Multi-language support** — generalize beyond Spanish ↔ English to other
  language pairs (e.g. Chinese ↔ English). The interpreter prompt, STT language
  hints, and TTS voice would become per-language configuration rather than
  hard-coded, so the same agent can serve any pair.
- **Twilio fallback** for telephony, once usage exceeds LiveKit's free inbound
  minutes.
- **Per-turn transcript + latency logging** as a JSONL stream (per-stage STT/LLM/TTS
  timings) for tuning the pipelined path.
- **Language-direction inference** in the transcript log (currently the
  `direction` field is unset).
- **Single-turn recovery** ("sorry, can you repeat?") for transient provider
  errors, beyond the existing circuit breaker for cascading failures.
- **Spanish voice tuning** — pick a Mexican-Spanish ElevenLabs voice for the
  pipelined TTS output.
