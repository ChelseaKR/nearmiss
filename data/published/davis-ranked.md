# Ranked segments — Davis

> **Synthetic demonstration data — not real reports. The hotspots are planted in the fixture, so the method finds what was put there.**

**Re-segmentation (MAUP) check:** 180 block units re-segmented into 90. The top-rate segment stays rank 1 *and* stays a significant Gi\* cluster at the coarser scale (top-5 rank overlap 0.80).

**Exposure-sensitivity check:** not evaluated — no rated segment declares an alternative exposure reading, so the ranking was never re-run under a different denominator. An unanswered question, not a passed check.

**Permutation reference check:** 3 of 5 significant cluster(s) do not clear the 0.05 level against a reference distribution of 999 re-shuffles. Their significance rests on the analytic normal approximation; the published flags are unchanged.

**Dependence robustness check:** 1 of 5 significant cluster(s) survive a false-discovery correction valid under arbitrary dependence (level 0.0161 instead of 0.05, across 12 simultaneous tests). The published flags are unchanged.

**Shrinkage stability check:** the top-rate segment stays rank 1 after every rate is shrunk toward the overall 3.68; it keeps 0.64 of its own rate (top-5 overlap 1.00).

| Rank | Segment | Rate /1000 | 95% CI | n | Hotspot |
| ---: | --- | ---: | --- | ---: | --- |
| 1 | 5th St (C–D) | 20.00 | 7.30–43.53 | 6 | ★ Gi* z=3.25 |
| 2 | C St (4th–5th) | 15.00 | 5.48–32.65 | 6 | ★ Gi* z=2.39 |
| 3 | 5th St (B–C) | 15.00 | 5.48–32.65 | 6 | ★ Gi* z=2.39 |
| 4 | 5th St (D–E) | 15.00 | 5.48–32.65 | 6 | ★ Gi* z=2.39 |
| 5 | D St (4th–5th) | 15.00 | 5.48–32.65 | 6 | ★ Gi* z=2.39 |
| 6 | 3rd St (B–C) | 2.50 | 1.53–3.86 | 20 | no Gi\* neighbors — global z=-0.62 |
| 7 | B St (1st–2nd) | 2.00 | 0.40–5.84 | 4 |  |
| 8 | 1st St (A–B) | 0.00 | 0.00–2.45 | 0 |  |
| 9 | 2nd St (D–E) | 0.00 | 0.00–2.45 | 0 |  |
