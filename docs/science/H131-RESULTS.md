# H13.1 — результаты калибровки нативных быстрых кодеров

**Решение:** 336/336 проверок завершены. Разрыв размеров в режиме A подтверждён на обеих панелях при измеренных медианах, но критерий стабильности времени не выполнен. Не переходить непосредственно к разработке нового кодека. B также не удовлетворяет правилу номинации (Silesia gap <20%, шум выше порога). Production NO-GO.

## Воспроизводимость
- [Протокол](H131-PROTOCOL.md), commit b7410c07c4ba8a66db57ec883b625a125fc8aae1.
- [C++ harness](../../research/science/h131_native.cpp), commit 5cfc80ace0b59c5f50681d158866741b645cb947.
- [Benchmark](../../research/science/h131_bench.py), commit 077873bc803f21f779eeeeb11512da4ad678b872.
- [Resume helper](../../research/science/h131_resume.py), commit e6afff4f5b8b54ae1ec20531b95c810767d43517.
- [Полный JSONL](results/H131-20261125.jsonl), commit 4b446e1efd0fe5d1d63bcbaac155847813cf2426.
- SHA-256 C++ bc5dd8ac7e037894bec129a29b91404be4731ad738231b80526ff9a2706532d9; benchmark 1995b6cb1158df7145d13ca8c83239bfb94b145216be7d18ea16ac4980ada5c8; resume 9425f03d05a10a93a837c62488771808bf778c98855ee44338c638c8d5af7bed; generated resumed benchmark 87bb7766c9621e13f5cc792a47df8d661e0d41b116ac23ab1bc956d7f599595c; executable 48fc97d85213277377a761c0a51764b5749c99594f8d1bf6363c6a5aadae2282; partial JSONL aeb1b3a96050fe59cde51ad1d14f8a07b9384d609401c02fe6bbfb6eab7843f5; complete JSONL 0abb092f5229e430edcfe5653b99619384050972511a1808d58f3c86dd7abe06.
- First job timed out at 300 s after 278 successful trials. Second job resumed 58 missing trials; previous rows preserved verbatim, checked script hash, unique measurement keys, source hashes; no profile or threshold changes. All 336 checks byte-exact, 252 native (14*6*3), 72 CLI (4*6*3), 12 reference (2*6). All repeated file/profile pairs deterministic by size and SHA-256, no missing profiles. Native library versions libzstd 1.5.5, liblz4 1.9.4, libdeflate 1.19, zlib 1.3; installed system runtime libraries linked directly, hashes/package versions recorded. GNU time per-process peak RSS, CPU0, nice+10, laboratory lock, no system package changes. tmp contains only benchmark.lock, 13 GiB available.

## Data and timing boundaries
Silesia: dickens/mr/x-ray whole, first 16 MiB of mozilla; 45,414,466 B. Local: libavcodec whole and first 16 MiB libicudata; 33,328,152 B. Total 78,742,618 B (~75.09 MiB). New local samples not a representative blind holdout; Silesia families reused. Original hashes verified against manifest or logged. Actual files/slices differ from H13; comparison across H13 and H13.1 is diagnostic, not paired causal attribution.
Native frame includes 13-byte header, original size, CRC32, codec tag, payload. LZ4 raw block differs from CLI LZ4 frame, libdeflate gzip carries redundant CRC. Core wall/CPU excludes input reading, output writing and preallocation of harness buffers, plus libdeflate handle creation; library-internal allocations during calls may still occur. CRC32 creation/check included. Native e2e includes process startup, allocations, I/O. Memory includes whole process including buffers; CLI streaming has different buffering. Reference CLI XZ5 and PPMd5 single run, size control only; not repeated speed validation.

## Aggregate measured profiles
All sizes bytes, speeds MiB/s. Core timing for native; e2e for CLI and reference. Each repeated profile: sum of per-file median times, max per-file median RSS, full framed bytes. Reference single observation per file.

| Profile | Bytes | Core enc | Core dec | E2E enc | E2E dec | Enc RSS KiB | Dec RSS KiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| LZ4 accel1 | 49336927 | 263.86 | 858.02 | 82.94 | 126.16 | 36736 | 30336 |
| LZ4 accel4 | 52533701 | 319.90 | 898.15 | 88.07 | 126.05 | 36736 | 30720 |
| LZ4 HC3 | 42482302 | 30.75 | 806.42 | 24.46 | 126.24 | 36992 | 29440 |
| LZ4 HC9 | 41248555 | 12.97 | 788.47 | 11.84 | 124.13 | 36992 | 29184 |
| Zstd -3 | 48020438 | 218.67 | 561.60 | 83.22 | 115.05 | 37248 | 30208 |
| Zstd -1 | 45440607 | 161.40 | 504.87 | 73.68 | 114.43 | 37376 | 29952 |
| Zstd 1 | 37990222 | 156.74 | 375.30 | 71.25 | 116.44 | 37248 | 28416 |
| Zstd 3 | 34393626 | 61.07 | 281.22 | 42.34 | 89.03 | 38016 | 27648 |
| Zstd 6 | 32497212 | 24.15 | 245.62 | 20.43 | 93.54 | 39808 | 27264 |
| Zstd 9 | 31500534 | 15.68 | 205.53 | 14.19 | 81.99 | 47488 | 27136 |
| Zstd 12 | 31188655 | 6.21 | 164.41 | 5.94 | 75.14 | 78208 | 27136 |
| libdeflate 1 | 37501492 | 70.43 | 273.16 | 47.81 | 87.62 | 36864 | 28288 |
| libdeflate 3 | 35670186 | 43.81 | 233.72 | 33.02 | 88.27 | 37376 | 27520 |
| libdeflate 6 | 35044946 | 34.84 | 263.00 | 27.66 | 83.14 | 37248 | 27392 |
| CLI Zstd 1 | 38044266 | — | — | 62.20 | 125.02 | 15104 | 5248 |
| CLI Zstd 3 | 34410119 | — | — | 38.35 | 100.01 | 25984 | 6784 |
| CLI Zstd 9 | 31500480 | — | — | 12.53 | 92.60 | 37504 | 8832 |
| CLI LZ4 1 | 49363155 | — | — | 115.89 | 150.14 | 9728 | 9856 |
| XZ5 ref | 25969484 | — | — | 0.93 | 20.43 | 97536 | 10368 |
| PPMd5 ref | 27880106 | — | — | 2.43 | 2.19 | 24448 | 23296 |

## Resource budgets, preregistered primary core wall
A enc >=20 MiB/s, dec >=50 MiB/s, each RSS <=64 MiB. B enc >=5, dec >=20, each RSS <=256 MiB.

| Panel | Best fixed reference | Per-file reference oracle | A Zstd6 | B Zstd12 | A excess vs fixed ref | B excess vs fixed ref |
|---|---:|---:|---:|---:|---:|---:|
| Silesia | 15540004 (PPMd5) | 14691350 | 19267060 | 18515821 | 23.98% | 19.15% |
| Local | 9943156 (XZ5) | 9943156 | 13230152 | 12672834 | 33.06% | 27.45% |
| Aggregate | 25969484 (XZ5) | 24634506 | 32497212 | 31188655 | 25.14% | 20.10% |

Same winners for native core CPU sensitivity. Core-wall A rates on Silesia 21.87/213.79, local 28.16/308.15 MiB/s; aggregate 24.15/245.62. B 5.37/129.92 and 7.88/257.62, aggregate 6.21/164.41. On Silesia native e2e A winner shifts to Zstd3 (Zstd6 enc 18.74 <20), local and aggregate retain Zstd6 (aggregate enc 20.43 marginal). CLI A winner Zstd3 on each panel, CLI B Zstd9 (not all native levels in CLI menu). The differences are evidence that timing boundaries and profile availability matter; they do not isolate a causal CLI penalty or establish a fundamental algorithmic limit.
Reference oracle sums per-file minima and is not deployable fixed profile. Aggregate fixed reference XZ5 differs from per-panel minima. A gap vs oracle 31.15%, 33.06%, 31.92%; B 26.03%, 27.45%, 26.61%. Gap is excess size, not possible saving. Future 5% target on this diagnostic aggregate A = floor(0.95*32497212)=30,872,351 B with same constraints; on B = floor(0.95*31188655)=29,629,222 B. Independent validation mandatory.

## Variability
Relative range (max-min)/median per file/profile/operation, median and empirical p90 (index floor(0.9*n), no interpolation).

| Panel | Native core wall median / p90 | Native core CPU median / p90 | CLI wall median / p90 |
|---|---|---|---|
| Silesia | 22.83% / 51.26% | 20.10% / 40.64% | 7.98% / 61.89% |
| Local | 24.31% / 55.76% | 21.61% / 49.36% | 24.52% / 50.04% |
| All | 23.55% / 53.74% | 20.48% / 42.55% | 16.63% / 61.89% |

168 native wall triples, 168 native CPU triples, 48 CLI wall triples. Despite larger inputs and direct calls, wall variation exceeds registered 20% limit on both panels and aggregate. Even core CPU median relative range exceeds 20%; no causal diagnosis of source of variability (shared VDS, scheduling, frequency/cache etc. unisolated). Larger input/native timing reduced aggregate median wall range relative to H13 (27.65%) only descriptively; the datasets, profiles and timing boundaries differ.
**A nomination gate fails:** >=20% gap on both panels yes, median relative range <=20% no. B gap Silesia 19.15% also fails the analogous 20% condition. Do not substitute CPU or CLI statistic post-hoc. No new codec developed.

## Next step (proposal)
H13.2 targeted calibration, not a broad new sweep: focus Zstd3/6/9/12, LZ4 and libdeflate6, repeat native calls in the same process with standardized warmup, per-call timing and checksum, measure allocation-inclusive alternative separately. Compare isolated vs end-to-end boundary, record CPU frequency/steal/load indicators if accessible without privileged changes, 7+ repeats, report per-profile uncertainty and robust margins to speed thresholds, retain original A/B budgets. New independent families where feasible. Register timing-stability criterion and rules before execution. Only nominate new representation when reproducible practical advantage is plausible; no lowering H13.1 gate. If stable, investigate asymmetric cost of encoder parse choices versus decode commands, starting from known Zstd/LZ4 parsers and matched controls, not presumed novelty. 
## Reproduction
```bash
source ~/sedravarch-lab/bin/env.sh
cd ~/sedravarch-lab
g++ -std=c++17 -O3 experiments/h131/h131_native.cpp -o experiments/h131/native -l:libzstd.so.1 -l:liblz4.so.1 -l:libdeflate.so.0 -l:libz.so.1
python experiments/h131/h131_bench.py --lab "$PWD" --out results/h131-reproduction.jsonl
```
Use new output path, verify source and library hashes. Longer single job or bounded resume as above; resume helper requires complete newline-terminated partial JSONL and matching script hash. Original partial retained in VDS; complete JSONL includes original prefix and resume marker. No production changes.
