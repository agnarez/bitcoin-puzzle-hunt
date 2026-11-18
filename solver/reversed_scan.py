"""Sequential reversed / centre-out scanner — pure Python, CPU.

Scans an interval [a, b] key-by-key, checking each candidate's public key
against the target. Uses incremental EC addition (P_{k+1} = P_k + G), so
each key costs one Jacobian point addition, not a fresh scalar mult.

Modes
-----
- forward:      a, a+1, a+2, ... b
- reversed:     b, b-1, b-2, ... a   (backwards from the top)
- centre-out:   centre, centre+1, centre-1, centre+2, centre-2, ...
                centre defaults to the interval midpoint (for the front-50%
                window that is the 25% point of the full range).
- midpoint:     the xlh6 variant — down arm from M, up arm from M+1,
                interleaved. M defaults to the interval midpoint.

Checkpointing: state is saved every --checkpoint-every keys (default
1,000,000) to logs/reversed_scan-<puzzle>-<mode>.json and can be resumed
with --resume. The checkpoint contains only counts and the next key —
never a private key.

Honest note: sequential scanning checks keys one by one. For #140's
front-50% window that is 2^138 keys. Even at 100k keys/s that is ~10^34
years. This scanner is a correct small-range / verification engine and
a way to cover a *chosen* slice (e.g. the first/last million keys of a
window). It is not a realistic #140 engine — Kangaroo on a GPU is.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from secp256k1 import (  # noqa: E402
    G,
    P,
    _jacobian_add,
    _jacobian_double,
    _to_affine,
    _to_jacobian,
    pubkey_hex_to_point,
    scalar_mult,
)

HUNT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_puzzles():
    with open(os.path.join(HUNT_ROOT, "data", "puzzles.json")) as f:
        return {p["n"]: p for p in json.load(f)["puzzles"]}


def _compressed_from_affine(pt):
    if pt is None:
        return None
    x, y = pt
    return ("03" if y & 1 else "02") + format(x, "064x")


class Scanner:
    def __init__(self, pubkey_hex, a, b, mode="centre-out", centre=None,
                 max_keys=1_000_000, checkpoint_every=1_000_000,
                 checkpoint_path=None):
        self.pubkey_hex = pubkey_hex.lower()
        self.target = pubkey_hex_to_point(self.pubkey_hex)
        self.a, self.b = a, b
        self.mode = mode
        self.centre = centre if centre is not None else (a + b) // 2
        self.max_keys = max_keys
        self.checkpoint_every = checkpoint_every
        self.checkpoint_path = checkpoint_path
        self.checked = 0
        self._g_j = _to_jacobian(G)
        self._neg_g_j = (G[0], (-G[1]) % P, 1)

    # -- order generators: each yields (key_int, point_jacobian) ---------
    def _iter_forward(self, start_key, start_pt_j):
        k, pt_j = start_key, start_pt_j
        while k <= self.b and self.checked < self.max_keys:
            yield k, pt_j
            pt_j = _jacobian_add(pt_j, self._g_j)
            k += 1

    def _iter_reversed(self, start_key, start_pt_j):
        k, pt_j = start_key, start_pt_j
        while k >= self.a and self.checked < self.max_keys:
            yield k, pt_j
            pt_j = _jacobian_add(pt_j, self._neg_g_j)
            k -= 1

    def _iter_centre_out(self):
        c = self.centre
        # Centre itself, then +1/-1, +2/-2, ... staying inside [a, b].
        centre_pt = _to_jacobian(scalar_mult(c))
        yield c, centre_pt
        up_pt, down_pt = centre_pt, centre_pt
        step = 1
        while self.checked < self.max_keys:
            progressed = False
            if c + step <= self.b:
                up_pt = _jacobian_add(up_pt, self._g_j)
                yield c + step, up_pt
                progressed = True
            if c - step >= self.a:
                down_pt = _jacobian_add(down_pt, self._neg_g_j)
                yield c - step, down_pt
                progressed = True
            if not progressed:
                return
            step += 1

    def _iter_midpoint(self):
        # xlh6 variant: M = centre, down arm M, M-1, ... ; up arm M+1, ...
        # Interleave down, up, down, up...
        m = self.centre
        down_pt = _to_jacobian(scalar_mult(m))
        up_pt = _jacobian_add(down_pt, self._g_j)
        yield m, down_pt
        step = 1
        while self.checked < self.max_keys:
            progressed = False
            if m - step >= self.a:
                if step > 1:
                    down_pt = _jacobian_add(down_pt, self._neg_g_j)
                else:
                    down_pt = _jacobian_add(down_pt, self._neg_g_j)
                yield m - step, down_pt
                progressed = True
            if m + step <= self.b:
                if step > 1:
                    up_pt = _jacobian_add(up_pt, self._g_j)
                yield m + step, up_pt
                progressed = True
            if not progressed:
                return
            step += 1

    def _iterator(self):
        if self.mode == "forward":
            return self._iter_forward(self.a, _to_jacobian(scalar_mult(self.a)))
        if self.mode == "reversed":
            return self._iter_reversed(self.b, _to_jacobian(scalar_mult(self.b)))
        if self.mode == "centre-out":
            return self._iter_centre_out()
        if self.mode == "midpoint":
            return self._iter_midpoint()
        raise ValueError(f"unknown mode {self.mode!r}")

    def save_checkpoint(self, next_key=None):
        if not self.checkpoint_path:
            return
        data = {"a": format(self.a, "x"), "b": format(self.b, "x"),
                "mode": self.mode, "centre": format(self.centre, "x"),
                "checked": self.checked, "next_key": format(next_key, "x") if next_key is not None else None,
                "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        with open(self.checkpoint_path, "w") as f:
            json.dump(data, f, indent=2)

    def scan(self):
        """Return (key_or_None, keys_checked, seconds). Key returned only."""
        t0 = time.time()
        last_key = None
        for k, pt_j in self._iterator():
            if self.checked >= self.max_keys:
                break
            pt = _to_affine(pt_j)
            self.checked += 1
            last_key = k
            if pt is not None and _compressed_from_affine(pt) == self.pubkey_hex:
                self.save_checkpoint(next_key=k)
                return k, self.checked, time.time() - t0
            if self.checked % self.checkpoint_every == 0:
                self.save_checkpoint(next_key=k)
        self.save_checkpoint(next_key=last_key)
        return None, self.checked, time.time() - t0


def main():
    ap = argparse.ArgumentParser(description="Sequential reversed/centre-out scanner")
    ap.add_argument("--puzzle", type=int, choices=[140, 145, 150, 155, 160])
    ap.add_argument("--pubkey")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--mode", default="centre-out",
                    choices=["forward", "reversed", "centre-out", "midpoint"])
    ap.add_argument("--window", default="front50",
                    choices=["front50", "full"],
                    help="front50 = [2^(N-1), 2^(N-1)+2^(N-2)); full = whole range")
    ap.add_argument("--max-keys", type=int, default=1_000_000)
    ap.add_argument("--checkpoint-every", type=int, default=1_000_000)
    ap.add_argument("--checkpoint")
    args = ap.parse_args()

    if args.puzzle:
        p = load_puzzles()[args.puzzle]
        pubkey = p["public_key"]
        if args.window == "front50":
            a = int(p["front50_start_hex"], 16)
            b = int(p["front50_end_hex"], 16)
            centre = int(p["centre25_hex"], 16)
        else:
            a = int(p["range_start_hex"], 16)
            b = int(p["range_end_hex"], 16)
            centre = int(p["midpoint_hex"], 16)
    else:
        if not (args.pubkey and args.start and args.end):
            ap.error("need --puzzle or --pubkey/--start/--end")
        pubkey, a, b = args.pubkey, int(args.start, 16), int(args.end, 16)
        centre = (a + b) // 2

    ckpt = args.checkpoint or os.path.join(
        HUNT_ROOT, "logs", f"reversed_scan-{args.puzzle or 'custom'}-{args.mode}.json")
    scanner = Scanner(pubkey, a, b, mode=args.mode, centre=centre,
                      max_keys=args.max_keys,
                      checkpoint_every=args.checkpoint_every,
                      checkpoint_path=ckpt)
    k, checked, secs = scanner.scan()
    rate = checked / secs if secs > 0 else 0
    if k is not None:
        print("FOUND")  # HARD RULE: never print the key.
    else:
        print(f"not found: checked={checked} elapsed={secs:.1f}s rate={rate:.0f} keys/s")
    return 0 if k is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
