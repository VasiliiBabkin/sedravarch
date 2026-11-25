# H18–H20 — результаты обратимого моделирования системных журналов

**Решение:** H18 не прошла; H19 прошла предварительный отбор; H20 не подтвердила переносимость фиксированной модели D. Production NO-GO. Диагностический выбор лучшего из A/B/C/D по полному размеру перспективен как отдельная гипотеза, но не является прохождением зарегистрированного H20.

## Воспроизводимость
- [Протокол](H18-H20-PROTOCOL.md), commit 6a962411b5f85477f889b72e1c958db18f9660d5.
- [Код](../../research/science/h18_h20_logs.py), commit 8044c8002552030c6e0dcb3679fc5786f6755410, SHA256 1b71aaa8778c46ef4b82f16162f32304df58df8b42d99f49b111a80fab911298.
- [Полный JSONL](results/H18-H20-20261125.jsonl), commit c6302513f2ad45c4743b14ea2c42fb65d9f12eef, SHA256 fdcb1e5173aa1137a2659f8b0fe3d1aa23a53f4d796dd5f57639a8df9da03787, 26247 B, 16 lines.
- Loghub source revision dd61d0952749ee7963bde24220d1be5ede023033, public repository https://github.com/logpai/loghub, paper https://arxiv.org/abs/2008.06448. Original raw URLs and SHA256 per file in JSONL. Template-based log compression prior art: https://github.com/logpai/logzip; MDL https://arxiv.org/abs/math/0406077. No novelty claim.
- VDS job job_01M89XW20X00WKA384DEG8BCZY succeeded, CPU0, nice+10, lock, RLIMIT_AS2GiB. Zstandard 1.5.5, XZ/liblzma 5.4.5 (CLI version; Python lzma backend used), 7-Zip 23.01. 12 files × 8 representations = 96/96 byte-exact roundtrips. 24000 lines, 3563865 source bytes. Six development families and six distinct confirmation families, fixed code and thresholds; public data not statistically blind. No annotation CSV or private server logs. No package changes. Temp contains only benchmark.lock, 32 GiB available. Main unchanged.

## Complete sizes (bytes)
A raw XZ5 + 13-byte common frame, B numeric templates, C inferred constant/variable columns by token-shape + anchors, D same C plus reversible canonical-decimal delta lanes. All candidates include model, field tags, order and full framing, compressed by XZ5. Strong oracle = per-file min of unframed XZ5, Zstd19, 7z PPMd5, 7z LZMA2 mx5. Framed oracle = per-file min A/B/C/D; cost of constructing/testing each candidate not measured. Diagnostic only, not primary gate.

| Panel | Input | A | B | C | D | XZ5 | Zstd19 | PPMd5 | 7z5 | Strong oracle | Framed oracle |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Dev | 1414206 | 133398 | 119154 | 112238 | 104666 | 133320 | 125906 | 114929 | 134151 | 113796 | 104666 |
| Confirmation | 2149659 | 127138 | 135578 | 125994 | 122982 | 127060 | 119890 | 117221 | 127414 | 114128 | 107818 |

H18: C vs B reduction 5.8043% dev, 7.0690% confirmation; C vs strong 1.3691% reduction dev, 10.3971% excess confirmation. Dev 4/6 wins, fails >=5% strong reduction. H18 FAIL.
H19: D vs C reduction 6.7464% dev, D vs strong reduction 8.0231%, 5/6 wins. Dev criteria >=3% vs C, >=5% vs strong, >=4/6 wins all passed. H19 screening PASS.
H20: fixed D vs C reduction 2.3906% confirmation; D vs strong excess 7.7580%, 3/6 wins. All three confirmation conditions fail. C also fails confirmation against strong. H20 FAIL, no nomination. Do not replace fixed D with posthoc oracle.
 
## Per-file D compared with strongest control
| Family | Panel | Control B | D B | Savings |
|---|---|---:|---:|---:|
| HDFS | Dev | 38736 | 35305 | 8.86% |
| BGL | Dev | 39038 | 42309 | -8.38% |
| Linux | Dev | 11377 | 10525 | 7.49% |
| Apache | Dev | 6279 | 4421 | 29.59% |
| Spark | Dev | 8941 | 5025 | 43.80% |
| OpenSSH | Dev | 9425 | 7081 | 24.87% |
| Hadoop | Confirmation | 13272 | 9953 | 25.01% |
| OpenStack | Confirmation | 39987 | 60161 | -50.45% |
| Thunderbird | Confirmation | 21578 | 14297 | 33.74% |
| Windows | Confirmation | 9221 | 7117 | 22.82% |
| Android | Confirmation | 15236 | 16113 | -5.76% |
| Zookeeper | Confirmation | 14834 | 15341 | -3.42% |

## Model cost diagnosis
All metrics below before backend compression, not independent components of compressed size. D retains C group definitions/constant bytes/order exactly; chooses numeric lane iff eligible and shorter in uncompressed bytes. Lane length varint costs included. Model bytes include group/field counts, tags and constant values, lane length prefixes. Raw variable bytes include per-value length prefixes; empirical H0 statistics diagnostic only, not file-specific lower bounds.

| Metric | Dev C | Dev D | Confirmation C | Confirmation D |
|---|---:|---:|---:|---:|
| Groups | 459 | 459 | 1919 | 1919 |
| Model bytes | 132490 | 132344 | 979707 | 979639 |
| Lane bytes | 471050 | 314808 | 325905 | 216419 |
| Order bytes | 12434 | 12434 | 13546 | 13546 |
| Inner bytes | 615974 | 459586 | 1319158 | 1209604 |
| Numeric lanes | 0 | 1407 | 0 | 1381 |

D cuts lane bytes by 33.17%/33.59%, but full archive savings vs C only 6.75%/2.39%. Model share of D inner bytes 28.80% dev vs 80.99% confirmation. OpenStack alone has 1346 groups for 2000 lines and 826431 B model description before backend, more than its 595119 B original input. This is evidence of excessive partition/model overhead for this representation, not proof of a causal compressed-size attribution (backend mixes fields). Token-shape/anchor grouping can fragment highly variable logs, storing many nearly singleton templates. 
Framed oracle 104666 vs 113796 dev (8.02% reduction), 107818 vs 114128 confirmation (5.53% reduction). It is a measured best-of-menu diagnostic including full frame overhead, attainable by exhaustive encoding and selection on these inputs, but neither a registered winning fixed model nor independently validated adaptive selector, and its cost not measured. No specialized log compressor was tested; Logzip exact byte reconstruction and stronger specialized baselines remain open. These are small 2k-line samples, not full logs, one run, no timing/RSS, trusted inputs only. No claim of general archiver or production advantage.

## Next research proposal (not performed)
H21: compare an explicitly registered exhaustive selector A/B/C/D with strong specialized byte-exact log compression on larger independent public logs (different families/segments, exact source hashes), then analyze a bounded-cost grouping criterion that merges or abandons templates when total serialized cost increases. Include the raw fallback, complete model cost, exact output, encoding overhead and decoding RAM; distinguish screening from confirmation. Do not reinterpret H20 after observing data. If specialized exact comparator cannot run, report blocker and do not claim competitive log-codec advantage. 
## Reproduction
```bash
source ~/sedravarch-lab/bin/env.sh
cd ~/sedravarch-lab
python experiments/h18/h18_h20_logs.py --lab "$PWD" --out results/h18-h20-reproduction.jsonl
```
Verify source revision, per-file SHA256, versions; new output path. 
