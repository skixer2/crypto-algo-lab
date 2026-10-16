#!/bin/bash
# 056 chunk sims (sequential, nice 10), then verification compose.
set -u
REPO=/home/node/.openclaw/workspace/crypto
cd "$REPO"
LOG=/tmp/audit/chunks_056.log
mkdir -p tuner/runs/v21g_direct/chunks_056
for SPEC in "2021 2021-01-01T00:00:00+00:00 2022-01-01T00:00:00+00:00" \
            "2022 2022-01-01T00:00:00+00:00 2023-01-01T00:00:00+00:00" \
            "2023 2023-01-01T00:00:00+00:00 2024-01-01T00:00:00+00:00" \
            "2024 2024-01-01T00:00:00+00:00 2025-01-01T00:00:00+00:00" \
            "2025H1 2025-01-01T00:00:00+00:00 2026-07-28T00:00:00+00:00"; do
  set -- $SPEC
  NAME=$1; S=$2; E=$3
  OUT="tuner/runs/v21g_direct/chunks_056/ETH_alpha_056_${NAME}.csv.gz"
  if [ -s "$OUT" ]; then echo "$(date -u +%H:%M:%S) SKIP chunk $NAME" >> "$LOG"; continue; fi
  echo "$(date -u +%H:%M:%S) START chunk $NAME" >> "$LOG"
  nice -n 10 env MPLCONFIGDIR=/tmp/mpl python3 /tmp/audit/sim_one.py \
    --market ETH --alpha alpha_056 --start "$S" --end "$E" --out "$OUT" >> "$LOG" 2>&1
  echo "$(date -u +%H:%M:%S) DONE chunk $NAME rc=$?" >> "$LOG"
done
nice -n 10 env MPLCONFIGDIR=/tmp/mpl python3 /tmp/audit/verify_056.py >> "$LOG" 2>&1
echo "$(date -u +%H:%M:%S) CHUNKS_PHASE_COMPLETE rc=$?" >> "$LOG"
