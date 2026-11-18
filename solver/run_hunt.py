"""run_hunt.py — CLI orchestrator for the Bitcoin Puzzle hunt.

Usage:
  python3 run_hunt.py --puzzle 140 --method kangaroo-centre-out --max-ops 1000000
  python3 run_hunt.py --puzzle 140 --method scan-centre-out --max-ops 1000000
  python3 run_hunt.py --puzzle 140 --method bsgs-reversed --max-ops 100000

Methods:
  kangaroo-forward | kangaroo-reversed | kangaroo-centre-out
  scan-forward | scan-reversed | scan-centre-out | scan-midpoint
  bsgs-forward | bsgs-reversed   (small subranges only; full puzzles refused)

Interval: kangaroo-centre-out and all scan-* modes use the FRONT-50%
window [2^(N-1), 2^(N-1)+2^(N-2)); kangaroo-forward/reversed and BSGS
use the full range unless --window front50 is given.

HARD RULE — READ THIS BEFORE RUNNING:
  * If a key is found, this script prints ONLY "FOUND puzzle #N" to stdout.
  * The key is written ONLY to private/FOUND-PRIVATE.txt (hex + WIF),
    a file that must NEVER be included in any website build, log, or
    shared output.
  * data/progress.json records only status=solved, date, and ops searched.
  * No log file, checkpoint, or progress file ever contains a key.
  * After a find, claim via a private/direct-to-miner submission
    (e.g. MARA Slipstream) — never broadcast a spend to the public
    mempool first. See docs/METHOD.md § Risks.
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HUNT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRIVATE_FILE = os.path.join(HUNT_ROOT, "private", "FOUND-PRIVATE.txt")
PROGRESS_FILE = os.path.join(HUNT_ROOT, "data", "progress.json")


def load_puzzles():
    with open(os.path.join(HUNT_ROOT, "data", "puzzles.json")) as f:
        return {p["n"]: p for p in json.load(f)["puzzles"]}


def load_progress():
    with open(PROGRESS_FILE) as f:
        return json.load(f)


def save_progress(prog):
    prog["last_updated"] = time.strftime("%Y-%m-%d")
    with open(PROGRESS_FILE, "w") as f:
        json.dump(prog, f, indent=2)


def reconcile_kangaroo_progress(entry, checkpoint_path):
    """Pull kangaroo progress up to the checkpoint value (one-way).

    The Kangaroo checkpoint is saved ~every 100k ops mid-chunk, but
    progress.json was only credited when a full 200k chunk completed, so
    a VM replacement mid-chunk stranded up to 100k of checkpointed work
    per restart (cumulative gap, ~17.8M by 2026-11-17). After each
    completed chunk, set kangaroo_ops to the checkpoint value when it is
    ahead, so stranded work is credited and the checkpoint/progress gap
    stays within one mid-chunk save (0-100k) instead of growing without
    bound. Never moves progress backwards; if the checkpoint is missing
    or unreadable, keep the chunk-credited value. Returns the checkpoint
    ops used, or None.
    """
    if not checkpoint_path:
        return None
    try:
        # The checkpoint file is large (tens of MB of DPs); the top-level
        # "ops" field sits in the first bytes, so read only the head.
        with open(checkpoint_path) as f:
            head = f.read(4096)
        m = re.search(r'"ops":\s*(\d+)', head)
        if not m:
            return None
        ckpt_ops = int(m.group(1))
    except Exception:
        return None
    if ckpt_ops < 0:
        return None
    if ckpt_ops > entry.get("kangaroo_ops", 0):
        entry["kangaroo_ops"] = ckpt_ops
        entry["ops_searched"] = ckpt_ops + entry.get("sequential_keys_checked", 0)
    return ckpt_ops


def _wif(priv):
    """Private key (int) -> WIF compressed. Key material — private file only."""
    import hashlib
    payload = b"\x80" + priv.to_bytes(32, "big") + b"\x01"
    chk = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    n = int.from_bytes(payload + chk, "big")
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = alphabet[r] + s
    return "1" * (len(payload + chk) - len((payload + chk).lstrip(b"\x00"))) + s


def handle_found(puzzle_n, key, ops):
    """HARD RULE implementation. Prints ONLY 'FOUND puzzle #N' to stdout."""
    os.makedirs(os.path.dirname(PRIVATE_FILE), exist_ok=True)
    with open(PRIVATE_FILE, "w") as f:
        f.write("PRIVATE — DO NOT SHARE, DO NOT PUBLISH, DO NOT PUT ON ANY WEBSITE\n")
        f.write(f"puzzle: {puzzle_n}\n")
        f.write(f"date_found: {time.strftime('%Y-%m-%d')}\n")
        f.write(f"ops_searched: {ops}\n")
        f.write(f"private_key_hex: {key:064x}\n")
        f.write(f"private_key_wif_compressed: {_wif(key)}\n")
    # Progress file: solved announcement only — no key.
    prog = load_progress()
    entry = prog["puzzles"][str(puzzle_n)]
    entry["status"] = "solved"
    # ops were already added by the caller before handle_found(); do not
    # add them a second time here.
    entry["last_run"] = time.strftime("%Y-%m-%d")
    save_progress(prog)
    print(f"FOUND puzzle #{puzzle_n}")


def main():
    ap = argparse.ArgumentParser(description="Bitcoin Puzzle hunt orchestrator")
    ap.add_argument("--puzzle", type=int, required=True,
                    choices=[140, 145, 150, 155, 160])
    ap.add_argument("--method", default="kangaroo-centre-out",
                    choices=["kangaroo-forward", "kangaroo-reversed",
                             "kangaroo-centre-out", "scan-forward",
                             "scan-reversed", "scan-centre-out", "scan-midpoint",
                             "bsgs-forward", "bsgs-reversed"])
    ap.add_argument("--window", default="front50",
                    choices=["front50", "full"],
                    help="front50 is the default scope for this hunt")
    ap.add_argument("--max-ops", type=int, default=1_000_000)
    ap.add_argument("--dp-bits", type=int, default=0)
    args = ap.parse_args()

    puzzles = load_puzzles()
    p = puzzles[args.puzzle]
    pubkey = p["public_key"]

    engine, _, mode = args.method.partition("-")
    if args.window == "front50":
        a = int(p["front50_start_hex"], 16)
        b = int(p["front50_end_hex"], 16)
        centre = int(p["centre25_hex"], 16)
    else:
        a = int(p["range_start_hex"], 16)
        b = int(p["range_end_hex"], 16)
        centre = int(p["midpoint_hex"], 16)

    t0 = time.time()
    key, ops = None, 0
    ckpt_path = None
    if engine == "kangaroo":
        from kangaroo import solve_interval
        # centre-out uses the front-50% interval; its tame anchor is the centre.
        ckpt_path = os.path.join(HUNT_ROOT, "logs",
                                 f"kangaroo-{args.puzzle}-{mode}.json")
        key, ops, _secs = solve_interval(
            pubkey, a, b, method=mode, max_ops=args.max_ops,
            dp_bits=args.dp_bits,
            checkpoint_path=ckpt_path)
    elif engine == "scan":
        from reversed_scan import Scanner
        scanner = Scanner(pubkey, a, b, mode=mode, centre=centre,
                          max_keys=args.max_ops,
                          checkpoint_path=os.path.join(
                              HUNT_ROOT, "logs",
                              f"reversed_scan-{args.puzzle}-{mode}.json"))
        key, ops, _secs = scanner.scan()
    elif engine == "bsgs":
        from bsgs import solve_interval
        key, ops = solve_interval(pubkey, a, b, method=mode)
    else:
        ap.error(f"unknown engine {engine}")

    secs = time.time() - t0
    rate = ops / secs if secs > 0 else 0

    prog = load_progress()
    entry = prog["puzzles"][str(args.puzzle)]
    entry["ops_searched"] = entry.get("ops_searched", 0) + ops
    if engine == "kangaroo":
        entry["kangaroo_ops"] = entry.get("kangaroo_ops", 0) + ops
        # Reconcile to the checkpoint after each completed chunk, so work
        # stranded by mid-chunk VM replacements is credited and the gap
        # stops growing. See reconcile_kangaroo_progress().
        reconcile_kangaroo_progress(entry, ckpt_path)
    elif engine == "scan":
        entry["sequential_keys_checked"] = entry.get("sequential_keys_checked", 0) + ops
        # Record the sequential slice actually covered (centre-out covers
        # both sides of the centre; record the bounding box, not a claim
        # of contiguous coverage — see docs/METHOD.md).
        entry.setdefault("ranges_covered", []).append(
            {"window": args.window, "method": args.method,
             "start_hex": format(a, "x"), "end_hex": format(b, "x"),
             "keys_checked": ops, "date": time.strftime("%Y-%m-%d")})
    entry["last_method"] = args.method
    entry["last_run"] = time.strftime("%Y-%m-%d")
    save_progress(prog)

    if key is not None:
        handle_found(args.puzzle, key, ops)
        return 0
    print(f"not found: puzzle=#{args.puzzle} method={args.method} "
          f"window={args.window} ops={ops} elapsed={secs:.1f}s "
          f"rate={rate:.0f} ops/s")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
