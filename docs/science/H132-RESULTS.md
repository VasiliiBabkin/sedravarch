# H13.2 — результаты повторных нативных вызовов

**Решение: основной эксперимент COMPLETE, 344/344 проверок; номинации A и B не прошли.** Не начинать новую LZ77-архитектуру на основании H13.2. Результаты локального smoke H132-STATUS.md не включены в основной счётчик.

## Воспроизводимость
- [Протокол](H132-PROTOCOL.md), commit cfd0342e3f95dcd49d8cae5aa735a358588e0757.
- [Калибровочный стенд](../../research/science/h132_calibrate.py), commit 95e98202abf828d65d44563141e73bfac7e0725e; SHA-256 af97553b4daea05c886b70ac23d22d650aea4ea0e62498132942030ad72d2eed.
- [Resume helper](../../research/science/h132_resume.py), commit 81fd2c63e32a5f24d27b0bac8d4289ab789cb54f; SHA-256 f369ecc6e2c6eef5ba3fd17589d6f7d36f8068063e660d752abefffa4618eac0 (VDS copy).
- [Полные измерения](results/H132-20261125.jsonl), commit 4871b5355441fdf6f02d8c2946d1e4aacb5cab56; SHA-256 13ef52ed4fe01078e80b22a74f5f9bede1b5fe46ab7e24d07b20d8ffaa2b17a1; 85953 B, 65 lines.
- Original partial JSONL SHA-256 09bc0bfa1683c7d14cabf0205d0b271b474a76515306e6299c7389eb42fab643. Generated resumed script SHA-256 eeb89e127c20b14e9d98ee9498b2e3d7d5b2c767a8df9bb7232210894a0d2019.

VDS initially blocked by ENOSPC; restricted Gateway command diagnosed 100% filesystem use, 2% inode use. After checking Rust build processes and CACHEDIR.TAG, removed only four generated debug/build and debug/incremental directories in temporary .sedrava-sqlite-a5.auiH6QDN checkouts. Used bytes 77726433280→63481999360, reduction 14244433920 B; ordinary Gateway restored. Source, release directories, databases, sites and SedravArch laboratory retained. A trailing LF introduced by transfer was removed to match exact pinned script hash before measurements. First job job_01M88VDGNF00W6WVECDRSZ9JHQ timed out at 600s after all 48 native pairs and six reference checks. Resume job job_01M88W07KB00MEHTBJHAAJ5GFR verified unchanged source/library hashes and CPU affinity, retained original JSONL prefix and completed two missing references. No profile or gate changes. Final temporary directory contains only benchmark.lock; 12 GiB free. No production service changes or main commits.

Python 3.12.3, libzstd 1.5.5, liblz4 1.9.4, libdeflate 1.19, zlib 1.3. One CPU (0), nice+10. 2 warmups and 7 measured consecutive calls per phase in each worker. 4 sources × 6 profiles × 2 allocation modes × 7 = 336 exact decoded checks; plus 8 reference checks = 344. All completed; repeated encoded bytes and prealloc/alloc archive hashes matched. Full framed size includes 13-byte H131 header and CRC32. Python FFI and whole worker RSS differ from C++ H13.1 measurement boundaries.

## Corpus
Silesia dickens 10192446 B and first 16777216 B mozilla; local libavfilter.so.9.12.100 13549208 B and libx265.so.199 16308864 B (whole file because <16 MiB). Total 56827734 B. Source and library SHA-256 in JSONL. Reused Silesia families, two new local libraries; not blind holdout. 
## Primary preallocated results
Bytes, MiB/s, KiB. Speeds are total input divided by sum of per-file median call durations. Worst observed rate uses sum of per-file maximum durations; not confidence interval. RSS includes Python process/buffers and verification.

| Panel | Profile | Bytes | Encode | Decode | Worst encode | Worst decode | Enc RSS | Dec RSS |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Silesia | LZ4 a1 | 15797425 | 193.01 | 719.39 | 94.64 | 344.76 | 53376 | 55040 |
| Silesia | Zstd3 | 10858043 | 30.53 | 192.52 | 20.81 | 155.46 | 54316 | 51200 |
| Silesia | Zstd6 | 10322789 | 24.84 | 289.25 | 19.77 | 219.38 | 56104 | 50432 |
| Silesia | Zstd9 | 10071382 | 9.97 | 176.29 | 7.84 | 111.12 | 63912 | 50304 |
| Silesia | Zstd12 | 9928902 | 6.44 | 267.24 | 5.20 | 184.22 | 94644 | 50304 |
| Silesia | libdeflate6 | 11218363 | 31.25 | 260.67 | 29.17 | 231.28 | 53504 | 50944 |
| Local | LZ4 a1 | 10689622 | 173.14 | 565.36 | 102.63 | 384.48 | 52224 | 48256 |
| Local | Zstd3 | 6840828 | 88.63 | 131.79 | 49.76 | 71.14 | 53268 | 44032 |
| Local | Zstd6 | 6356802 | 38.09 | 413.21 | 36.13 | 298.73 | 55296 | 43264 |
| Local | Zstd9 | 6130803 | 17.65 | 145.10 | 8.50 | 62.36 | 62848 | 43008 |
| Local | Zstd12 | 6087654 | 10.66 | 382.46 | 8.49 | 238.18 | 93716 | 42880 |
| Local | libdeflate6 | 7508223 | 47.15 | 329.94 | 42.98 | 273.57 | 52736 | 43648 |

Reference XZ5: Silesia 8787828 B, local 5040136 B; PPMd5 9146776/6187233 B. Fixed reference winner XZ5 both. Single reference measurement, not speed validation.

## Registered gates
A: >=20/50 MiB/s encode/decode, both RSS<=64 MiB. B: >=5/20 MiB/s, both RSS<=256 MiB. Nomination requires excess size >=20% versus best fixed reference on BOTH panels, median relative range <=20% on BOTH panels, and chosen median-feasible winner also satisfies worst-repeat speed floors.

| Panel | A winner | A size excess | A worst speed pass | B winner | B size excess | B worst speed pass | Prealloc median range |
|---|---|---:|---|---|---:|---|---:|
| Silesia | Zstd6 | 17.47% | NO | Zstd12 | 12.98% | YES | 42.76% |
| Local | Zstd6 | 26.12% | YES | Zstd12 | 20.78% | YES | 46.76% |

A fails Silesia size gap and worst encode threshold (19.77<20), timing stability on both panels. B fails Silesia size gap and timing stability both. No selection of alternate mode after looking at data. Allocation-inclusive diagnostic A winner Zstd3 on Silesia (23.56% excess, worst pass) and Zstd6 on local (26.12%, worst fail). B Zstd12 both (Silesia worst fail, local pass). Allocation-inclusive relative range medians 41.78%/37.39%. Variation remained substantial despite warmup; causes not isolated. Do not claim that native speed itself regressed relative to H13.1: code, corpus, timing boundaries and number of repetitions differ. These gates do not establish that no fast compression improvement is possible.

## Interpretation and next direction
H13, H13.1 and H13.2 show measured resource/size tradeoffs, not an identified exploitable mathematical weakness. Close this calibration cycle without relaxing thresholds. For any subsequent speed-based claim, obtain a quieter or dedicated environment and register a new independent comparison. Avoid indefinite calibration or claiming a win from noisy measurements. A possible distinct research direction is a byte-exact, size-first structural model with an explicitly specified decoder work budget (bounded operations and memory) and strong matched controls; only if mathematically motivated and passing independent screening should real throughput claims be attempted. This is a proposal, not an implemented result, and does not replace failed A/B gates. No production GO.

## Reproduction
Use the pinned source and library versions, VDS laboratory and source hashes above. 
```bash
source ~/sedravarch-lab/bin/env.sh
cd ~/sedravarch-lab
python experiments/h132/h132_calibrate.py --lab "$PWD" --out results/h132-reproduction.jsonl
```
If job times out, preserve newline-terminated raw partial and apply the resume helper to a new output path only after first job and child processes have terminated. Verify hashes and unchanged conditions; document interruption. Disk safety floor 5 GiB. 
