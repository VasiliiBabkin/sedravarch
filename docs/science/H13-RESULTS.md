# H13 — результаты эмпирической карты Парето

**Решение:** завершён screening 14 конфигураций. Наибольший наблюдаемый разрыв — быстрый режим A, но значительные колебания wall time и короткие файлы требуют независимой проверки до выбора новой математической гипотезы. В режиме B — второй приоритет. Режим C близок к минимуму суммарного размера, но неоднороден по файлам. Production NO-GO; новый кодек не разрабатывался.

## Воспроизводимость
- [Протокол](H13-PROTOCOL.md), commit 39f47905c903aefdf91b0c339356e8ccb6ac3f17.
- [Код](../../research/science/h13_pareto.py), commit 621328d7fbc6104f3c52cc81bdf49ded22a2de2b.
- [Все измерения](results/H13-20261125.jsonl), commit 42f9e328c21038d5d1c2eba2e3d53ab2bbba258b.
- SHA-256 скрипта 95e939937b8da727a820e07ecddb2d5ff624e30ca929d4b791611a0508ef8702; JSONL d037eefb6d79b84f9cfdc23bbf87037b5b3f36d92f7a2fc82f8a26bae099d6f4.
- VDS: один CPU affinity, nice +10, последовательное выполнение, GNU time, 2 GiB RLIMIT_AS. Zstd 1.5.5, XZ 5.4.5, LZ4 1.9.4, Brotli 1.1.0, gzip 1.12, 7-Zip 23.01, SedravArch 0.7 previously built control. Binary hashes and command argv in JSONL; 7z hash refers to launcher wrapper rather than underlying executable/library, a reproducibility limitation. All 420/420 byte-exact checks pass (252 Silesia, 168 local), all 140 file/profile pairs stable by encoded size and SHA-256 across three repeats. Total canonical data 10108760 B: Silesia 6291456 B, local 3817304 B. No production services changed. Temporary directories cleaned; 13 GiB free.

## All-panel results
Size is sum of 10 complete independently encoded files, not a single solid archive. Throughput = total input / sum of per-file median wall time. RSS = max per-file median peak RSS, KiB; not maximum of all individual observations. CPU metrics retained separately.

| Profile | Bytes | Encode MiB/s | Decode MiB/s | Encode RSS KiB | Decode RSS KiB |
|---|---:|---:|---:|---:|---:|
| lz4-1 | 5803273 | 42.36 | 59.90 | 3584 | 3712 |
| lz4-9 | 4607269 | 7.34 | 39.74 | 3712 | 3584 |
| gzip6 | 3948085 | 7.11 | 29.34 | 2048 | 1792 |
| zstd1 | 4248724 | 27.48 | 37.52 | 5888 | 4480 |
| zstd3 | 3885439 | 18.80 | 37.39 | 6528 | 4608 |
| zstd9 | 3631417 | 7.13 | 34.78 | 16128 | 4608 |
| zstd19 | 3443549 | 0.88 | 31.98 | 22784 | 4608 |
| xz1 | 3444276 | 2.79 | 13.08 | 9856 | 3200 |
| xz5 | 3118856 | 1.02 | 12.47 | 28416 | 3200 |
| xz9 | 3112300 | 0.82 | 12.78 | 77568 | 3200 |
| brotli9 | 3515414 | 2.77 | 32.01 | 40400 | 4224 |
| 7z5 | 3117482 | 1.14 | 10.06 | 17792 | 7424 |
| ppmd5 | 2979917 | 2.53 | 2.21 | 22912 | 21760 |
| sda-balanced | 4850661 | 2.15 | 12.42 | 4492 | 3348 |

Exact five-objective frontier includes all profiles except sda-balanced on both panels and aggregate. On aggregate gzip6 dominates the tested historical SedravArch balanced profile in all five metrics. This is not a statement about newer code, other profiles, all inputs, or statistical significance of all time differences. High-dimensional exact dominance naturally produces a broad frontier; do not rank 13 non-dominated points as equally desirable.

## Preregistered budget slices
A: encode >=20, decode >=50 MiB/s, both RSS <=64 MiB.
B: encode >=5, decode >=20 MiB/s, both RSS <=256 MiB.
C: decode >=10 MiB/s, decode RSS <=16 MiB, encode RSS <=512 MiB, no encode speed floor.

| Panel | Unconstrained min | A lz4-1 | B zstd9 | C xz9 |
|---|---:|---:|---:|---:|
| Silesia | 1839057 | 3726513 | 2311031 | 1959276 |
| Local | 1140860 | 2076760 | 1320386 | 1153024 |
| All | 2979917 | 5803273 | 3631417 | 3112300 |

Unconstrained min is PPMd5 across each complete panel, not a per-file oracle. Relative excess (budget winner/min - 1): A 94.7461%, B 21.8630%, C 4.4425% overall. The gap is not achievable saving: it is measured tradeoff under the tested finite menu. At the same measured budgets a future candidate must reach at most 5513109 B (A), 3449846 B (B), or 2956685 B (C) to save >=5% on this diagnostic panel (floor(0.95*winner)); independent test required. Alternative criterion >=2x throughput at <=101% size and no worse other resource constraints. Do not use these observations to tune and claim validation on H13.

## Per-file observations
The winner under budget B is Zstd9 on 9/10 samples and Zstd3 on mozilla. A is infeasible on dickens and glib-news on a per-file basis; aggregate A feasible because aggregate rate is weighted by input/time. For the eight feasible files A's size excess relative to individual unconstrained best is 67.74–135.46%. Under B: mozilla +43.18%, mr +40.47%, x-ray +37.47%, dickens +37.81%, osdb +32.97%; samba only +7.47%. Under C: x-ray +36.57%, dickens +25.52%, glib-news +21.23%; mozilla, samba, crypto reach individual min. These are exploratory observations, not causal evidence for any transform.

## Critical uncertainty
Wall times include launching CLI, shell wrappers, output writing and scheduling. 280 triples (140 pairs × encode/decode) examined: median relative range (max-min)/median = 27.65%; empirical 90th percentile index = 125.47%; worst 420.04% (dickens gzip6 decode). This is a noisy shared VDS experiment, not isolated throughput. In particular, the A decode threshold excludes Zstd1 in this measured run, but this may be caused by process overhead or server contention; do NOT claim a fundamental speed limitation of Zstandard. The absolute times are not transferable to a different machine or longer files. No cache dropping; warm OS cache, deterministic randomized profile order. RSS is process max, not total application memory or theoretical dictionary size. The two decompressed local gzip samples are canonical plaintext, not original .gz compression tasks. New local sources are not blind representative samples; windows of reused Silesia families are not independent holdout. Stronger/newer controls and specialized filters not exhausted. No new algorithm or novelty claim.

## Next research decision (H13.1 proposal)
First validate the fast/balanced gap with longer full files (>=8 MiB where available), separate in-process native codec timing from CLI end-to-end measurements, include Zstd fast modes and intermediate levels, LZ4 modes, and a fast strong control such as libdeflate where available. Use bounded resource budgets and randomized repeated measurements; record CPU and wall, process peak RSS; examine variability before making threshold decisions. If budget A gap persists, choose a specific representation mechanism with predicted savings (e.g. token parsing cost vs decode-friendly command layout) and compare against optimized LZ4/Zstd at matched resources. If gap disappears or is a measurement artifact, abandon that direction. No alteration to H13 original budget criteria; preregister H13.1 separately. B is an alternative target only if the gap survives calibration. 
## Reproduction
```bash
source ~/sedravarch-lab/bin/env.sh
cd ~/sedravarch-lab
python experiments/h13/h13_pareto.py --lab "$PWD" --out results/h13-reproduction.jsonl
```
New output path. Verify source and binary hashes. The local packages can change. 
