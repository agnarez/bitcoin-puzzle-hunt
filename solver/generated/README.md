# Generated GPU solver configs

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
        f"{s:x}\n{e:x}\n{p['public_key']}\n")
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
