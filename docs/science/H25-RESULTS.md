# H25 — frozen D: independent falsification test

**Decision: NO-GO. Do not proceed to H26 Rust implementation or H27 performance engineering.** The registered worst-file bound is definitively violated on an available source; the fourth source is missing, so full four-source aggregate, coverage and win-rate outcomes remain incomplete. No replacement corpus, no revised gate, no tuning after measurement. The observed advantage on prior selected log families remains a historical result, not evidence of broad competitive advantage.

## Reproducibility
- [Protocol](H25-PROTOCOL.md), commit 0821ef93e2383f030c0f576c5af54b7e753f2d89.
- [Validation script](../../research/science/h25_frozen_validation.py), commit 0b7d5a84fd82d01b663509eb63502996a1144784, SHA256 2ce0ebd230f09694cc71e0553063f9c943ecf6c92ea9be4067e0f0ca832d34e7.
- [Raw results](results/H25-20261125.jsonl), commit b40388986a85fb1df56506ec2f4d307300602375, SHA256 87400dc66fb672df727781af73ccc543ad22459fac98244e6cf573c51db5fe6e (9283 B, 6 lines).
- Frozen H18 module SHA256 1b71aaa8778c46ef4b82f16162f32304df58df8b42d99f49b111a80fab911298. H22 module SHA256 da3ba8d1e7ad86507281655f83bff8af2c9fd9519c847e58bd87fd1e7965b816; H21 07d1ff28850023a68a2839a4072924472a03a9503c45e434dd17ed38a55f0778; CLP binary SHA256 fe3e1cf508c996c94de0a39d96a2113d5a475590e5048511ddfa7cb68d695718. Logfold pinned commit 0330396bbe2bc7c44ea07e24d0c57b8725f7bbc2.
- VDS job job_01M89ZT7AX00MFDKPQEG4QN1PN succeeded with recorded source skip. CPU0, nice+10, RLIMIT_AS 2GiB. XZ/liblzma 5.4.5, Zstd1.5.5, 7-Zip23.01, Brotli1.1.0, CLP0.14.1. No installation/system changes. 48/48 performed exact checks: 3 sources × (3 D repetitions + 13 controls). 64 planned including optional Brotli. All D repeated archive sizes and SHA256 identical per sample. All controls complete and exact on obtained samples.
- Source URLs, download/member/window hashes and offsets in JSONL. KTH and SDSC from production workload traces in SWF (same format, different sites), NASA HTTP from independent archive; fixed UCI power source skipped after curl exit28 timeout despite one retry. These are new sources relative to prior tests, but not a blind randomized sample of all workloads. No private logs. 6,291,335 input bytes; 64,365 rows. Temporary data cleaned, lab tmp only benchmark.lock; 32 GiB disk available. No main branch changes.

## Full archive sizes (bytes)
| Source | D | XZ5 | XZ9 | Zstd19 | Zstd22 | PPMd5 | PPMd7 | 7z5 | Logfold | Logfold-XZ | CLP3 | CLP19 | CLP19-XZ | Brotli11 | Strong |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| KTH | 206541 | 216736 | 202348 | 232782 | 232773 | 293085 | 241645 | 217823 | 375810 | 304252 | 437465 | 327229 | 257508 | 209788 | 202348 |
| SDSC | 249733 | 291816 | 272088 | 314878 | 314813 | 367543 | 348289 | 292734 | 467539 | 371744 | 496900 | 391486 | 314952 | 281436 | 272088 |
| NASA | 218625 | 161840 | 141552 | 143504 | 143498 | 111979 | 102765 | 161976 | 209124 | 166772 | 290319 | 253311 | 198144 | 136542 | 102765 |

Strong = per-file minimum of 13 verified controls, not a single deployable codec. CLP native sizes include all regular archive files including SQLite DB; derived tar+XZ also exact. D contains complete original-length and CRC framing. No feature parity claim versus searchable CLP. 
Available total D 674899 B vs strong 577201 B (+16.9262%), wins 1/3. KTH +2.0722%, SDSC −8.2161%, NASA +112.7427%. Even the two eligible SWF sources together yield D 456274 B vs strong 474436 B (−3.8281%), only 1/2 wins. XZ9 beats XZ5 on both and exposes a weakness of earlier controls. 

## Structural eligibility (fixed criterion)
| Source | Rows | Groups | Eligible numeric bytes | Fraction of source | Groups/rows | Eligible |
|---|---:|---:|---:|---:|---:|---|
| KTH | 22795 | 2 | 696282 | 33.20% | 0.0088% | yes |
| SDSC | 22442 | 2 | 866375 | 41.31% | 0.0089% | yes |
| NASA | 19128 | 4968 | 163018 | 7.77% | 25.97% | no |

Eligibility = numeric variable values >=10% input bytes and groups <=10% rows. 66.67% of available bytes eligible, just one domain. No filtering of primary outcome. This eligibility rule does not identify a reliably large advantage even among eligible sources. NASA observed failure is consistent with prior OpenStack template fragmentation; this is an association, not a causal compressed-size decomposition.

## Resource diagnostics (fresh processes)
D medians of three runs; XZ9 single run. CPU seconds (GNU time user+system rounded to hundredths). RSS KiB; wall/CPU per process, Python D includes whole framing and reconstruction. XZ9 CLI includes input/output. No Rust or matched dedicated throughput claims.
| Source | D enc median CPU | D dec median CPU | D max enc RSS | D max dec RSS | XZ9 enc CPU | XZ9 dec CPU | XZ9 enc RSS | XZ9 dec RSS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| KTH | 3.70 | 1.53 | 67076 | 42412 | 1.65 | 0.02 | 23168 | 4224 |
| SDSC | 4.26 | 1.66 | 66188 | 38888 | 2.60 | 0.03 | 23808 | 4224 |
| NASA | 3.83 | 1.53 | 94768 | 33040 | 1.20 | 0.01 | 48512 | 4224 |

Worst observed D CPU encode 4.28s, decode 2.00s, RSS 94768 KiB (~92.55 MiB), within generous feasibility limits. This does not demonstrate competitive speed: current Python decoder substantially slower than XZ9 in these diagnostics. Shared VDS and nonmatched implementations, XZ9 short CPU times imprecise. 

## Registered gates and final disposition
| Gate | Required | Available outcome |
|---|---|---|
| complete | 4 sources, mandatory controls exact | incomplete (3/4 sources, 39/39 controls on available) |
| aggregate | >=10% saving | available −16.93%; full aggregate unverified |
| wins | >=3/4 | 1 win among 3, at most 2/4 possible: definitive fail |
| worst file | <=105% strong | NASA 212.74%: definitive fail |
| coverage | >=75% bytes and >=2 domains | available 66.67%, one domain; full unverified |
| resource | per run CPU enc<=60s dec<=5s RSS<=256MiB | available PASS; full unverified |

The protocol permits resolving a missing source without changing parameters, but no result on UCI can fix the win-count and worst-file vetoes. Stop this cycle rather than spending further resources on a mathematically impossible GO. No change to thresholds. The narrow H19/D research direction is not a production candidate; no new implementation justified. Do not claim nonexistence of useful specialized log compression generally. Previous experimental advantages remain reproducible local observations. 
Totals: 48 new successful main checks, 7207 cumulative; H25 is the final falsification gate of this cycle. Recommend strategic review and explicit user decision whether to close the research program or fund a genuinely different hypothesis with a well-defined independent benchmark, not more variants of D. 
