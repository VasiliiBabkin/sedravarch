# H06.2 — результаты сравнительного исследования числовых предикторов

**Решение:** H06.2a и H06.2b не прошли заранее зарегистрированные критерии. Не интегрировать исследованные представления. На ECG получен небольшой локальный выигрыш, но не доказано практически значимое преимущество. Не опровергаются иные предикторы и методы кодирования исключений.

## Воспроизводимость
- [Протокол до измерений](H062-PROTOCOL.md), commit 98d07ba86d731df8b845487313f8b42f80391d29.
- [Исследовательский код](../../research/science/h062_numeric.py), commit 9f91490d6a2fc36a8160275ba75b620ba8a3554c.
- [ALP adapter](../../research/science/h062_alp_driver.rs), commit 2156d4b26af85e8b8a8c510d85351a56bf1b3157.
- [Полные измерения](results/H062-20261124.jsonl), commit 2d99c5e334d238dbcc9cb2c713f4d855c951097c.
- SHA-256 Python: 649194be64dad9fd55ede52fac9ec1c78db2a7207b8c8923256e42c84928bb84.
- SHA-256 Rust adapter: 8c1a46d0ad425e98f2e1c6d0cf7bfae530e5af5b0ba3725a2a42815aa45bec3e.
- SHA-256 ALP executable: a4067dba45033367d93f91fbed66d20f12680708bd5ddf016bfc0f91857800ee.
- SHA-256 JSONL: aaaa29963f124b9dccab4e9cac3e6cc3b520bca7f17f69cf99913de6c1359656.

VDS, one CPU affinity, nice +10, NumPy 2.5.5, zstd 1.5.5, FLAC 1.4.3 from Ubuntu package extracted locally. Official C++ ALP checkout timed out; independently implemented entropack-alp 0.2.1 built with rustc, source commit e92a100cc8f330aa9518d1ebe8b98079d7a3d814, source tar SHA-256 8037e8fc3e926356283fc5c68880395c9a94115bd8e7b747f55c3bfcbe13ec0b. It uses its own wire format and extensions; does not substitute for the original C++ reference. Special-bit smoke test before main experiment passed. All input files available, source hashes in JSONL. All 22 arrays × 9 candidates/controls = 198 byte-exact checks; special-bit smoke test not included in count.

## Sizes
All figures bytes; control and candidate are sums of per-array minima, not a single deployable codec. Headers and exceptions counted.

| Panel | Arrays | Original | Strongest control | Candidate oracle | Saving |
|---|---:|---:|---:|---:|---:|
| ECG | 6 | 786432 | 200405 | 199375 | 0.5140% |
| Speech | 6 | 39634 | 23546 | 24612 | -4.5273% |
| NEON | 2 | 16384 | 3125 | 3892 | -24.5440% |
| Stocks | 2 | 16384 | 1846 | 2466 | -33.5861% |
| POI | 2 | 16384 | 14479 | 15286 | -5.5736% |
| Synthetic integer | 2 | 65536 | 34958 | 32824 | 6.1045% |
| Synthetic float | 2 | 139472 | 1280 | 2606 | -103.5938% |

All five real panels fail the 5% threshold. Integer control is FLAC on each real array. Five of six ECG channels win, but the sixth loses 1932 B (29371 vs 31303). Fixed delta2+byte shuffle+XZ5 sum on ECG = 200394 B, only 11 B smaller than FLAC; per-array oracle gains 1030 B. Integer block scheme with exceptions totals 259882 B plain, 231590 B XZ5, 232802 B Zstd15 on ECG. Thus adaptive predictor/width choice based on uncompressed record cost did not improve aggregate compressed size relative to fixed delta2. On all six speech samples FLAC wins; on the six real floating-point arrays the strongest ALP control wins. Integer synthetic linear signal 2190 vs 33 B, random 32768 raw vs 32791 B candidate; synthetic is diagnostic only. For special floats, all nine candidates/controls preserved bits, including negative zero, NaN payloads and infinities; no exhaustive test or security claim.

Float decimal scheme found exact scales without exceptions on four NEON/stocks arrays; all eight blocks of two POI arrays selected raw. The POI result is consistent with inadequacy of the tested decimal menu for those arrays, not proof of irreducible precision. For special-bit synthetic data, 750 exceptions were stored. No lossiness introduced.

## Limitations
Small public panels, not blind holdout; channels from same ECG record dependent, speech short, float samples from original ALP benchmark. Compared canonical arrays rather than original .dat/.wav/.csv containers. Original C++ ALP not measured. Controls and candidate have different metadata; raw/XZ/zstd rely on external dtype while own frame includes header. One run, no peak RSS. Timing fields are diagnostic only: ALP+outer compression encode excludes previously computed ALP step, fixed delta2 transform preparation excludes preprocessing, adaptive block records reuse precomputed payload; do not compare as end-to-end throughput. Decoder not fuzzed and for trusted data only. Scientific novelty unestablished. No stable codec modifications.

## Next direction
Do not polish this exception scheme or repeat parameter sweeps without a new rationale. H04b.2: study stronger probability predictors with separate ablations, measure log loss before committing to complex codec implementation; compare full encoded bytes against PPMd and stronger context-mixing control if available. Preregister data, resource budget, exact model family and gate. Keep all research prototypes separate from production.

## Reproduction
With the local FLAC and ALP adapter (verified hash), run:
```bash
source ~/sedravarch-lab/bin/env.sh
cd ~/sedravarch-lab
python experiments/h062/h062_numeric.py --lab "$PWD" --out results/h062-reproduction.jsonl
```
New output path; sources pinned where applicable, check input hashes. To build adapter from verified ALP source use rustc --edition 2021 -C opt-level=3 --crate-name entropack_alp --crate-type rlib src/lib.rs, then rustc --edition 2021 -C opt-level=3 --extern entropack_alp=path/to/libentropack_alp.rlib h062_alp_driver.rs -o alp-driver. Compiler/build differences may alter executable hash; record a new reproduction environment explicitly, not silently disable verification. Temporary data directories cleaned.
