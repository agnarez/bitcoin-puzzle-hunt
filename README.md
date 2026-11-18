# Bitcoin Puzzle Hunt

Hunting the five known **pubkey-exposed** Bitcoin puzzles — #140, #145, #150, #155, #160 — for **75 BTC combined**, using reversed / backwards scanning, centre-out from 25%, and front-50%-only methods.

Live since 2026-11-10, running non-stop with a watchdog. This repo holds the solver code, the runner, and the live progress numbers. No private key is — or will ever be — in this repo.

- **Live progress site:** https://muse.ai/s/bitcoin-puzzle-hunt-live-progress-qd6xa6jvxxlrq/Vk-N8ZR5QNjnJA0mbiR_MXl0W1Ly2wczzIq2PG9ofR4
- **Research page:** https://muse.ai/s/bitcoin-puzzle-hunt-research-xtxu6xa8ubzdgx0/axoghp0rB4ISigDvMiSogBS0IxjdLZeOHVcGPvN2LQQ
- **Website:** https://agnarez.github.io/bitcoin-puzzle-hunt/
- **Progress data:** [hunt-progress.json](hunt-progress.json)

## Targets — all still unsolved

| Puzzle | Address | Prize | Range |
|---|---|---|---|
| #140 | `1QKBaU6WAeycb3DbKbLBkX7vJiaS8r42Xo` | 14 BTC | [2^139, 2^140) |
| #145 | `19GpszRNUej5yYqxXoLnbZWKew3KdVLkXg` | 14.5 BTC | [2^144, 2^145) |
| #150 | `1MUJSJYtGPVGkBCTqGspnxyHahpt5Te8jy` | 15 BTC | [2^149, 2^150) |
| #155 | `1AoeP37TmHdFh8uN72fu9AqgtLrUwcv2wJ` | 15.5 BTC | [2^154, 2^155) |
| #160 | `1NBC8uXJy1GiJ6drkiZa1WuKn51ps7EPTv` | 16 BTC | [2^159, 2^160) |

Public keys for all five are in `docs/METHOD.md` and in the solver code. Reference: https://privatekeys.pw/puzzles/bitcoin-puzzle-tx

## Live progress (2026-11-18)

- **Main search (Pollard Kangaroo, centre-out, front 50%, puzzle #140):** 708,504,000 ops, ~4,500 ops/s
- **Second scanner (fast C scanner, front half key-by-key):** 160,166,000,000 keys / 32,034 slices, ~295,000 keys/s
- **Milestone reached 2026-11-18 ~00:14 WIB:** C-scan passed 150,000,000,000 keys
- **Watchdog restarts:** 493+ across machine replacements — no work lost

## Strategy — the honest version

Among the 83 solved keys there is no front clustering (40 front half, 43 back half), so front-50% / centre-out / reversed scanning does **not** change the expected Kangaroo work (~2^69.5 group ops for #140). It only changes which keys would be found early. Scale vs solved puzzle #135 (~5 months on 200 GPUs): #140 ~5.7x, #145 ~32x, #150 ~181x, #155 ~1,024x, #160 ~5,800x. This is a long hunt, run on free machines — the code here is real, the odds are stated plainly.

## What's in here

- `solver/` — the machines: Pollard Kangaroo (forward / reversed / centre-out, distinguished points, checkpoints, batch-inversion speedup), BSGS (forward + reversed), sequential reversed / centre-out / midpoint scanner, fast C scanner (`c_scan.c`, OpenSSL), smoke tests (`test_smoke.py` — 13/13 PASS on a synthetic key)
- `solver/generated/` — 56 ready-to-run GPU launch files (RCKangaroo, JeanLucPons Kangaroo, KeyHunt BSGS, collider, Coin Cracker) for all five puzzles. BitCrack is deliberately excluded — it's the wrong tool for pubkey puzzles
- `solver/c_scan2.c` — batch-inversion C scanner experiment, tested and **NOT deployed** (measured 0.41–0.44x the speed of `c_scan`)
- `run_nonstop.py` — the non-stop runner (loops 200,000-op Kangaroo chunks, checkpointed/resumable)
- `run_cscan_nonstop.py` — the non-stop C scanner runner (5,000,000-key slices)
- `watchdog.sh` — restarts either worker if it dies; never restarts after a solve or STOP
- `docs/METHOD.md` — the method, the math, and the claim protocol
- `docs/free-setup-my-machine.docx` — the free setup guide (run the hunt on free machines)
- `docs/puzzle-145-status-log.docx` — the daily status log for puzzle #145 (still contradictory: the site says both SOLVED and HUNTING; treated as unsolved)
- `hunt-progress.json` — live ops totals (public-safe numbers only)
- `progress-history.md` — the full dated progress history, from launch to today, including the 150B milestone and the checkpoint reconciliation

## Quick start

```bash
# Smoke test (synthetic key in a small 28-bit range — should find it)
python3 solver/test_smoke.py

# Build the C scanner
make -C solver

# Run one Kangaroo chunk on puzzle #140, centre-out, front 50%
python3 solver/run_hunt.py --puzzle 140 --method kangaroo-centre-out --window front50 --dp-bits 12 --max-ops 200000

# Run non-stop with the watchdog
python3 run_nonstop.py --puzzle 140 --method kangaroo-centre-out --chunk-ops 200000 --dp-bits 12
```

Needs Python 3.12+ and gcc. No GPU required for the Python/C tools; the `generated/` launch files are for a real GPU rig.

## Found-key protocol — locked in

If a private key is found, it goes **only to agnarez, privately**. It is stored only in a private file, never in progress logs, never in this repo, never on any website. A public announcement says only "SOLVED — puzzle #, date, ops searched", and only after the funds are safely moved. Claiming uses a private / direct-to-miner submission (e.g. MARA Slipstream), never a public mempool broadcast — puzzles #66 and #69 were stolen after public broadcasts.

## Free only

Everything here runs on free machines. No paid cloud, no paid GPU runs.

## Credits

Built by agnarez with Muse and the multi-agent crew: dra69on, aoxy, 0xindy, 0xfinu, zync, claude.ai research.

- GitHub: https://github.com/agnarez
- X: https://x.com/agnarez_
- Telegram: https://t.me/agnarez
- Linktree: https://linktr.ee/agnarez
