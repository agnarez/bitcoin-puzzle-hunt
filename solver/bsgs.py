"""Baby-step giant-step (BSGS) for a small interval [a, b] — pure Python.

Solves k in [a, b] with k*G == Q. Time Theta(sqrt(b-a)), memory
Theta(sqrt(b-a)) stored points — that is why BSGS is REFUSED for large
intervals (see MAX_BABY_STEPS). For #140, sqrt(width) ~ 2^69.5 table
entries is impossible; BSGS here is a small-range verifier / cross-check,
and the real #140 engine is Kangaroo (constant memory) or a GPU rig.

Reversed mode: solve the mirrored problem Q_rev = (a+b)*G - Q for k_rev,
then k = a + b - k_rev. Same complexity, searches the interval backwards.

HARD RULE: a found key is returned to the caller only, never printed or
logged by this module.
"""
import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from secp256k1 import (  # noqa: E402
    G,
    _jacobian_add,
    _jacobian_double,
    _to_affine,
    _to_jacobian,
    mirror_pubkey,
    pubkey_hex_to_point,
    scalar_mult,
    verify_privkey,
)

HUNT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Refuse baby-step tables larger than this unless explicitly overridden.
# 5,000,000 points is already ~hundreds of MB in CPython dicts.
MAX_BABY_STEPS = 5_000_000


def load_puzzles():
    with open(os.path.join(HUNT_ROOT, "data", "puzzles.json")) as f:
        return {p["n"]: p for p in json.load(f)["puzzles"]}


def bsgs(pubkey_hex, a, b, allow_large_memory=False):
    """Return (key_or_None, ops). ops = baby steps + giant steps performed."""
    from secp256k1 import P as _P, point_add_affine

    width = b - a + 1
    m = math.isqrt(width) + 1
    if m > MAX_BABY_STEPS and not allow_large_memory:
        raise ValueError(
            f"BSGS needs ~{m:,} baby-step points for width {width:,} "
            f"(sqrt). Refusing: that table does not fit in RAM. "
            f"Use Kangaroo instead, or a subrange with width <= "
            f"{MAX_BABY_STEPS ** 2:,}."
        )
    target = pubkey_hex_to_point(pubkey_hex)
    # Baby steps: j*G for j in [0, m). Store affine point -> j.
    # j=0 is the point at infinity; represent it with the key None.
    table = {None: 0}
    cur_j = _to_jacobian(G)  # 1*G
    ops = 0
    for j in range(1, m):
        pt = _to_affine(cur_j)
        table.setdefault(pt, j)
        cur_j = _jacobian_add(cur_j, _to_jacobian(G))
        ops += 1
    # Giant steps: Q - a*G - i*m*G, look up in the baby table.
    aG = scalar_mult(a)
    neg_aG = (aG[0], (-aG[1]) % _P)
    cur = point_add_affine(target, neg_aG)
    mG = scalar_mult(m)
    neg_mG = (mG[0], (-mG[1]) % _P)
    for i in range(m + 1):
        if cur in table:
            j = table[cur]
            k = a + i * m + j
            if a <= k <= b and verify_privkey(k, pubkey_hex):
                return k, ops + i + 1
        if cur is None:
            break
        cur = point_add_affine(cur, neg_mG)
        ops += 1
    return None, ops


def solve_interval(pubkey_hex, a, b, method="forward", allow_large_memory=False):
    """method: forward | reversed. Returns (key_or_None, ops)."""
    if method == "reversed":
        q_rev = mirror_pubkey(pubkey_hex, a, b)
        k_rev, ops = bsgs(q_rev, a, b, allow_large_memory=allow_large_memory)
        if k_rev is None:
            return None, ops
        k = a + b - k_rev
        return (k, ops) if verify_privkey(k, pubkey_hex) else (None, ops)
    return bsgs(pubkey_hex, a, b, allow_large_memory=allow_large_memory)


def main():
    ap = argparse.ArgumentParser(description="BSGS (small intervals only)")
    ap.add_argument("--puzzle", type=int, choices=[140, 145, 150, 155, 160])
    ap.add_argument("--pubkey")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--method", default="forward", choices=["forward", "reversed"])
    ap.add_argument("--allow-large-memory", action="store_true")
    args = ap.parse_args()

    if args.puzzle:
        p = load_puzzles()[args.puzzle]
        pubkey = p["public_key"]
        a = int(p["range_start_hex"], 16)
        b = int(p["range_end_hex"], 16)
        print("NOTE: full puzzle BSGS will be refused (table ~2^70). "
              "Use a small --start/--end subrange for verification.")
    else:
        if not (args.pubkey and args.start and args.end):
            ap.error("need --puzzle or --pubkey/--start/--end")
        pubkey, a, b = args.pubkey, int(args.start, 16), int(args.end, 16)

    t0 = time.time()
    try:
        k, ops = solve_interval(pubkey, a, b, method=args.method,
                                allow_large_memory=args.allow_large_memory)
    except ValueError as e:
        print(f"refused: {e}")
        return 2
    secs = time.time() - t0
    if k is not None:
        print("FOUND")  # HARD RULE: never print the key.
    else:
        print(f"not found: ops={ops} elapsed={secs:.1f}s rate={ops / secs:.0f} ops/s" if secs > 0 else f"not found: ops={ops}")
    return 0 if k is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
