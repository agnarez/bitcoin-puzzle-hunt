"""Generate exact input files + commands for the public GPU solvers.

Outputs to solver/generated/ — one set per puzzle per tool. These configs
are for a GPU rig (CUDA). They do NOT run on this CPU-only VM, and this
script does not claim otherwise.

Tools covered (see research report §4 for sources and limits):
- RCKangaroo (RetiredCoder) — SOTA Kangaroo, no 125-bit cap. The tool
  that solved #135. https://github.com/RetiredC/RCKangaroo
- JeanLucPons Kangaroo — hard 125-bit interval-width limit. Full #140
  (139-bit width) and front-50% (138-bit) do NOT fit; this generator
  splits the front-50% window into <=125-bit subranges and writes one
  example file per puzzle, plus a splitter script. Also points to the
  Kangaroo-256 fork (ZenulAbidin) which lifts the cap.
  https://github.com/JeanLucPons/Kangaroo
- KeyHunt BSGS (albertobsd) — CPU BSGS. -B both = reversed mode.
  Full #140 BSGS is refused (memory); configs are for subranges.
  https://github.com/albertobsd/keyhunt
- collider (hevnsnt) — GPU Kangaroo, solo or pool.
  https://github.com/hevnsnt/collider
- Coin Cracker (lleoha) — Gaudry-Schost interval ECDLP, CUDA.
  https://github.com/lleoha/coin-cracker

Reversed mode: for Kangaroo/BSGS tools that take a pubkey, the reversed
variant uses the mirrored pubkey Q_rev = (a+b)*G - Q over the same
interval. A key found for Q_rev (k_rev) converts to k = a + b - k_rev.
The generator computes Q_rev with secp256k1.mirror_pubkey and writes it
into the reversed config files, with the conversion formula in the
accompanying README. NEVER put a found key in a generated file.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from secp256k1 import mirror_pubkey  # noqa: E402

HUNT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HUNT_ROOT, "solver", "generated")


def load_puzzles():
    with open(os.path.join(HUNT_ROOT, "data", "puzzles.json")) as f:
        return json.load(f)["puzzles"]


def bits(n):
    return n.bit_length()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    return path


def gen(puzzle):
    n = puzzle["n"]
    pubkey = puzzle["public_key"]
    lo = int(puzzle["range_start_hex"], 16)
    hi = int(puzzle["range_end_hex"], 16)
    f_lo = int(puzzle["front50_start_hex"], 16)
    f_hi = int(puzzle["front50_end_hex"], 16)
    centre25 = int(puzzle["centre25_hex"], 16)
    width_full = hi - lo + 1
    width_f50 = f_hi - f_lo + 1
    q_rev_f50 = mirror_pubkey(pubkey, f_lo, f_hi)
    q_rev_full = mirror_pubkey(pubkey, lo, hi)

    # --- RCKangaroo: -range is the interval WIDTH in bits, -start is hex.
    write(os.path.join(OUT, f"rckangaroo-{n}-front50.sh"),
          f"# RCKangaroo — puzzle #{n}, FRONT-50% window, centre-out scope\n"
          f"# Width {bits(width_f50)-1} bits (front-50% width = 2^{bits(width_f50)-1}).\n"
          f"# Run on a CUDA GPU rig. -dp 16 = distinguished-point bits.\n"
          f"RCKangaroo -dp 16 -range {bits(width_f50)-1} "
          f"-start {format(f_lo, 'x')} -pubkey {pubkey}\n")
    write(os.path.join(OUT, f"rckangaroo-{n}-front50-reversed.sh"),
          f"# RCKangaroo — puzzle #{n}, FRONT-50% window, REVERSED\n"
          f"# Mirrored pubkey Q_rev = (a+b)*G - Q for the front-50% interval.\n"
          f"# If this run finds k_rev, the real key is k = a + b - k_rev\n"
          f"#   where a = {format(f_lo, 'x')}, b = {format(f_hi, 'x')}.\n"
          f"# NEVER write a found key into this file or any public file.\n"
          f"RCKangaroo -dp 16 -range {bits(width_f50)-1} "
          f"-start {format(f_lo, 'x')} -pubkey {q_rev_f50}\n")
    write(os.path.join(OUT, f"rckangaroo-{n}-full.sh"),
          f"# RCKangaroo — puzzle #{n}, FULL range (for reference; front-50% is the hunt scope)\n"
          f"RCKangaroo -dp 16 -range {bits(width_full)-1} "
          f"-start {format(lo, 'x')} -pubkey {pubkey}\n")

    # --- JeanLucPons Kangaroo: 3-line input file, 125-bit width limit.
    # Front-50% width is N-2 bits (138 for #140) — too wide. Split into
    # subranges of at most 125 bits: chunk width 2^125, count 2^(N-2-125).
    chunk_bits = 125
    chunk_width = 1 << chunk_bits
    n_chunks = (width_f50 + chunk_width - 1) // chunk_width
    # Example: the centre chunk (contains centre25) and the first chunk.
    centre_chunk = (centre25 - f_lo) // chunk_width
    for label, idx in (("centre", centre_chunk), ("first", 0)):
        cs = f_lo + idx * chunk_width
        ce = min(f_hi, cs + chunk_width - 1)
        write(os.path.join(OUT, f"jlp-kangaroo-{n}-front50-{label}-chunk{idx}.txt"),
              f"{format(cs, 'x')}\n{format(ce, 'x')}\n{pubkey}\n")
    write(os.path.join(OUT, f"jlp-kangaroo-{n}-front50-split.sh"),
          f"# JeanLucPons Kangaroo — puzzle #{n}, FRONT-50% window\n"
          f"# HARD LIMIT: interval width <= 125 bits. Front-50% width is "
          f"{bits(width_f50)-1} bits, so it splits into {n_chunks} chunks of "
          f"2^125 keys each.\n"
          f"# Two example chunk files are generated (centre + first).\n"
          f"# Generate ALL chunk files with: python3 -c \"...\" (see generated/README.md)\n"
          f"# Or use the Kangaroo-256 fork (ZenulAbidin/Kangaroo-256), which\n"
          f"# lifts the cap to 256 bits and takes the same 3-line format:\n"
          f"#   ./Kangaroo -gpu jlp-kangaroo-{n}-front50-full.txt\n"
          f"# Example chunk run:\n"
          f"./Kangaroo -gpu jlp-kangaroo-{n}-front50-centre-chunk{centre_chunk}.txt\n")
    # Full front-50% file for Kangaroo-256 (same 3-line format).
    write(os.path.join(OUT, f"jlp-kangaroo-{n}-front50-full.txt"),
          f"{format(f_lo, 'x')}\n{format(f_hi, 'x')}\n{pubkey}\n")

    # --- KeyHunt BSGS ---
    write(os.path.join(OUT, f"keyhunt-{n}.txt"), f"{pubkey}\n")
    write(os.path.join(OUT, f"keyhunt-{n}-bsgs.sh"),
          f"# KeyHunt BSGS — puzzle #{n}\n"
          f"# WARNING: BSGS memory is ~sqrt(width) points. Full/front-50% #140\n"
          f"# needs ~2^69 table entries — impossible. Use only on small\n"
          f"# subranges (see solver/bsgs.py, which refuses large intervals).\n"
          f"# Forward:\n"
          f"./keyhunt -m bsgs -f keyhunt-{n}.txt -b {n} -R\n"
          f"# Reversed (both directions):\n"
          f"./keyhunt -m bsgs -f keyhunt-{n}.txt -b {n} -B both -R\n")

    # --- collider / Coin Cracker ---
    write(os.path.join(OUT, f"collider-{n}.sh"),
          f"# collider — puzzle #{n} (GPU Kangaroo, solo)\n"
          f"# Note: collider selects by puzzle number; it searches the full\n"
          f"# range, not the front-50% window. Front-50% scoping is a\n"
          f"# RCKangaroo / JLP-Kangaroo feature, not a collider option.\n"
          f"./collider --puzzle {n} --kangaroo\n"
          f"# Pool mode (payout share is DP-proportional):\n"
          f"# ./collider --worker <your-BTC-address>\n")
    write(os.path.join(OUT, f"coin-cracker-{n}.sh"),
          f"# Coin Cracker (Gaudry-Schost) — puzzle #{n}, FRONT-50% window\n"
          f"coin-cracker --dp-bits 16 --public-key {pubkey} "
          f"--begin {format(f_lo, 'x')} --range-bits {bits(width_f50)-1}\n")
    return {"n": n, "q_rev_front50": q_rev_f50, "q_rev_full": q_rev_full,
            "jlp_chunks": n_chunks, "centre_chunk": centre_chunk}


def main():
    os.makedirs(OUT, exist_ok=True)
    results = [gen(p) for p in load_puzzles()]
    readme = """# Generated GPU solver configs

One set per puzzle (140, 145, 150, 155, 160) per tool. These are for a
CUDA GPU rig — they do NOT run on the CPU-only Muse VM.

## Files per puzzle N
- `rckangaroo-N-front50.sh` — RCKangaroo, front-50% window (the hunt scope).
- `rckangaroo-N-front50-reversed.sh` — same, with the mirrored pubkey
  Q_rev; if it finds k_rev, the real key is k = a + b - k_rev.
- `rckangaroo-N-full.sh` — full range, for reference only.
- `jlp-kangaroo-N-front50-centre-chunk*.txt` / `-first-chunk*.txt` —
  JeanLucPons Kangaroo 3-line inputs. JLP has a hard 125-bit width limit,
  so the front-50% window is split into 2^(N-127) chunks of 2^125 keys.
  Only the centre chunk (contains the 25% centre) and the first chunk
  are written as examples; generate the rest with the snippet below.
- `jlp-kangaroo-N-front50-full.txt` — same 3-line format for the
  Kangaroo-256 fork, which lifts the 125-bit cap.
- `keyhunt-N.txt` + `keyhunt-N-bsgs.sh` — KeyHunt BSGS (CPU, small
  subranges only; full #140 BSGS is impossible on memory).
- `collider-N.sh`, `coin-cracker-N.sh` — collider / Coin Cracker commands.

## Generate ALL JLP 125-bit chunks for puzzle N
```python
import json
p = {x["n"]: x for x in json.load(open("../data/puzzles.json"))["puzzles"]}[140]
lo = int(p["front50_start_hex"], 16); hi = int(p["front50_end_hex"], 16)
W = 1 << 125
for i, s in enumerate(range(lo, hi + 1, W)):
    e = min(hi, s + W - 1)
    open(f"jlp-kangaroo-140-front50-chunk{i}.txt", "w").write(
        f"{s:x}\\n{e:x}\\n{p['public_key']}\\n")
```

## BitCrack is NOT included — deliberately
BitCrack brute-forces by *address* and ignores the public key, so for
these pubkey-exposed puzzles it faces the full 2^139 address checks
instead of ~2^70 Kangaroo ops. It is the right tool for address-only
targets (#71 etc.), the wrong tool here. See docs/METHOD.md.

## Hard rule
A found key goes ONLY to agnarez privately in the main chat, and ONLY
into private/FOUND-PRIVATE.txt. Never write a key into a generated file,
a log, or any public output.
"""
    write(os.path.join(OUT, "README.md"), readme)
    for r in results:
        print(f"puzzle {r['n']}: JLP front-50% splits into {r['jlp_chunks']} "
              f"x 2^125 chunks; centre chunk {r['centre_chunk']}; "
              f"Q_rev(front50)={r['q_rev_front50'][:20]}...")
    print(f"generated files in {OUT}")


if __name__ == "__main__":
    main()
