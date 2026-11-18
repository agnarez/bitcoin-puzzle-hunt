#!/usr/bin/env python3
"""Second free worker for the #140 hunt — fast sequential checker.

Runs the compiled C scanner in slices over the FRONT HALF of puzzle
#140's range, starting at the very beginning of that half and moving
forward one slice at a time. This is the part of the range the main
search does not cover key-by-key, so the two workers never check the
same keys twice.

This worker NEVER touches the main hunt's progress file
(data/progress.json) or its checkpoint. It keeps its own progress file
(data/progress-140-cscan.json), its own log and its own heartbeat, so
its count can never be mixed into — or double-counted with — the main
audited total. The daily audit reads this file separately.

HARD RULE: on a find, the C scanner prints only "FOUND" and writes the
key only to private/FOUND-PRIVATE.txt. This wrapper checks for that
file and for "FOUND" in the output, stops immediately, and never logs
or copies a key.

Stop: touch ~/workspace/bitcoin-puzzle-hunt/STOP
"""
import fcntl
import json
import os
import subprocess
import sys
import time

HUNT_ROOT = os.path.dirname(os.path.abspath(__file__))
SOLVER_DIR = os.path.join(HUNT_ROOT, "solver")
C_SCAN = os.path.join(SOLVER_DIR, "c_scan")
PROGRESS_FILE = os.path.join(HUNT_ROOT, "data", "progress-140-cscan.json")
PRIVATE_FILE = os.path.join(HUNT_ROOT, "private", "FOUND-PRIVATE.txt")
STOP_FILE = os.path.join(HUNT_ROOT, "STOP")
LOG_FILE = os.path.join(HUNT_ROOT, "logs", "cscan-140.log")
HEARTBEAT_FILE = os.path.join(HUNT_ROOT, "logs", "cscan-heartbeat.json")
PID_FILE = os.path.join(HUNT_ROOT, "logs", "run_cscan.pid")
LOCK_FILE = os.path.join(HUNT_ROOT, "logs", "cscan.lock")

PUBKEY = "031f6a332d3c5c4f2de2378c012f429cd109ba07d69690c6c701b6bb87860d6640"
WINDOW_START = "80000000000000000000000000000000000"
WINDOW_END = "bffffffffffffffffffffffffffffffffff"
SLICE_KEYS = 5_000_000


def log(msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state():
    with open(PROGRESS_FILE) as f:
        return json.load(f)


def save_state(st):
    st["last_updated"] = time.strftime("%Y-%m-%d")
    tmp = PROGRESS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, PROGRESS_FILE)


def write_heartbeat(status, st):
    try:
        with open(HEARTBEAT_FILE, "w") as f:
            json.dump({"worker": "c-scan", "puzzle": 140, "status": status,
                       "keys_checked": int(st.get("keys_checked_total", 0)),
                       "pid": os.getpid(),
                       "last_heartbeat": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
    except Exception:
        pass


def main():
    os.makedirs(os.path.join(HUNT_ROOT, "logs"), exist_ok=True)
    os.makedirs(os.path.join(HUNT_ROOT, "data"), exist_ok=True)

    # Single-instance lock: a second wrapper must never run alongside
    # this one, or two wrappers could scan (and count) the same slice.
    lock_f = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("c-scan wrapper already running, exiting")
        return 0
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    try:
        st = load_state()
    except Exception:
        st = {"worker": "c-scan", "puzzle": 140, "status": "running",
              "keys_checked_total": 0, "slices_completed": 0,
              "next_start_hex": WINDOW_START,
              "window_start_hex": WINDOW_START, "window_end_hex": WINDOW_END}

    log(f"c-scan worker starting pid={os.getpid()} next={st['next_start_hex']} total={st['keys_checked_total']}")
    write_heartbeat("running", st)

    while True:
        if os.path.exists(STOP_FILE):
            log("STOP file present, stopping cleanly.")
            write_heartbeat("stopped", st)
            return 0
        if os.path.exists(PRIVATE_FILE):
            log("FOUND file exists, puzzle already solved — stopping, will NOT restart.")
            write_heartbeat("solved", st)
            return 0
        nxt = int(st["next_start_hex"], 16)
        end = int(WINDOW_END, 16)
        if nxt > end:
            log("front-half window fully scanned sequentially — stopping.")
            write_heartbeat("done", st)
            return 0

        t0 = time.time()
        try:
            proc = subprocess.run(
                [C_SCAN, "--pubkey", PUBKEY, "--start", format(nxt, "x"),
                 "--end", WINDOW_END, "--mode", "forward",
                 "--max-keys", str(SLICE_KEYS),
                 "--private-out", PRIVATE_FILE,
                 "--checkpoint-every", "1000000"],
                cwd=SOLVER_DIR, capture_output=True, text=True, timeout=600)
            out = (proc.stdout or "").strip()
        except subprocess.TimeoutExpired:
            log("slice TIMEOUT after 600s, retrying (no progress recorded)")
            time.sleep(5)
            continue
        except Exception as e:
            log(f"slice ERROR {e}, sleeping 10s before retry")
            time.sleep(10)
            continue

        if "FOUND" in out or os.path.exists(PRIVATE_FILE):
            log("FOUND puzzle #140 — STOPPING, key is private only.")
            write_heartbeat("solved", st)
            return 0
        # Parse "not found: checked=N elapsed=... rate=... keys/s"
        checked = 0
        try:
            for token in out.replace(",", " ").split():
                if token.startswith("checked="):
                    checked = int(token.split("=", 1)[1])
        except Exception:
            checked = 0
        if checked <= 0:
            log(f"slice unparseable output {out[:200]!r}, sleeping 10s before retry")
            time.sleep(10)
            continue
        elapsed = time.time() - t0
        st["keys_checked_total"] = int(st.get("keys_checked_total", 0)) + checked
        st["slices_completed"] = int(st.get("slices_completed", 0)) + 1
        st["next_start_hex"] = format(nxt + checked, "x")
        save_state(st)
        rate = checked / elapsed if elapsed > 0 else 0
        log(f"slice {st['slices_completed']}: checked={checked} total={st['keys_checked_total']} "
            f"next={st['next_start_hex'][:12]}... elapsed={elapsed:.0f}s rate={rate:.0f} keys/s")
        write_heartbeat("running", st)
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
