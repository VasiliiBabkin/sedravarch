# H21 — результаты укрупнения структурных моделей и адаптивного выбора

**Решение:** основная панель COMPLETE, H21-F, H21-E и incremental gate не пройдены. Крупный локальный выигрыш на HealthApp и HPC подтверждён относительно проверенных общих и двух вариантов специализированного контроля Logfold; не заявлять универсальное или production преимущество. H21-E не интегрировать.

## Воспроизводимость
- [Протокол](H21-PROTOCOL.md), commit 88a56c0f6c27ef2fba55310f1bdc19de9361c004.
- [Код](../../research/science/h21_coarsen.py), commit b5798cdbfb4e6b4e15d7f877d70d02b0bd933a0a, SHA256 07d1ff28850023a68a2839a4072924472a03a9503c45e434dd17ed38a55f0778.
- [JSONL](results/H21-20261125.jsonl), commit 65b0d3508e9f4885cc9fd49bc669bd23e9ae50c8, SHA256 6cc5b0f92219f9b3e1c171d6117beb9a091f2756f9353b125e0b856959b5bbf6 (16996 B, 10 lines).
- H18 module SHA256 1b71aaa8778c46ef4b82f16162f32304df58df8b42d99f49b111a80fab911298. Logfold 0.1.0 source pinned commit 0330396bbe2bc7c44ea07e24d0c57b8725f7bbc2, https://github.com/sani-savaliya/logfold, Apache-2.0. Core API reproduces default gzip9 JSON representation (mtime=0), derived JSON+XZ5 also measured. No dependencies installed. Not a claim to have tested strongest specialized log compressor. LogNexus explicitly describes token-level not byte-level restoration, https://github.com/OpsPAI/LogNexus; original Logzip not executed.
- Source public Loghub Zenodo record https://zenodo.org/records/8196385, paper https://arxiv.org/abs/2008.06448. Archive/member/window hashes and offsets recorded. Whole LF lines after first 2000 lines, at most 2 MiB per source. Four new families, one previously studied family diagnostic. No private data. Apache download failed twice (curl exit 28 timeout), no substitution. No claim that full logs or all planned diagnostic files tested.
- VDS job job_01M89YEBAF00S66K06R9M252ZA succeeded. CPU0, nice+10, lock, RLIMIT_AS 2GiB. 60/60 exact checks among completed samples (48 primary + 12 diagnostic), 72 planned. Total 10485279 B and 93039 LF lines, primary 8388341 B and 85959 lines. Logfold and derived XZ verified exact on every completed file. F selected frame decoded separately. Temp only benchmark.lock, 32 GiB free, no main/service changes.

## Sizes (bytes)
A/B/C/D as H18; E exact group-record proxy coarsening with raw group fallback, F exhaustive min A–E. Full frame includes original length, checksum, mode, group definitions and sequence. Strong = per-file min direct XZ5/Zstd19/PPMd5/7z5 and Logfold/Logfold-XZ5. This oracle is not a fixed deployable codec.
| Family | A | B | C | D | E | F | Strong | F mode |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Mac | 110349 | 89889 | 94425 | 92505 | 92813 | 89889 | 87612 | B |
| HealthApp | 149217 | 62601 | 61445 | 43209 | 43149 | 43149 | 129116 | E |
| HPC | 142437 | 106769 | 99953 | 76077 | 76193 | 76077 | 140352 | D |
| Proxifier | 113585 | 114117 | 105653 | 102729 | 103405 | 102729 | 85202 | D |
| Primary total | 515588 | 373376 | 361476 | 314520 | 315560 | 311844 | 442282 | mixed |
| OpenStack | 153833 | 213433 | 202941 | 203249 | 159261 | 153833 | 131388 | A |

| Family | XZ5 | Zstd19 | PPMd5 | 7z5 | Logfold | Logfold-XZ5 |
|---|---:|---:|---:|---:|---:|---:|
| Mac | 110336 | 95990 | 87612 | 110441 | 178564 | 117460 |
| HealthApp | 149204 | 129116 | 132731 | 149252 | 220534 | 166620 |
| HPC | 142424 | 161903 | 170678 | 142805 | 243765 | 140352 |
| Proxifier | 113572 | 103265 | 85202 | 113706 | 136276 | 109496 |
| OpenStack | 153820 | 136795 | 131388 | 153866 | 178789 | 148480 |

Primary F reduces strong by 29.4920%, but wins only 2/4 (required 3/4). Per-file gains Mac -2.5990%, HealthApp 66.5812%, HPC 45.7956%, Proxifier -20.5711%. E is 0.3307% larger than D, fails required >=3% improvement and win count despite aggregate gain against strong. Best-of A–D = 311904 B; adding E saves only 60 B (0.0192%), fails >=1% incremental gate. Diagnostic OpenStack E vs D saves 21.6424%, but F selects A and F is 17.0830% larger than PPMd. F raw fallback is XZ, not per-file strongest universal compressor.

## Coarsening and model cost
| Family | D groups | E groups | Merged | Raw E groups | E group-record bytes | E row order bytes |
|---|---:|---:|---:|---:|---:|---:|
| Mac | 805 | 804 | 1 | 334 | 680540 | 19516 |
| HealthApp | 151 | 145 | 6 | 75 | 227339 | 22653 |
| HPC | 55 | 51 | 4 | 11 | 292672 | 30874 |
| Proxifier | 566 | 519 | 47 | 154 | 493277 | 25965 |
| OpenStack | 4489 | 4489 | 0 | 4080 | 1626572 | 12403 |

Group record proxy excludes row-ID sequence and header when choosing each shape partition; actual final size includes all. OpenStack reduction largely coincides with raw group fallback, not template merging (0 merged), so do not attribute it to merging. Local uncompressed record-cost reductions do not guarantee entropy-coded savings. HealthApp/HPC wins mostly inherited from D rather than novel E.

## Diagnostic process resources
Single measurement. Candidate worker includes all five encodes, exact checks and selection; F decode in fresh process. Logfold worker includes both representations and verification. Times include process startup/I/O and Python overhead, no matched per-codec throughput comparison; GNU time max RSS is per worker.
| Family | Candidate wall s | CPU s | RSS KiB | F decode wall s | RSS KiB | Logfold shared wall s | RSS KiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| Mac | 11.531 | 11.31 | 93652 | 0.857 | 29008 | 2.037 | 77500 |
| HealthApp | 11.295 | 11.23 | 85188 | 0.651 | 28940 | 7.265 | 71168 |
| HPC | 11.376 | 11.27 | 96272 | 0.642 | 35672 | 4.343 | 71576 |
| Proxifier | 11.562 | 11.52 | 99468 | 0.721 | 28588 | 1.870 | 60588 |
| OpenStack | 32.701 | 32.29 | 111824 | 0.192 | 27520 | 1.396 | 68256 |

## Interpretation and next step
Reject this coarsening and wide selector as preregistered, do not lower win-count thresholds. A narrower hypothesis is now justified: numeric-heavy repetitive log workloads (HealthApp/HPC) may offer a measurable structural advantage. H22 proposal: isolate numeric field representations by ablation on disjoint chunks of those two families and new independent numeric-heavy log families, compare against a stronger specialized byte-exact control (e.g. CLP or another verified lossless codec), with model cost and exact restoration. Predefine workload from observable criteria before examining new compression results; avoid cherry-picking. Establish a baseline with direct per-column integer coding, delta/delta-of-delta, and appropriate strong specialized controls, then test only if meaningful. No algorithm novelty or production claims. 
## Reproduction
Use pinned H18 module and Logfold revision, original source URLs and SHA256, and the same lab environment. 
```bash
source ~/sedravarch-lab/bin/env.sh
cd ~/sedravarch-lab
PYTHONDONTWRITEBYTECODE=1 python experiments/h21/h21_coarsen.py --lab "$PWD" --out results/h21-reproduction.jsonl
```
New output path. Network failures recorded, no data substitution.
