# Hunt progress history

Dated checkpoints for puzzle #140 — the puzzle being scanned. Main search is the
Pollard Kangaroo (centre-out, front 50%); C-scan is the fast C scanner checking the
front half key-by-key. All five puzzles are still unsolved; no private key has ever
been found. Current snapshot lives in [hunt-progress.json](hunt-progress.json).

| Date (WIB) | Main ops | C-scan keys | Notes |
|---|---|---|---|
| 2026-11-10 22:03 | 0 | 0 | Hunt goes live, non-stop, with watchdog |
| 2026-11-10 22:07 | 303,000 | — | First reading (300,000 Kangaroo + 3,000 sequential) |
| 2026-11-11 09:50 | 81,703,000 | 20,056,000,000 | Daily report #1 |
| 2026-11-12 09:50 | 208,303,000 | 54,606,000,000 | Daily report #2; audit gap growing |
| 2026-11-13 09:50 | 272,903,000 | 74,026,000,000 | Daily report #3; all five prizes intact on-chain |
| 2026-11-14 09:50 | 321,703,000 | 88,916,000,000 | Daily report #4 |
| 2026-11-15 09:50 | 382,503,000 | 106,811,000,000 | Daily report #5 |
| 2026-11-16 09:52 | 422,703,000 | 119,526,000,000 | Daily report #6; 370 watchdog restarts |
| 2026-11-16 23:46 | 446,103,000 | 126,901,000,000 | Checkpoint gap 17,397,000 (under-count, work was real) |
| 2026-11-17 02:43 | 469,303,000 | 128,651,000,000 | **Reconciliation applied**: +17,800,000 stranded ops credited, gap 0, counting fixed |
| 2026-11-17 09:30 | 489,603,000 | 134,891,000,000 | Audit PASSES again (gap 0); daily report 491,603,000 |
| 2026-11-17 12:59 | 511,103,000 | 140,226,000,000 | Closing in on the 150B C-scan milestone |
| 2026-11-17 17:46 | 535,103,000 | 146,836,000,000 | — |
| 2026-11-17 21:46 | 542,003,000 | 148,866,000,000 | 475 watchdog restarts |
| 2026-11-17 23:46 | 545,103,000 | 149,796,000,000 | ~204M short of 150B |
| 2026-11-18 00:14 | 546,103,000 | 150,091,000,000 | **🎯 MILESTONE: C-scan passes 150,000,000,000 keys** |
| 2026-11-18 02:11 | 555,004,000 | 151,321,000,000 | Throttle live: watchdog 15m → 5m, Kangaroo ~6.5x faster (~4,500 ops/s), C-scan ~295k keys/s |
| 2026-11-18 04:56 | 639,404,000 | 156,141,000,000 | — |
| 2026-11-18 07:09 | 708,104,000 | 160,136,000,000 | Latest checkpoint; both workers alive, 493 restarts |
| 2026-11-24 09:50 | 5,138,604,000 | 408,456,000,000 | Daily report; audit PASS, checkpoint lead 200,000 (in tolerance); all 5 prizes unspent |

## Notes

- **Watchdog restarts** count every time the platform replaced the machine and the
  watchdog brought both workers back. No work was lost at any restart.
- **The gap (Nov 11–16):** the Kangaroo saved checkpoints mid-chunk but progress was
  only credited when a full 200,000-op chunk finished, so each machine replacement
  stranded up to 100,000 checkpointed ops. The work was real and never redone —
  progress was under-counted, never double-counted. Fixed 2026-11-17 with
  `reconcile_kangaroo_progress()` in `solver/run_hunt.py`.
- **Rates:** main search ~4,500 ops/s (long-window, after the 2026-11-18 batch-inversion
  speedup); C-scan ~295,000 keys/s.
- **Prizes:** all five intact on-chain at every check (14 / 14.5 / 15 / 15.5 / 16 BTC).
