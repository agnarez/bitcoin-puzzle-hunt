"""Pollard's Kangaroo (interval discrete log) — pure Python, CPU.

Solves k in [a, b] (inclusive) with k*G == Q, given Q's compressed pubkey.

Method
------
Tame herd: kangaroos start at known scalars in the interval (default: the
interval end b, and — for centre-out — the centre). Wild herd: kangaroos
start at Q itself (unknown scalar k). Each step adds a jump J[h(P)] where
h is the point's x-coordinate mod len(jumps). When a tame and a wild
kangaroo land on the same point, k = tame_scalar - wild_offset.

Distinguished points (DP): only points with x % 2**dp_bits == 0 are stored.
For small test intervals dp_bits is small (or 0 = store every point).
Checkpointing saves the herds' current points/distances (never a key).

Honest note (see docs/METHOD.md): expected work is Theta(sqrt(b-a)).
Scan order / centre-out / reversed do NOT change that expectation if keys
are uniform — they only change which keys are found early. Reversed mode
solves the mirrored problem Q_rev = (a+b)*G - Q for k_rev, then
k = a + b - k_rev.

This is a correctness-first CPU implementation. For #140 it is a verifier
and a small-range engine only — see README.md for the GPU tools that are
the real engine at 2^69.5 ops.
"""
import argparse
import hashlib
import json
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from secp256k1 import (  # noqa: E402
    G,
    _batch_to_affine,
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


def load_puzzles():
    with open(os.path.join(HUNT_ROOT, "data", "puzzles.json")) as f:
        return {p["n"]: p for p in json.load(f)["puzzles"]}


def make_jumps(width, n_jumps=32):
    """Jump sizes: powers of two from 1 up to ~2*sqrt(width).

    The mean jump is ~sqrt(width)/7 — a bit below the optimal
    ~sqrt(width)/2, which costs a small constant factor, but the table
    MUST include 1 (gcd of the jumps must be 1). Do NOT scale the table
    by a factor s > 1: that makes every jump a multiple of s, which
    partitions the interval into s residue classes mod s. A key in a
    class no tame kangaroo can reach would then be unfindable forever.
    That is exactly what the first smoke test exposed: a scaled table
    (all jumps multiples of 4) let forward find its key (same residue
    as the tame starts, mod 4) while reversed could never find k_rev
    (different residue, mod 4) in 500,000 ops.
    """
    if width <= 1:
        return [1]
    target_mean = max(1, int(math.isqrt(width)) // 2)
    jumps = []
    v = 1
    while len(jumps) < n_jumps and v <= 2 * target_mean:
        jumps.append(v)
        v *= 2
    if not jumps:
        jumps = [1]
    assert math.gcd(*jumps) == 1, "jump table must have gcd 1"
    return jumps


class Kangaroo:
    def __init__(self, pubkey_hex, a, b, dp_bits=0, max_ops=1_000_000,
                 seed=12345, n_tame=2, n_wild=2, checkpoint_path=None):
        self.pubkey_hex = pubkey_hex.lower()
        self.a, self.b = a, b
        self.width = b - a
        self.dp_bits = dp_bits
        self.max_ops = max_ops
        self.checkpoint_path = checkpoint_path
        self.jumps = make_jumps(max(1, self.width))
        self.jump_points_j = [_to_jacobian(scalar_mult(j)) for j in self.jumps]
        self.rng = random.Random(seed)
        self.target_point = pubkey_hex_to_point(self.pubkey_hex)
        self.ops = 0
        # Herds: each kangaroo is [point_jacobian, distance_int, kind,
        # cached_affine]. The cache holds the point's affine form (or
        # None while it still needs converting / for infinity), so a
        # step reuses the affine computed for the previous round's
        # collision check instead of inverting again. See solve().
        self.tame = []
        self.wild = []
        # Distinguished-point store: affine point -> (kind, distance)
        self.dps = {}
        self._init_herds(n_tame, n_wild)

    def _init_herds(self, n_tame, n_wild):
        # Tame starts: interval end, and the centre (centre-out anchor).
        tame_starts = [self.b, (self.a + self.b) // 2]
        for i in range(n_tame):
            s = tame_starts[i % len(tame_starts)]
            pt = scalar_mult(s)  # affine; cache it, no inversion needed
            self.tame.append([_to_jacobian(pt), s, "tame", pt])
        for _ in range(n_wild):
            pt = self.target_point  # already affine; cache it directly
            self.wild.append([_to_jacobian(pt), 0, "wild", pt])

    def _is_dp(self, pt_affine):
        if pt_affine is None:
            return False
        return self.dp_bits == 0 or (pt_affine[0] % (1 << self.dp_bits) == 0)

    def _step(self, roo):
        # Hash uses the CURRENT point's affine x. That affine was already
        # computed for the previous round's collision check and cached in
        # roo[3], so a step costs one Jacobian add and no inversion.
        # (The old code inverted here AND again in _check_collision.)
        pt = roo[3]
        if pt is None:
            if roo[0][2] == 0:
                return None  # point at infinity: cannot step (as before)
            pt = _to_affine(roo[0])
            roo[3] = pt
            if pt is None:
                return None
        h = pt[0] % len(self.jumps)
        roo[0] = _jacobian_add(roo[0], self.jump_points_j[h])
        roo[1] = roo[1] + self.jumps[h]
        roo[3] = None  # affine stale after the jump; solve() re-fills it
        self.ops += 1
        return roo

    def _check_collision(self, roo, pt_affine=None):
        """Check a kangaroo's current point against stored DPs / other herd.

        Returns the recovered private key (int) or None. The key is
        returned to the caller only — never logged here.
        pt_affine is the point's affine form when the caller already has
        it (solve() passes the batch-converted value); otherwise it is
        taken from the roo's cache or computed once.
        """
        if pt_affine is None:
            pt_affine = roo[3]
        if pt_affine is None:
            if roo[0][2] == 0:
                return None
            pt_affine = _to_affine(roo[0])
            roo[3] = pt_affine
            if pt_affine is None:
                return None
        if not self._is_dp(pt_affine):
            return None
        kind, dist = roo[2], roo[1]
        other = self.dps.get(pt_affine)
        if other is not None and other[0] != kind:
            if kind == "wild":
                # tame scalar - wild offset = k
                k = other[1] - dist
            else:
                k = dist - other[1]
            if self.a <= k <= self.b and verify_privkey(k, self.pubkey_hex):
                return k
            return None
        self.dps.setdefault(pt_affine, (kind, dist))
        return None

    def save_checkpoint(self):
        if not self.checkpoint_path:
            return
        def ser(roo):
            pt = _to_affine(roo[0])
            return {"x": format(pt[0], "x") if pt else None,
                    "y": format(pt[1], "x") if pt else None,
                    "dist": str(roo[1]), "kind": roo[2]}
        # Save DPs too when the store is small enough to be useful.
        # With dp_bits=16 the store stays small; with dp_bits=0 every
        # point is a DP and the store is the whole walk, so skip it.
        dps_list = []
        if len(self.dps) <= 200000:
            for (x, y), (kind, dist) in self.dps.items():
                dps_list.append({"x": format(x, "x"), "y": format(y, "x"),
                                 "kind": kind, "dist": str(dist)})
        data = {"a": str(self.a), "b": str(self.b), "ops": self.ops,
                "dp_bits": self.dp_bits, "tame": [ser(r) for r in self.tame],
                "wild": [ser(r) for r in self.wild],
                "dps_stored": len(self.dps), "dps": dps_list}
        tmp = self.checkpoint_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.checkpoint_path)

    def load_checkpoint(self):
        """Resume from a checkpoint saved by save_checkpoint.

        Restores herd positions/distances, ops count, and DPs when they
        were saved. Returns True if a usable checkpoint was loaded.
        Without this, every run_hunt call restarts the same walks from
        scratch — looping would repeat work forever. Never logs a key:
        checkpoints contain points and distances only.
        """
        if not self.checkpoint_path or not os.path.exists(self.checkpoint_path):
            return False
        try:
            with open(self.checkpoint_path) as f:
                data = json.load(f)
        except Exception:
            return False
        if str(data.get("a")) != str(self.a) or str(data.get("b")) != str(self.b):
            return False
        try:
            def unser(d):
                if d.get("x") is None:
                    return None
                pt = (int(d["x"], 16), int(d["y"], 16))
                # Affine is the stored point itself: cache it, no inversion.
                return [_to_jacobian(pt), int(d["dist"]), d["kind"], pt]
            tame = [unser(d) for d in data.get("tame", [])]
            wild = [unser(d) for d in data.get("wild", [])]
            if not tame or not wild or any(r is None for r in tame + wild):
                return False
            self.tame = tame
            self.wild = wild
            self.ops = int(data.get("ops", 0))
            self.dps = {}
            for d in data.get("dps", []):
                try:
                    self.dps[(int(d["x"], 16), int(d["y"], 16))] = (d["kind"], int(d["dist"]))
                except Exception:
                    continue
            return True
        except Exception:
            return False

    def solve(self):
        t0 = time.time()
        # max_ops is per-call (additional ops), so a resumed run does
        # chunk_size more ops on top of the loaded checkpoint, not a
        # total cap that would stop immediately after resume.
        start_ops = self.ops
        target_ops = start_ops + self.max_ops
        herd = self.tame + self.wild
        # Seed DP store with starting points (one inversion for the herd).
        affines = _batch_to_affine([r[0] for r in herd])
        for roo, pt in zip(herd, affines):
            roo[3] = pt
            k = self._check_collision(roo, pt)
            if k is not None:
                return k, self.ops - start_ops, time.time() - t0
        while self.ops < target_ops:
            # Step every roo. Each step reuses its cached affine for the
            # jump hash, so this loop does Jacobian adds only — no
            # inversions at all.
            stepped = []
            for roo in herd:
                self._step(roo)
                stepped.append(roo)
                if self.ops >= target_ops:
                    break
            # One inversion converts the whole herd's new points to
            # affine (Montgomery's trick), then collision-check each in
            # herd order, exactly as the old per-step checks did. The
            # affine values are mathematically identical to the old
            # one-inversion-per-point conversions, so the walk — jumps,
            # DPs, collisions, recovered key — is bit-identical; only
            # the cost changed (8 inversions per 4 ops became 1).
            # One cosmetic difference: on a find, the roos stepped
            # earlier in this round already advanced, so the returned
            # ops count can be up to len(herd)-1 higher than the old
            # code's. The key found is the same.
            affines = _batch_to_affine([r[0] for r in stepped])
            for roo, pt in zip(stepped, affines):
                roo[3] = pt
                k = self._check_collision(roo, pt)
                if k is not None:
                    return k, self.ops - start_ops, time.time() - t0
            if self.ops % 100_000 < len(herd):
                self.save_checkpoint()
        self.save_checkpoint()
        return None, self.ops - start_ops, time.time() - t0


def solve_interval(pubkey_hex, a, b, method="forward", max_ops=1_000_000,
                   dp_bits=0, checkpoint_path=None):
    """method: forward | reversed | centre-out.

    - forward: interval [a, b] as given.
    - centre-out: same interval, but tame herd is anchored at its centre
      (see Kangaroo._init_herds). Expected work is unchanged; the anchor
      only changes which collisions are found first.
    - reversed: solve the mirrored interval for k_rev, convert back.
    Returns (key_or_None, ops, seconds). Key is returned, never printed.
    """
    if method == "reversed":
        q_rev = mirror_pubkey(pubkey_hex, a, b)
        solver = Kangaroo(q_rev, a, b, dp_bits=dp_bits, max_ops=max_ops,
                          checkpoint_path=checkpoint_path)
        solver.load_checkpoint()
        k_rev, ops, secs = solver.solve()
        if k_rev is None:
            return None, ops, secs
        k = a + b - k_rev
        if not verify_privkey(k, pubkey_hex):
            return None, ops, secs
        return k, ops, secs
    # forward and centre-out share the solver; centre-out only differs
    # in the tame anchor, which _init_herds already uses.
    solver = Kangaroo(pubkey_hex, a, b, dp_bits=dp_bits, max_ops=max_ops,
                      checkpoint_path=checkpoint_path)
    solver.load_checkpoint()
    return solver.solve()


def main():
    ap = argparse.ArgumentParser(description="Pollard Kangaroo (CPU, pure Python)")
    ap.add_argument("--puzzle", type=int, choices=[140, 145, 150, 155, 160])
    ap.add_argument("--pubkey")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--method", default="forward",
                    choices=["forward", "reversed", "centre-out"])
    ap.add_argument("--max-ops", type=int, default=1_000_000)
    ap.add_argument("--dp-bits", type=int, default=0)
    ap.add_argument("--checkpoint")
    args = ap.parse_args()

    if args.puzzle:
        p = load_puzzles()[args.puzzle]
        pubkey = p["public_key"]
        if args.method == "centre-out":
            a = int(p["front50_start_hex"], 16)
            b = int(p["front50_end_hex"], 16)
        else:
            a = int(p["range_start_hex"], 16)
            b = int(p["range_end_hex"], 16)
    else:
        if not (args.pubkey and args.start and args.end):
            ap.error("need --puzzle or --pubkey/--start/--end")
        pubkey, a, b = args.pubkey, int(args.start, 16), int(args.end, 16)

    ckpt = args.checkpoint or os.path.join(
        HUNT_ROOT, "logs", f"kangaroo-{args.puzzle or 'custom'}-{args.method}.json")
    k, ops, secs = solve_interval(pubkey, a, b, method=args.method,
                                  max_ops=args.max_ops, dp_bits=args.dp_bits,
                                  checkpoint_path=ckpt)
    rate = ops / secs if secs > 0 else 0
    if k is not None:
        # HARD RULE: print only FOUND, never the key.
        print(f"FOUND puzzle #{args.puzzle}" if args.puzzle else "FOUND")
    else:
        print(f"not found: ops={ops} elapsed={secs:.1f}s rate={rate:.0f} ops/s")
    return 0 if k is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
