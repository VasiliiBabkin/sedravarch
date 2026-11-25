# H22–H24 — numeric lane ablation and CLP controls
**Decision:** H23 and H24 fail as registered; expanded numeric mode E is rejected. H19 model D shows substantial reproducible size advantage on all five measured windows, including against CLP controls, but no registered broad confirmation of D and no general-archiver or production claim. A dedicated validation protocol for D is justified.

## Reproducibility
- [Protocol](H22-H24-PROTOCOL.md), commit 4fbde2f907a7c577069f9385d4a3b7a98c0564c9.
- [Code](../../research/science/h22_h24_numeric.py), commit df5f62bdfd960e6b017cea32a54fe4ba8198f87a, SHA256 da3ba8d1e7ad86507281655f83bff8af2c9fd9519c847e58bd87fd1e7965b816.
- [JSONL](results/H22-H24-20261125.jsonl), commit 08b6585f1933142a3fb5016c4829bcab078282c6, SHA256 e21e5cb9d6799f63a01a8363b3d855c3bd19bb5348ad8a00d446adab106493d8 (14225 bytes, 10 lines).
- CLP official deb 0.14.1-1 amd64 extracted only into lab, package SHA256 b04653c8e4ccc6fcdbda37e1d8f626e2d0e9af2b8b54fa6dc00c629871a47a7f, executable SHA256 fe3e1cf508c996c94de0a39d96a2113d5a475590e5048511ddfa7cb68d695718. Release https://github.com/y-scope/clp/releases/tag/v0.14.1. Prior art Rodrigues et al. https://www.usenix.org/system/files/osdi21-rodrigues.pdf. Separate smoke confirmed exact spaces, CRLF and no final LF; not included in main check count. No sudo or system package install.
- H18 module SHA256 1b71aaa8778c46ef4b82f16162f32304df58df8b42d99f49b111a80fab911298, H21 module SHA256 07d1ff28850023a68a2839a4072924472a03a9503c45e434dd17ed38a55f0778, Logfold revision 0330396bbe2bc7c44ea07e24d0c57b8725f7bbc2. Same ordinary control binaries as H21; not remeasured versions in this job.
- VDS job job_01M89Z5ZCS002JYS97G99E6413 succeeded; one CPU, nice+10, RLIMIT_AS 2GiB, temporary data cleaned, 32 GiB free. 60/60 executed exact checks, 72 planned. OpenSSH download curl exit22 HTTP failure; skipped per protocol. All nine controls exact on five completed windows. No production changes.
- Public Loghub source https://zenodo.org/records/8196385; archive/member/window hashes in JSONL. HealthApp/HPC dev and confirmation windows disjoint from each other and H21 selected windows. Zookeeper previously used in H18, later window not used in development; not a new independent family across entire research program. Total 10,485,534 bytes and 118,835 LF lines. No private logs.

## Sizes (bytes)
C inferred columns raw, D C plus raw-or-first-order delta, E adds direct ULEB, delta-of-delta, min-base fixed-width packing. All metadata and CRC included in candidate frame, all XZ5 backend. Strong = per-file minimum of nine exact controls, not a single deployable compressor.

| Panel/family | C | D | E | Strong | Best control | D savings |
|---|---:|---:|---:|---:|---|---:|
| Dev HealthApp | 58385 | 41261 | 50385 | 129524 | CLP19 tar+XZ5 | 68.1441% |
| Dev HPC | 56185 | 41185 | 43181 | 79692 | Logfold+XZ5 | 48.3198% |
| Confirm HealthApp | 62937 | 47465 | 58065 | 130392 | Zstd19 | 63.5982% |
| Confirm HPC | 118333 | 81101 | 86905 | 157012 | CLP19 tar+XZ5 | 48.3473% |
| Confirm Zookeeper | 13853 | 12241 | 12181 | 22232 | CLP19 tar+XZ5 | 44.9397% |
| Dev total | 114570 | 82446 | 93566 | 209216 | oracle | 60.5929% |
| Confirm available | 195123 | 140807 | 157151 | 309636 | oracle | 54.5250% |
| Total available | 309693 | 223253 | 250717 | 518852 | oracle | 56.9717% |

| Family | XZ5 | Zstd19 | PPMd5 | 7z5 | Logfold | Logfold-XZ5 | CLP3 | CLP19 | CLP19-XZ5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| HealthApp dev | 149424 | 129714 | 133965 | 149480 | 220558 | 167900 | 222064 | 184882 | 129524 |
| HPC dev | 118592 | 93837 | 111704 | 118896 | 142631 | 79692 | 147231 | 142518 | 84560 |
| HealthApp confirm | 151216 | 130392 | 133916 | 151366 | 219045 | 170088 | 229152 | 188476 | 133164 |
| HPC confirm | 192256 | 217592 | 214438 | 191808 | 283962 | 194540 | 292619 | 239377 | 157012 |
| Zookeeper confirm | 63296 | 45529 | 43036 | 63344 | 62948 | 51732 | 88620 | 79539 | 22232 |

CLP3/19 sizes count all regular archive files including SQLite DBs; omit separate directory framing, which favors CLP. CLP19-XZ5 archives complete generated tree of regular files with tar/PAX then XZ5 and restores via CLP, including DBs. UUID path names/internal metadata may vary across runs; single run, hashes for native CLP are digest of ordered per-file hashes, not a portable archive SHA. Tar-derived control is not directly searchable. CLP is designed also for search, therefore size-only comparison is not feature parity. No speed/memory measurements.

## H22 — numeric dependency diagnostic
| Window | Rows | Groups | Eligible numeric columns | Eligible numeric value bytes | Fraction of source | D vs C savings | Numeric-heavy criterion |
|---|---:|---:|---:|---:|---:|---:|---|
| HealthApp dev | 22757 | 84 | 338 | 728027 | 34.72% | 29.3295% | yes |
| HPC dev | 18060 | 40 | 102 | 357854 | 17.06% | 26.6975% | yes |
| HealthApp confirm | 22995 | 160 | 394 | 732499 | 34.93% | 24.5833% | yes |
| HPC confirm | 39228 | 3 | 11 | 724407 | 34.54% | 31.4638% | yes |
| Zookeeper confirm | 15795 | 28 | 73 | 204652 | 9.76% | 11.6365% | no |

Numeric-heavy predefined >=10% eligible value bytes and <=10% groups/rows. Zookeeper falls below 10%, still included and D wins; rule not a validated predictor. D improves same grouping C in every window, aggregate 27.9115%. H22 is diagnostic, not a registered acceptance gate. Zero differences and distinct counts in JSONL; e.g. HealthApp dev 113313/180426 first differences zero (62.80%). Attribution limited to controlled C→D ablation; cannot assign individual compressed byte savings to single fields.

## H23–H24 — more compact inner coding is not more compact archive
| Window | D inner bytes | E inner bytes | D archive | E archive |
|---|---:|---:|---:|---:|
| HealthApp dev | 262964 | 199697 | 41261 | 50385 |
| HPC dev | 321994 | 306970 | 41185 | 43181 |
| HealthApp confirm | 291073 | 229299 | 47465 | 58065 |
| HPC confirm | 418435 | 378281 | 81101 | 86905 |
| Zookeeper confirm | 171116 | 164244 | 12241 | 12181 |

Expanded E always reduces inner bytes but increases archive bytes on four of five windows. E dev -13.4876% savings vs D (negative), confirm available -11.6074%; fails required +3% improvement. E wins both dev and all three measured confirmation windows against strong controls but missing OpenSSH and improvement criterion not met. H23=false, H24_confirmation=false, H24=false. Do not re-label D as passing E gate. For example frame-of-reference selected in 269 HealthApp dev columns, suppressing repeated byte patterns that XZ can otherwise exploit; the measured result supports a mismatch between local inner-byte objective and full archive objective, not definitive causal attribution to FOR alone.

## Decision and proposed next step
Do not repeat speculative model E variations. D is the candidate with a concrete measured advantage: 5/5 available windows, aggregate 56.9717% smaller than best checked controls (including CLP), but small, correlated panels, one missing source, previously used families and selected promising workload. No claim of novelty, independent statistical confirmation, speed/memory advantage or general-purpose success. Propose H25 dedicated D validation before building Rust production codec: freeze D, independent log sources from other generators/domains, preregister numeric eligibility and size/coverage/win thresholds, include CLP and other exact controls, repeated size and actual resource measures, no adaptive tuning; require a minimum input coverage and worst-file expansion bound. If passes, prototype Rust bounded decoder with fuzz and resource tests, then compare matched throughput. If fails, close this narrow direction. 
