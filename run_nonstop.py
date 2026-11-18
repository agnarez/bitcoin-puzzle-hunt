#!/usr/bin/env python3
"""Non-stop runner for Bitcoin Puzzle #140 — Kangaroo centre-out, front-50%.

Loops run_hunt.py in chunks so progress is recorded after every chunk
and the hunt survives restarts. Kangaroo now resumes from its checkpoint
(see solver/kangaroo.py load_checkpoint), so each chunk continues the
same walks instead of restarting them.

HARD RULE: this runner never prints, logs, or copies a private key.
run_hunt.py prints only "FOUND puzzle #N" on a find and writes the key
only to private/FOUND-PRIVATE.txt. This runner checks for that file and
for "FOUND" in stdout, stops immediately, and does NOT restart that
puzzle. The public site / daily job may only announce
"SOLVED — puzzle #, date, ops searched" with no key.

Usage:
  python3 run_nonstop.py [--puzzle 140] [--method kangaroo-centre-out]
                         [--chunk-ops 200000] [--dp-bits 12]
Stop: touch ~/workspace/bitcoin-puzzle-hunt/STOP
"""
import argparse
import json
import os
import subprocess
import sys
import time

HUNT_ROOT = os.path.dirname(os.path.abspath(__file__))
SOLVER_DIR = os.path.join(HUNT_ROOT, "solver")
PROGRESS_FILE = os.path.join(HUNT_ROOT, "data", "progress.json")
PRIVATE_FILE = os.path.join(HUNT_ROOT, "private", "FOUND-PRIVATE.txt")
STOP_FILE = os.path.join(HUNT_ROOT, "STOP")
LOG_FILE = os.path.join(HUNT_ROOT, "logs", "nonstop-140.log")
HEARTBEAT_FILE = os.path.join(HUNT_ROOT, "logs", "nonstop-heartbeat.json")
PID_FILE = os.path.join(HUNT_ROOT, "logs", "run_nonstop.pid")


def log(msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def read_ops(puzzle):
    try:
        with open(PROGRESS_FILE) as f:
            prog = json.load(f)
        return int(prog["puzzles"][str(puzzle)].get("ops_searched", 0))
    except Exception:
        return 0


def write_heartbeat(puzzle, status, ops):
    try:
        with open(HEARTBEAT_FILE, "w") as f:
            json.dump({"puzzle": puzzle, "status": status, "ops_searched": ops,
                       "pid": os.getpid(),
                       "last_heartbeat": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--puzzle", type=int, default=140, choices=[140, 145, 150, 155, 160])
    ap.add_argument("--method", default="kangaroo-centre-out")
    ap.add_argument("--chunk-ops", type=int, default=200000)
    ap.add_argument("--dp-bits", type=int, default=12)
    args = ap.parse_args()

    os.makedirs(os.path.join(HUNT_ROOT, "logs"), exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    log(f"non-stop runner starting puzzle=#{args.puzzle} method={args.method} chunk_ops={args.chunk_ops} dp_bits={args.dp_bits} pid={os.getpid()}")
    log("HARD RULE: on FOUND, stop immediately, key only to agnarez privately in main chat, never on public site.")
    write_heartbeat(args.puzzle, "running", read_ops(args.puzzle))

    chunk = 0
    while True:
        if os.path.exists(STOP_FILE):
            log("STOP file present, stopping cleanly.")
            write_heartbeat(args.puzzle, "stopped", read_ops(args.puzzle))
            return 0
        if os.path.exists(PRIVATE_FILE):
            log(f"FOUND file exists, puzzle #{args.puzzle} already solved — stopping, will NOT restart.")
            write_heartbeat(args.puzzle, "solved", read_ops(args.puzzle))
            return 0

        chunk += 1
        ops_before = read_ops(args.puzzle)
        t0 = time.time()
        try:
            proc = subprocess.run(
                [sys.executable, os.path.join(SOLVER_DIR, "run_hunt.py"),
                 "--puzzle", str(args.puzzle), "--method", args.method,
                 "--window", "front50", "--dp-bits", str(args.dp_bits),
                 "--max-ops", str(args.chunk_ops)],
                cwd=SOLVER_DIR, capture_output=True, text=True, timeout=3600)
            out = (proc.stdout or "").strip()
            err = (proc.stderr or "").strip()
        except subprocess.TimeoutExpired:
            log(f"chunk {chunk}: TIMEOUT after 3600s, continuing (checkpoint saved)")
            write_heartbeat(args.puzzle, "running", read_ops(args.puzzle))
            time.sleep(5)
            continue
        except Exception as e:
            log(f"chunk {chunk}: ERROR {e}, sleeping 10s before retry")
            time.sleep(10)
            continue

        ops_after = read_ops(args.puzzle)
        elapsed = time.time() - t0
        # Never log stdout verbatim beyond the FOUND / not-found line — it
        # contains no key by design, but keep the log to counts only.
        if "FOUND puzzle" in out or os.path.exists(PRIVATE_FILE):
            log(f"chunk {chunk}: FOUND puzzle #{args.puzzle} after {ops_after} total ops — STOPPING, key is private only.")
            write_heartbeat(args.puzzle, "solved", ops_after)
            return 0
        rate = (ops_after - ops_before) / elapsed if elapsed > 0 else 0
        log(f"chunk {chunk}: not found, ops {ops_before}->{ops_after} (+{ops_after - ops_before}) elapsed={elapsed:.0f}s rate={rate:.0f} ops/s")
        if err:
            # Keep only the last line of stderr, counts only.
            log(f"chunk {chunk}: stderr: {err.splitlines()[-1][:200] if err.splitlines() else ''}")
        write_heartbeat(args.puzzle, "running", ops_after)
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
