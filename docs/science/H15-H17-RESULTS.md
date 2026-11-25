# H15–H17 — результаты последовательной оптимизации LZ-парсинга

**Решение:** H15, H16 и H17 отклонены по заранее установленным критериям. H17 выявил внутренний компромисс, но даже вторичный W32 не превосходит сильный контроль. Не интегрировать.

## Воспроизводимость
- [Протокол](H15-H17-PROTOCOL.md), commit be3c5cc33eb2cd3e4eb10aba2190471d34feb0b2.
- [C++ parser](../../research/science/h15_parse.cpp), commit f982b48b827cf56b688792a5dd02ebeb06af2c73, SHA256 574d57ddc7585517f1bfad672390456868e867b3f8846c682bad5f912103c1f3.
- [Python benchmark](../../research/science/h15_h17_bench.py), commit 4fb89df4c94bdfb7ce89d54722b6c2575c6a13c6, SHA256 0e76a2e2b40eb796e008b0efa60a97bebbdd66522d500b08b1743b50fb7b03f7.
- [JSONL](results/H15-H17-20261125.jsonl), commit 050c424785f59fb71625592c9b17e6143f7eff03, SHA256 b49beabece6912b87bf984be91a44ca6fb69a9fc74fe1001ab55113e41744d16, 37908 B, 25 lines.
- Parser executable SHA256 b7ca95aef6d9a38d50f0d2ea46dbbf42d7cebdcaca370608e4dba21ae6272988. H14 module SHA256 6e17c43d344a63aafecbb63f063cebf1109fedde5a18590953b75179727ab404. libzstd 1.5.5 SHA256 0a2128bc10841fb29e76d08d945864dfb0b6a66da5df6df5d8299197439e54bb.
- VDS job job_01M89WYJZH00X1KEH862V4KB15 succeeded. CPU0, nice+10, RLIMIT_AS2GiB, lock, bounded inputs. 19 samples × 9 representations = 171/171 exact roundtrips (108 real, 63 synthetic). Same corpus across stages, not 3 independent data sets. Greedy matched H14 per block; independent command validity, objective inequalities, exact decoding and logical counts checked. Temp contains only benchmark.lock; 33 GiB available. Main unchanged.

## Complete sizes (bytes)
| Group | Input | G | F | E | W8 | W32 | D | Zstd6 | Zstd9 | XZ5 | Direct oracle |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Silesia | 1572864 | 658516 | 644207 | 645793 | 643746 | 626352 | 611782 | 583497 | 573804 | 482184 | 573461 |
| Local | 902115 | 342544 | 337250 | 336322 | 339013 | 335631 | 330278 | 320082 | 309733 | 264932 | 309733 |
| Real | 2474979 | 1001060 | 981457 | 982115 | 982759 | 961983 | 942060 | 903579 | 883537 | 747116 | 883194 |
| Synthetic | 1310811 | 721247 | 719837 | 718692 | 720607 | 721016 | 718994 | 718835 | 718128 | 568932 | 718107 |

Direct oracle = sum per-file min Zstd6/9; not a fixed deployable profile. G/F/E/W8/W32 all use H14 B representation, same Zstd3 backend and experimental framing; D same framing/direct block Zstd3. Whole-input direct controls omit experimental framing. No runtime or RSS measurement.

## H15: fixed-cost shortest path
F minimizes restricted DAG additive cost (8 bits per literal, 32 per match); exact for this surrogate, not for actual compressed bytes. Surrogate savings vs G 7.8644% Silesia, 4.4000% local; actual size saves only 2.1729% and 1.5455%, combined 1.9582%. F vs direct oracle +12.3367% and +8.8841%, 1/12 win (openssl). Required >=5% vs G AND >=5% vs direct each, >=6/12 wins. FAIL.
## H16: empirical probability cost
E uses per-block KT-smoothed 256-symbol marginal prices from greedy parse, quantized; scoring model not transmitted, actual encoding unchanged. E's own surrogate improves vs F 2.6090% / 3.4454%, total 2.9161%; actual E size vs F +0.2462% / -0.2752%, total +0.0670%. E vs direct +12.6132% / +8.5845%, 0/12 wins. Required >=3% improvement over F and >=5% vs direct each, >=6/12 wins. FAIL. Optimizing the selected marginal likelihood proxy does not reliably optimize Zstd-compressed size.
## H17: copy-slice cost
| Group | W8 size change vs E | W8 copy reduction | W8 literal increase | W32 size change | W32 copy reduction | W32 literal increase |
|---|---:|---:|---:|---:|---:|---:|
| Silesia | -0.3170% | 44.1145% | 44.1704% | -3.0104% | 80.0704% | 94.6303% |
| Local | +0.8001% | 23.6938% | 38.2427% | -0.2055% | 64.7755% | 142.7055% |
| Real | +0.0656% | 35.0529% | 42.4198% | -2.0499% | 73.2833% | 108.8278% |

W8 passes size within 101% E both, fails local copy reduction >=25% and literal growth <=10% both; W8 +11.2733% vs direct aggregate, 0/12 wins. Proxy and competitive gates FAIL. W32 secondary: 961983 B vs E 982115, copy count 47891 vs 179255, literal bytes 1424141 vs 681969; still +8.9209% vs direct and 0/12 wins, not a nomination or posthoc replacement. Literal bytes can themselves compress in backend, so shifting work from LZ copying to Zstd is not evidence of total decoder work reduction.

## Real-panel work counts
| Variant | Matches | Copy slices | Literal bytes | Match bytes | Inner bytes |
|---|---:|---:|---:|---:|---:|
| G | 237166 | 242290 | 496848 | 1978131 | 1445868 |
| F | 163201 | 168229 | 697323 | 1777656 | 1350540 |
| E | 174289 | 179255 | 681969 | 1793010 | 1379541 |
| W8 | 115244 | 116421 | 971259 | 1503720 | 1433423 |
| W32 | 47438 | 47891 | 1424141 | 1050838 | 1616179 |

## Interpretation
Known optimal and bicriteria LZ parsing prior art: https://arxiv.org/abs/0802.0835 and https://pages.di.unipi.it/rossano/assets/pdf/papers/SODA14.pdf. Restricted graph, simple additive price and fixed split layout do not establish a novel codec. All mathematical objectives checked, but marginal and fixed prices do not account for Zstd's actual contextual compression. Logical copy counts exclude backend decompression, metadata and allocations. No CPU throughput, total memory traffic or measured peak RSS; one run on reused Silesia families and new local files, not blind validation. H17 is diagnostic because earlier gates failed. Do not claim all possible LZ parsing approaches fail. 

Next decision: stop this restricted-parser/secondary-Zstd representation direction. A distinct subsequent cycle should select a specific lossless workload and estimate information/representation gap before engineering; e.g. sparse correlated typed records or cross-version data with explicit random-access constraints, with current strongest specialized controls and independent data. No lowering gates after observing results. Do not simply repeat earlier rejected transformations; a new hypothesis needs its own mathematical basis and preregistration. 

## Reproduction
```bash
source ~/sedravarch-lab/bin/env.sh
cd ~/sedravarch-lab
g++ -O3 -std=c++17 experiments/h15/h15_parse.cpp -o experiments/h15/parse
PYTHONDONTWRITEBYTECODE=1 python experiments/h15/h15_h17_bench.py --lab "$PWD" --out results/h15-h17-reproduction.jsonl
```
Verify H14 source, corpus and library hashes; use new output path. No production changes.
