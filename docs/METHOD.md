# Method — Front 50%, Centre-Out from 25%, Reversed

Targets: Bitcoin Puzzle #140, #145, #150, #155, #160 — the only five
unsolved puzzles with a public key exposed (2019-06-01 creator spend).
Source: `data/puzzles.json` (privatekeys.pw / OnePiece-Bitcoin
`data/puzzles.json`, verified on-chain 2026-08-20, still unsolved
2026-11-10). Full research: `~/workspace/research_notes/bitcoin-puzzle-hunt-research-20261110-1408/report.md`.

## 1. The intervals

Puzzle *N* has its key in `[2^(N-1), 2^N)`. Width `W = 2^(N-1)`.

| Puzzle | Full range | Front-50% window | Centre-25% | Midpoint |
|---|---|---|---|---|
| 140 | `[2^139, 2^140)` | `[2^139, 2^139+2^138)` | `2^139+2^137` | `2^139+2^138` |
| 145 | `[2^144, 2^145)` | `[2^144, 2^144+2^143)` | `2^144+2^142` | `2^144+2^143` |
| 150 | `[2^149, 2^150)` | `[2^149, 2^149+2^148)` | `2^149+2^147` | `2^149+2^148` |
| 155 | `[2^154, 2^155)` | `[2^154, 2^154+2^153)` | `2^154+2^152` | `2^154+2^153` |
| 160 | `[2^159, 2^160)` | `[2^159, 2^159+2^158)` | `2^159+2^157` | `2^159+2^158` |

Exact hex values are in `data/puzzles.json` (`range_start_hex`,
`front50_end_hex`, `centre25_hex`, `midpoint_hex`).

- **Front 50% Only:** the window is the lower half of the range.
  A Kangaroo run on that half-width interval costs `sqrt(W/2) =
  sqrt(W)/sqrt(2)` — about 0.71× the full-interval work — *conditional*
  on the key being in the window.
- **Centre-Out from 25%:** the start point is the bottom of the range
  plus 25% of the width, i.e. the midpoint of the front-50% window.
  Scan both ways from there (forward and backward) inside the window.
  For *sequential* scanning this halves the expected distance to a
  front-half key: a uniform key in the window has expected distance
  0.25 of the window from the front start, but 0.125 from its centre.
- **Midpoint variant (xlh6):** anchor at `M`, the midpoint of the *full*
  range (`2^(N-1)+2^(N-2)`), with a down arm (backward from `M`) and an
  up arm (forward from `M+1`), interleaved. Same logic, different centre.
  Implemented as `scan-midpoint` in `solver/reversed_scan.py`.

## 2. Reversed / backwards scanning

The mirror map for an interval `[a, b]`:

```
k_rev = a + b - k
Q_rev = (a + b)·G − Q
```

If `k` is the key for `Q`, then `k_rev` is the key for `Q_rev`.
Searching for `k_rev` forward is searching for `k` backwards.
Implemented in `secp256k1.mirror_pubkey`, used by `kangaroo.py`,
`bsgs.py`, and `rckangaroo_gen.py` (reversed GPU configs use the
mirrored pubkey).

## 3. Pollard's Kangaroo and BSGS maths

For an interval of width `W`, Kangaroo costs `Θ(sqrt(W))` group
operations with constant `c ≈ 1.15` (RCKangaroo/collider SOTA) to `≈ 2.08`
(JeanLucPons). BSGS costs the same time but `Θ(sqrt(W))` *memory* —
for #140 that is ~2^70 stored points, impossible. Kangaroo stores only
distinguished points, so it is the main engine.

| Puzzle | Width | √W (ops, c=1) | vs #135 (2^67) | At 10 Gops/s |
|---|---|---|---|---|
| 140 | 2^139 | 2^69.5 ≈ 8.4×10^20 | ×5.7 | ~2,650 yr |
| 145 | 2^144 | 2^72 ≈ 4.7×10^21 | ×32 | ~15,000 yr |
| 150 | 2^149 | 2^74.5 ≈ 2.7×10^22 | ×181 | ~84,000 yr |
| 155 | 2^154 | 2^77 ≈ 1.5×10^23 | ×1,024 | ~480,000 yr |
| 160 | 2^159 | 2^79.5 ≈ 8.5×10^23 | ×5,800 | ~2.7M yr |

**Implementation trap found by the smoke test (2026-11-10):** the
Kangaroo jump table must have gcd 1. An early version scaled all jumps
by 4, partitioning the interval into residue classes mod 4; the
forward test key happened to share the tame starts' residue, but the
mirrored key `k_rev` did not, so reversed Kangaroo could never collide
in 500,000 ops. The fix: jumps are unscaled powers of two starting at
1 (`solver/kangaroo.py: make_jumps`, with a `gcd == 1` assertion).
Any Kangaroo implementation — including GPU ones — must satisfy this;
a jump set with a common factor silently makes some keys unreachable.

Reference point: #135 was solved in ~5 months on ~200 GPUs
(RetiredCoder, 28 Jul 2026). Scaling from that pace, #140 alone is
~2.4 years on 200 GPUs; #160 is ~2,400 years. On this VM (1.5 CPU,
no GPU, Python Kangaroo ~10^3–10^4 ops/s, C scanner ~10^5 keys/s),
#140 would take far longer than the age of the universe. The tools
here are correct, checkpointed, and ready to scale to a GPU rig —
they do not make #140 solvable on this VM, and nothing honest can
claim otherwise.

## 4. Honest odds — what front / centre-out / reversed do and do not do

**No evidence keys cluster in front.** Among the 83 solved keys,
privatekeys.pw's distribution chart puts 40 in the front half and 43
in the back half, spread across all ten deciles (peak: 60–70%, with
14). That is consistent with uniform random placement.

Consequences, stated plainly:

1. **Front-50%-only caps unconditional success at 50%.** Under
   uniformity the key is in the window with probability 1/2, and a
   front-only campaign never finds back-half keys. It is a bet on the
   distribution, and the data give no reason to make that bet — except
   as a deliberate, stated scope choice, which is what this hunt is.
2. **Centre-out does not change Kangaroo's expected work.** Kangaroo
   walks are randomised over the interval; expected ops depend on
   interval width, not on where the tame herd starts. Centre-out only
   shortens *sequential* distance to a front-half key (see §1).
3. **Reversed does not change expected time if keys are uniform.**
   Reversal searches the same interval with the same `sqrt(W)`
   complexity; a key at position *p* is found as early by the reverse
   front as a key at position *1−p* is by the forward front. Running
   forward + reverse fronts simultaneously avoids leaving top-half
   keys until last, but does not reduce total expected work.
   ("Backwards is not magic." — xlh6 page; "neither end is luckier on
   average" — gk6x page.)
4. The one genuine benefit of centre-out/midpoint starts noted in the
   sources is coordination: it reaches the "least-crowd-searched
   middle" — an argument about *other hunters'* coverage, not about
   the key distribution.

## 5. Why BitCrack is the wrong tool here

BitCrack brute-forces by *address* (derive key → address, compare).
It ignores the public key, so for these puzzles it faces the full
2^139 address checks instead of ~2^70 Kangaroo ops. It is the correct
tool for address-only targets (#71 etc.) and is deliberately *not*
generated in `solver/generated/`. The right engines for pubkey-exposed
puzzles are RCKangaroo, JeanLucPons Kangaroo (≤125-bit intervals, or
the Kangaroo-256 fork), KeyHunt BSGS (small subranges only), collider,
and Coin Cracker — see `solver/generated/README.md`.

## 6. Risks and claiming

- **#66 (Sep 2024) and #69 (Apr 2025) were stolen in the mempool.**
  The solver broadcast the spend publicly; bots extracted the newly
  revealed public key, Kangaroo'd the narrow 66–69-bit range, and
  replaced the transaction with a higher-fee one. The original solver
  got nothing.
- **#67 and #68 were claimed safely** by submitting directly to a
  miner without first broadcasting to the public mempool (MARA
  Slipstream is the named option).
- **For #140–160 the pubkey is already public**, so a broadcast spend
  does not newly enable Kangaroo — but private submission is still
  prescribed as belt-and-braces, and a found key must never be
  published in any form.
- **The creator can move the funds at any time** (they moved funds in
  2017, 2019, and 2023). A solve is a race against that, not just
  against other hunters.
- **Hard rule (locked in):** a found private key goes ONLY to agnarez
  privately in the main chat, and ONLY into
  `private/FOUND-PRIVATE.txt`. The public website never carries a
  private key — not before claiming, not after, not ever. It can only
  announce "SOLVED — puzzle #, date, ops searched" with no key.
