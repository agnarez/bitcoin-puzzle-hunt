"""Smoke test — synthetic 28-bit interval, known key.

Picks a KNOWN synthetic private key in [2^27, 2^28), computes its pubkey,
and confirms kangaroo.py, bsgs.py, and reversed_scan.py each find it.
Also runs run_hunt.py bounded (1,000 ops on real puzzle #140) and checks
data/progress.json updates without leaking any key.

The key below is SYNTHETIC — it is NOT a Bitcoin Puzzle key and unlocks
nothing. It exists only so the engines can be verified end-to-end.
Never use a real puzzle key in a test.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HUNT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from secp256k1 import priv_to_pubkey_compressed  # noqa: E402

LOW = 1 << 27
HIGH = (1 << 28) - 1
CENTRE = LOW + (HIGH - LOW + 1) // 4  # 0x0A000000
TEST_KEY = CENTRE + 0x123  # 0x0A000123, 291 keys above the centre


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
    return ok


def main():
    pubkey = priv_to_pubkey_compressed(TEST_KEY)
    print(f"synthetic test interval: [{LOW:#x}, {HIGH:#x}]")
    print(f"synthetic test key offset from centre: +0x123 (291 keys)")
    print(f"synthetic test pubkey: {pubkey}")
    results = []

    # --- Kangaroo, forward ---
    from kangaroo import solve_interval as kangaroo_solve
    t0 = time.time()
    k, ops, _ = kangaroo_solve(pubkey, LOW, HIGH, method="forward",
                               max_ops=500_000, dp_bits=0)
    secs = time.time() - t0
    results.append(check("kangaroo forward finds synthetic key", k == TEST_KEY,
                         f"ops={ops} {secs:.1f}s {ops / secs:.0f} ops/s" if secs else ""))

    # --- Kangaroo, reversed ---
    t0 = time.time()
    k, ops, _ = kangaroo_solve(pubkey, LOW, HIGH, method="reversed",
                               max_ops=500_000, dp_bits=0)
    secs = time.time() - t0
    results.append(check("kangaroo reversed finds synthetic key", k == TEST_KEY,
                         f"ops={ops} {secs:.1f}s {ops / secs:.0f} ops/s" if secs else ""))

    # --- Kangaroo, centre-out (same interval; anchor is its centre) ---
    t0 = time.time()
    k, ops, _ = kangaroo_solve(pubkey, LOW, HIGH, method="centre-out",
                               max_ops=500_000, dp_bits=0)
    secs = time.time() - t0
    results.append(check("kangaroo centre-out finds synthetic key", k == TEST_KEY,
                         f"ops={ops} {secs:.1f}s" if secs else ""))

    # --- BSGS, forward + reversed ---
    from bsgs import solve_interval as bsgs_solve
    t0 = time.time()
    k, ops = bsgs_solve(pubkey, LOW, HIGH, method="forward")
    secs = time.time() - t0
    results.append(check("bsgs forward finds synthetic key", k == TEST_KEY,
                         f"ops={ops} {secs:.1f}s {ops / secs:.0f} ops/s" if secs else ""))
    t0 = time.time()
    k, ops = bsgs_solve(pubkey, LOW, HIGH, method="reversed")
    secs = time.time() - t0
    results.append(check("bsgs reversed finds synthetic key", k == TEST_KEY,
                         f"ops={ops} {secs:.1f}s" if secs else ""))

    # --- BSGS refuses a huge interval ---
    try:
        bsgs_solve("031f6a332d3c5c4f2de2378c012f429cd109ba07d69690c6c701b6bb87860d6640",
                   1 << 139, (1 << 140) - 1, method="forward")
        results.append(check("bsgs refuses full #140 interval", False))
    except ValueError:
        results.append(check("bsgs refuses full #140 interval", True))

    # --- Sequential scan, centre-out (key is 291 above centre) ---
    from reversed_scan import Scanner
    t0 = time.time()
    sc = Scanner(pubkey, LOW, HIGH, mode="centre-out", centre=CENTRE,
                 max_keys=10_000)
    k, checked, _ = sc.scan()
    secs = time.time() - t0
    results.append(check("scan centre-out finds synthetic key", k == TEST_KEY,
                         f"checked={checked} {secs:.1f}s {checked / secs:.0f} keys/s" if secs else ""))

    # --- Sequential scan, reversed, on a narrow interval (key near the top) ---
    sub_lo, sub_hi = TEST_KEY - 100, TEST_KEY + 4000
    t0 = time.time()
    sc = Scanner(pubkey, sub_lo, sub_hi, mode="reversed",
                 max_keys=10_000)
    k, checked, _ = sc.scan()
    secs = time.time() - t0
    results.append(check("scan reversed finds synthetic key (narrow interval)", k == TEST_KEY,
                         f"checked={checked} {secs:.1f}s" if secs else ""))

    # --- Sequential scan, midpoint variant ---
    t0 = time.time()
    sc = Scanner(pubkey, LOW, HIGH, mode="midpoint", centre=CENTRE,
                 max_keys=10_000)
    k, checked, _ = sc.scan()
    secs = time.time() - t0
    results.append(check("scan midpoint finds synthetic key", k == TEST_KEY,
                         f"checked={checked} {secs:.1f}s" if secs else ""))

    # --- run_hunt.py bounded on real puzzle #140 (will NOT find; must update progress) ---
    before = json.load(open(os.path.join(HUNT_ROOT, "data", "progress.json")))
    before_ops = before["puzzles"]["140"]["ops_searched"]
    r = subprocess.run([sys.executable, "run_hunt.py", "--puzzle", "140",
                        "--method", "scan-centre-out", "--max-ops", "1000"],
                       cwd=os.path.dirname(os.path.abspath(__file__)),
                       capture_output=True, text=True, timeout=600)
    after = json.load(open(os.path.join(HUNT_ROOT, "data", "progress.json")))
    after_ops = after["puzzles"]["140"]["ops_searched"]
    results.append(check("run_hunt bounded run updates progress.json",
                         after_ops == before_ops + 1000,
                         f"ops {before_ops} -> {after_ops}; stdout={r.stdout.strip()[:120]}"))
    results.append(check("run_hunt bounded run reports not found (exit 1)",
                         r.returncode == 1, f"exit={r.returncode}"))

    # --- No key leak: synthetic test key hex must not appear in progress.json or logs ---
    key_hex = format(TEST_KEY, "064x")
    leaked = []
    for root, _dirs, files in os.walk(HUNT_ROOT):
        if "private" in root:
            continue
        for fn in files:
            if fn.endswith((".json", ".log", ".txt", ".md")) and "generated" not in root:
                path = os.path.join(root, fn)
                try:
                    if key_hex in open(path, errors="ignore").read():
                        leaked.append(path)
                except Exception:
                    pass
    results.append(check("no synthetic key in progress/logs (leak check)",
                         not leaked, f"leaked in: {leaked}" if leaked else ""))
    private_file = os.path.join(HUNT_ROOT, "private", "FOUND-PRIVATE.txt")
    results.append(check("no FOUND-PRIVATE.txt created by smoke test",
                         not os.path.exists(private_file)))

    print(f"\n{sum(results)}/{len(results)} smoke checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
