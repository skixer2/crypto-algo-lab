#!/bin/bash
# Startup script for trading bots
# Only starts bots if they're not already running (idempotent watchdog)

BOTS="/home/node/.openclaw/workspace/crypto"
LOG_DIR="$BOTS/logs"
mkdir -p "$LOG_DIR"

start_bot() {
    local name="$1"
    local script_full="$2"
    local logfile="$LOG_DIR/$3"
    local pidfile="/tmp/$3.pid"
    local script_basename=$(basename "$script_full")

    # 1) Check PID file first (fast and stale-safe via kill -0)
    if [ -f "$pidfile" ]; then
        local saved_pid=$(cat "$pidfile" 2>/dev/null)
        if [ -n "$saved_pid" ] && kill -0 "$saved_pid" 2>/dev/null; then
            echo "$name: already running (PID $saved_pid, from pidfile)"
            return 0
        else
            echo "$name: stale pidfile (PID $saved_pid), cleaning up"
            rm -f "$pidfile"
        fi
    fi

    # 2) Fallback: pgrep the script name, filter only python processes
    local running=$(pgrep -f "python.*$script_basename" 2>/dev/null)
    if [ -n "$running" ]; then
        for pid in $running; do
            if kill -0 "$pid" 2>/dev/null; then
                echo "$name: already running (PID $pid, from pgrep)"
                echo "$pid" > "$pidfile"
                return 0
            fi
        done
    fi

    # 3) Not running — start it
    echo "Starting $name..."
    nohup python3 -u "$script_full" >> "$logfile" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$pidfile"
    echo "$name started with PID $new_pid"

    # Verify it actually started
    sleep 2
    if ! kill -0 "$new_pid" 2>/dev/null; then
        echo "ERROR: $name failed to start (PID $new_pid died immediately)"
        rm -f "$pidfile"
        return 1
    fi
}

# Start OKX RSI Scalper Pro v3 (futures, bidirectional, 15m) — rebuilt 2026-09-14 from v2 spec
start_bot "OKX RSI Scalper Pro" "$BOTS/live_rsi_scalper_okx.py" "live_rsi_scalper_okx.log"

# Start Revolut RSI v2 (recovered as compiled bytecode 2026-09-14; source lost)
start_bot "Revolut RSI v2 trend-filtered" "$BOTS/live_trading_revolut_v2.pyc" "live_trading_revolut_v2.log"

echo "All bots checked."
