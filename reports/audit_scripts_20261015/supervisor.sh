#!/bin/bash
# Overnight audit supervisor — chains phases with output-existence checks.
# P1: wait SOL curves (9) -> compose SOL
# P2: wait BTC curves (9) -> compose BTC
# P3: chunks_056 stream + jitter stream (2 cores)
# P4: final marker
set -u
cd /home/node/.openclaw/workspace/crypto
SUP=/tmp/audit/supervisor.log
log(){ echo "$(date -u +%H:%M:%S) $*" >> "$SUP"; }

wait_count(){ # $1 glob $2 n
  while true; do
    N=$(ls -1 $1 2>/dev/null | wc -l)
    [ "$N" -ge "$2" ] && break
    sleep 90
  done
}

log "SUPERVISOR start — waiting SOL 9 curves"
wait_count "tuner/runs/v21g_direct/SOL_alpha_*.csv.gz" 9
log "SOL curves complete -> compose"
MPLCONFIGDIR=/tmp/mpl python3 /tmp/audit/compose_transplant.py --market SOL >> "$SUP" 2>&1
log "compose SOL rc=$?"

log "waiting BTC 9 curves"
wait_count "tuner/runs/v21g_direct/BTC_alpha_*.csv.gz" 9
log "BTC curves complete -> compose"
MPLCONFIGDIR=/tmp/mpl python3 /tmp/audit/compose_transplant.py --market BTC >> "$SUP" 2>&1
log "compose BTC rc=$?"

log "launching chunks_056 + jitter streams"
setsid nohup /tmp/audit/chunks_056.sh > /dev/null 2>&1 < /dev/null &
setsid nohup env MPLCONFIGDIR=/tmp/mpl python3 /tmp/audit/jitter_driver.py > /tmp/audit/jitter.log 2>&1 < /dev/null &

# P4: jitter done when driver prints complete (poll its log tail marker)
while ! grep -q "JITTER_PHASE_COMPLETE" /tmp/audit/jitter.log 2>/dev/null; do
  sleep 120
done
log "JITTER phase complete"
while ! grep -q "CHUNKS_PHASE_COMPLETE" /tmp/audit/chunks_056.log 2>/dev/null; do
  sleep 60
done
log "CHUNKS phase complete"
touch /tmp/audit/NIGHT_COMPLETE
log "NIGHT_COMPLETE"
