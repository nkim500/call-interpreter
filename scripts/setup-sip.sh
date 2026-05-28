#!/usr/bin/env bash
# Create the inbound SIP trunk (with the phone number from .env.local) and
# the dispatch rule that routes calls to the interpreter agent.
#
# Idempotency: this script CREATES new trunk/dispatch resources every time
# it runs. If you already have them set up, you don't need to run it again.
# To re-create from scratch, delete the existing resources first via
# `lk sip inbound delete <id>` and `lk sip dispatch delete <id>`.

set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env.local ]; then
  echo "ERROR: .env.local not found. Copy .env.example and fill it in first." >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env.local
set +a

if [ -z "${LIVEKIT_PHONE_NUMBER:-}" ]; then
  echo "ERROR: LIVEKIT_PHONE_NUMBER not set in .env.local" >&2
  exit 1
fi

echo "Creating inbound trunk for ${LIVEKIT_PHONE_NUMBER}..."
sed "s/__PHONE_NUMBER__/${LIVEKIT_PHONE_NUMBER}/" livekit/inbound-trunk.json \
  | lk sip inbound create /dev/stdin

echo "Creating dispatch rule for agent 'interpreter'..."
lk sip dispatch create livekit/dispatch-rule.json

echo "Done. Verify with: lk sip inbound list && lk sip dispatch list"
