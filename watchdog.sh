#!/usr/bin/env bash
# Watchdog for the Bitcoin Puzzle non-stop hunt.
# Uses a PID file (logs/run_nonstop.pid) — pgrep -f is unreliable here
# because tool wrapper shells contain the runner name in their own
# command line and would give false "alive" hits.
# - If FOUND file exists: do NOT restart, log SOLVED and exit 0.
# - If STOP file exists: do NOT restart.
# - If PID file points to a live python3 run_nonstop.py: do nothing.
# - Otherwise: restart it in background, log the restart.
# Never prints, logs, or copies a private key. Checks only file existence
# and process presence, never file contents of private/FOUND-PRIVATE.txt.
set -u
HUNT_ROOT="$HOME/workspace/bitcoin-puzzle-hunt"
LOG="$HUNT_ROOT/logs/watchdog.log"
PID_FILE="$HUNT_ROOT/logs/run_nonstop.pid"
mkdir -p "$HUNT_ROOT/logs"
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
echo "$(ts) watchdog check" >> "$LOG"

if [ -f "$HUNT_ROOT/private/FOUND-PRIVATE.txt" ]; then
  echo "$(ts) SOLVED - FOUND file exists, NOT restarting. Key is private only." >> "$LOG"
  exit 0
fi
if [ -f "$HUNT_ROOT/STOP" ]; then
  echo "$(ts) STOP file present, NOT restarting." >> "$LOG"
  exit 0
fi
# --- Second worker: the separate C-scan checker (own PID file, own
# progress file, never touches the main hunt's progress or checkpoint).
# Checked on every watchdog run, same as the main runner. If it is not
# alive, kill any stray c_scan child, then restart the wrapper. The
# wrapper holds an exclusive lock, so a second wrapper can never run
# alongside it and double-count a slice.
CSCAN_PID_FILE="$HUNT_ROOT/logs/run_cscan.pid"
CSCAN_ALIVE=0
if [ -f "$CSCAN_PID_FILE" ]; then
  CPID=$(cat "$CSCAN_PID_FILE" 2>/dev/null || true)
  if [ -n "${CPID:-}" ] && kill -0 "$CPID" 2>/dev/null; then
    if tr '\0' ' ' < "/proc/$CPID/cmdline" 2>/dev/null | grep -q "run_cscan_nonstop.py"; then
      echo "$(ts) c-scan worker alive pid $CPID, nothing to do." >> "$LOG"
      CSCAN_ALIVE=1
    fi
  fi
fi
if [ "$CSCAN_ALIVE" = "0" ]; then
  echo "$(ts) c-scan worker NOT alive, restarting." >> "$LOG"
  pkill -f "c_scan --pubkey" 2>/dev/null || true
  sleep 1
  cd "$HUNT_ROOT" || exit 1
  nohup python3 "$HUNT_ROOT/run_cscan_nonstop.py" >> "$HUNT_ROOT/logs/cscan-140.log" 2>&1 &
  echo "$(ts) restarted c-scan worker pid $!" >> "$LOG"
fi
if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE" 2>/dev/null || true)
  if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
    if tr '\0' ' ' < "/proc/$PID/cmdline" 2>/dev/null | grep -q "run_nonstop.py"; then
      echo "$(ts) runner alive pid $PID, nothing to do." >> "$LOG"
      exit 0
    fi
  fi
  echo "$(ts) stale PID file pid ${PID:-?}, will restart." >> "$LOG"
fi
echo "$(ts) runner NOT alive, restarting." >> "$LOG"
python3 "$HUNT_ROOT/kill_strays.py" >> "$LOG" 2>&1 || true
cd "$HUNT_ROOT" || exit 1
nohup python3 "$HUNT_ROOT/run_nonstop.py" --puzzle 140 --method kangaroo-centre-out --chunk-ops 200000 --dp-bits 12 >> "$HUNT_ROOT/logs/nonstop-140.log" 2>&1 &
echo "$(ts) restarted runner pid $!" >> "$LOG"
exit 0
