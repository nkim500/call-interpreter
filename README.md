# voice-agent

A simple setup for when you need a Spanish ↔ English interpreter on a phone
call. The agent joins your call as a third participant and translates both
directions in real time.

Conference in the agent's phone number while you're on a call, and it greets
both parties and interprets each turn.

## Stack

- **LiveKit Cloud** — bundled phone number, SIP routing, hosted agent
- **OpenAI Realtime API** — speech-to-speech model
- **Python 3.11+** via [`uv`](https://docs.astral.sh/uv/)

## Setup

1. Install [`uv`](https://docs.astral.sh/uv/) and the [`lk` CLI](https://docs.livekit.io/cli/).
2. `uv sync`
3. Create a LiveKit Cloud project at https://cloud.livekit.io and run `lk cloud auth`.
4. `cp .env.example .env.local` and fill in `LIVEKIT_*` and `OPENAI_API_KEY`.
5. Buy a phone number in the LiveKit dashboard (Telephony → Phone Numbers) and
   put its E.164 form (e.g. `+12025550100`) into `LIVEKIT_PHONE_NUMBER` in `.env.local`.
6. `cp livekit.toml.example livekit.toml` and fill in your project subdomain and agent ID.
7. `./scripts/setup-sip.sh` — creates the inbound trunk and the dispatch rule
   that routes calls to the interpreter agent.

## Run locally

```bash
uv run python -m agent.worker dev
```

Then dial your LiveKit number from any phone.

## Deploy

```bash
lk agent deploy
lk agent env set OPENAI_API_KEY=<your key>
lk agent status
```

## Tests

```bash
uv run pytest -v
```

## Use

1. Save your LiveKit phone number in your contacts as "Translator."
2. On a call with a Spanish-only counterparty, tap **add call → Translator →
   merge calls**.
3. The agent greets both of you in English and Spanish, then translates each turn.

## Roadmap

A v2 pipelined build (Deepgram + Claude + ElevenLabs) and other future work are
described in [ROADMAP.md](ROADMAP.md).
