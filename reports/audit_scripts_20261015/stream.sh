#!/bin/bash
# Stream driver: runs one market's specialist sims sequentially, resumable, logging each.
# Usage: stream.sh MARKET LOGFILE
set -u
REPO=/home/node/.openclaw/workspace/crypto
cd "$REPO"
MKT=$1
LOG=$2
START="2021-01-01T00:00:00+00:00"
END="2026-07-28T00:00:00+00:00"
# priority order: v21g portfolio weight (desc): 056, 050, 027, 035, 048, 028, 024, 004, 032
for A in alpha_056 alpha_050 alpha_027 alpha_035 alpha_048 alpha_028 alpha_024 alpha_004 alpha_032; do
  OUT="tuner/runs/v21g_direct/${MKT}_${A}.csv.gz"
  if [ -s "$OUT" ]; then echo "$(date -u +%H:%M:%S) SKIP $MKT $A (exists)" >> "$LOG"; continue; fi
  echo "$(date -u +%H:%M:%S) START $MKT $A" >> "$LOG"
  nice -n 10 env MPLCONFIGDIR=/tmp/mpl python3 /tmp/audit/sim_one.py \
    --market "$MKT" --alpha "$A" --start "$START" --end "$END" --out "$OUT" \
    >> "$LOG" 2>&1
  RC=$?
  echo "$(date -u +%H:%M:%S) DONE rc=$RC $MKT $A" >> "$LOG"
done
echo "$(date -u +%H:%M:%S) STREAM_COMPLETE $MKT" >> "$LOG"
