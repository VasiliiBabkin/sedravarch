# H12 — реальное условное арифметическое кодирование ошибок совпадений

**Решение:** H12a и H12b отклонены по зарегистрированным критериям. Получен реальный локальный выигрыш над оригинальным CABAC-представлением поправок на новой текстовой панели, но не практически значимое улучшение полных архивов по установленному критерию. Не интегрировать; не заявлять новый конкурентоспособный архиватор.

## Воспроизводимость
- [Протокол](H12-PROTOCOL.md), commit b031a44b242c6bf52f1e3ed6dae6f7118a7f1bfb.
- [Инструментирование](../../research/science/h12_instrument.py), commit 67b80e9626102debc59d83af6c6d2f39936aa980.
- [Арифметическое кодирование](../../research/science/h12_arithmetic.rs), commit b4b0e358b3d3a1617faf0e153fb9876abeee30fd.
- [Rust driver](../../research/science/h12_driver.rs), commit c402e127a14bdea8f00e12c4d78771fad47f7dbf.
- [Python audit](../../research/science/h12_audit.py), commit 20604f51ac6a787f5bd3cf5e4ee658610c0487ae.
- [Полный JSONL](results/H12-20261124.jsonl), commit 21a6d74dd2c3a6d36efcffc46f538f9d4087b11b.
- Crate preflate-rs 0.7.6 SHA-256 1a2e9d0ac8c6cd9bb134681e11b5a32c7c56b89c5958cf785775080def38537c; Cargo.lock H10 без изменений.
- SHA-256 driver source dffee0c8affc2b0f67bebe5a3128c1068e55192fe95b34b314645d3dafb124ae; instrumentation 59065864998ee9a12bf07755f44bf4132af9495ec69b4c4263a22472c4586b0c; arithmetic e8fc07d055b889c2721ea32cb0cd49f959454c478703ff195a31810928f99fb3; Python dd1655149979db4f667ba076ace545c85c739e59f82fdb8733d25d8c0e01d023; binary e573c917ccdb54896111dd9753cc7d07f063b39a7ebae80c7167568cb5275a55; JSONL 0f0a403df259353e65fe2d8f1100413347500728c65136d06eeb141f9373b941.

VDS, release build locked, one CPU affinity (CPU 0), nice +10. All 23 files and 148 streams accepted, 224510 predicted-reference events (43680 old, 180190 new text, 640 new binary). 529 byte-exact checks: 148*3 raw stream representations + 23*3 full file representations + 8*2 direct controls. Baseline CABAC replay verified via H11 instrumentation; old baseline correction length and reference event count matched H10 for each stream. Alternative decoder obtains predicted length/distance before decoding each label; original predictor and all non-reference correction values unchanged. Independent arithmetic channel has own termination and mode/length overhead. Source hashes, exact frame hashes and measurements recorded. Temporary files cleaned; disk 13 GiB available, tmp only benchmark.lock.

## Correction blob size, bytes

All modes include one-byte mode; L/M include additional u32 length, original bitcode params and CABAC without reference errors, arithmetic stream. No posthoc selection in gate.

| Panel | Streams | Original | L | M | L reduction | L wins |
|---|---:|---:|---:|---:|---:|---:|
| New text | 4 | 5503 | 3897 | 3986 | 29.1841% | 2 |
| New binary | 4 | 203 | 208 | 207 | -2.4631% | 1 |
| Old PDF | 16 | 1950 | 1587 | 1595 | 18.6154% | 6 |
| Old DOCX | 74 | 3219 | 3395 | 3406 | -5.4675% | 11 |
| Old XLSX | 38 | 1588 | 1755 | 1754 | -10.5164% | 3 |
| Old ZIP | 9 | 1277 | 1145 | 1134 | 10.3367% | 7 |
| Old PNG | 3 | 662 | 390 | 489 | 41.0876% | 2 |
| Old total | 140 | 8696 | 8272 | 8378 | 4.8758% | 29 |

H12a fails: new text passes size criterion, new binary fails; only 3/8 wins (required 4/8). Two large successful text cases: nginx changelog.gz 2284→1652 B (27.67%), coreutils NEWS.gz 3142→2148 B (31.64%). bash.1.gz 44→54 B, coreutils.info.gz 33→43 B. Thus high number of reference decisions alone does not predict benefit: latter has 85688 predicted-reference events and a very small original correction blob. The new binary panel has only 640 events, and no structural representation is selected for the full files. L wins one correction blob there (fontconfig-user.pdf.gz 67→62 B). No claim that estimated strategy, event count or data type alone explains performance.

## Complete archive sizes, bytes

The complete experimental H12 frame includes original file length, CRC32, all raw/structural records, plaintext, exact original container wrappers, correction blobs, and outer XZ5. Local selection is strict per record, not a globally optimized search. Control for new panels is per-file min(direct XZ5,zstd15) over the original gzip file; old panels use previous verified strong control including Precomp+XZ5, matched by SHA-256. H12 baseline is our wrapper with original preflate, NOT official full-file preflate pipeline. 

| Panel | Baseline wrapper | L | M | Strong control | L vs baseline | L vs strong |
|---|---:|---:|---:|---:|---:|---:|
| New text | 416676 | 415032 | 415116 | 497912 | 0.3946% | 16.6455% |
| New binary | 364556 | 364556 | 364556 | 364251 | 0% | -0.0837% |
| Old PDF | 496144 | 495576 | 495600 | 494164 | 0.1145% | -0.2857% |
| Old DOCX | 169540 | 169512 | 169440 | 130292 | 0.0165% | -30.1016% |
| Old XLSX | 586192 | 586216 | 586184 | 479276 | -0.0041% | -22.3128% |
| Old ZIP | 677896 | 677116 | 677096 | 665683 | 0.1151% | -1.7175% |
| Old PNG | 24888 | 24616 | 24708 | 24833 | 1.0929% | 0.8738% |
| Old total | 1954660 | 1953036 | 1953028 | 1794248 | 0.0831% | -8.8498% |

H12b fails: neither new panel meets >=1% relative to baseline wrapper, and binary fails >=5% vs direct controls. The new text wrapper saves 16.32% already with baseline preflate and 16.65% with L; most gain is the existing precompression approach. H12 incremental L saves 1644 B of complete frames in that panel. New binary frames identical by size across modes (all raw fallback); overhead increases size slightly against direct strong controls. Old total L saves 1624 B over baseline wrapper, still 8.85% larger than strong controls. The L/M difference in full sizes illustrates that local correction size and global outer compression are different objectives; no tuning or switching after data inspection.

## Resource measurements (diagnostic)
GNU time peak RSS in KiB, per driver subprocess, not full Python pipeline. Encode wall includes original trace, verification, replay, isolated category measurements, both candidate encodes and I/O; cannot compare per-mode encode speed. Internal phase timings not independent end-to-end measurements. Sum wall for standalone stream decode includes process startup and I/O.

| Panel | Shared encode wall ms | Encode max RSS KiB | Decode wall ms original/L/M | Decode max RSS KiB original/L/M |
|---|---:|---:|---|---|
| New text | 1067.89 | 10844 | 325.50 / 272.93 / 243.51 | 5888 / 5632 / 5632 |
| New binary | 192.93 | 6400 | 57.17 / 65.20 / 52.26 | 3840 / 3712 / 3968 |
| Old | 2512.16 | 5632 | 1185.41 / 1130.08 / 1186.94 | 3072 / 3072 / 3072 |

One run; no confidence intervals, no production throughput claim. Full-frame decode records time excludes outer XZ decompression and is not full decoder runtime. 

## Scientific interpretation and decision
H11's conditional model improvement has a real analogue in the L arithmetic channel on a distinct text panel, but the overall effect is not competitive at the registered thresholds. The original hypothesis is rejected, including further optimization of this single correction category for general archiving. Preserve code for reproducibility only. No novelty claim: conditional coding with context features is established, and these experiments do not prove a unique method. New panels are local gzip files (four documents and four binary files, including three related fonts), not a blind representative holdout. New panels lack a separately measured full-file Precomp control, but original preflate wrapper provides the isolated channel control. Only one pinned preflate build tested, no independent uninstrumented output comparison, no fuzzing or production parser. Stable/main unchanged.

## Proposed next research decision
Close the current DEFLATE-specific incremental channel direction. Before more codec engineering, set a new independent target where the potential full-file improvement is large enough. H13 proposal: quantify full representation costs and compare size/speed/peak-RSS frontiers on substantially larger, diverse public inputs, with fixed reproducible budgets and modern strong controls. Use a preregistered Pareto criterion (e.g. size savings at matched decode resources OR resource savings at matched size) and distinguish screening from independent validation. Do not simply combine rejected prototypes or lower H12 gates after observing results.

## Reproduction
Verify pinned crate and lock, copy h12_driver.rs to crate root and h12_arithmetic.rs to src/. Apply h11_instrument.py then h12_instrument.py. Build cargo build --release --locked --bin h12-driver --target-dir <temporary-dir>. Install executable to lab experiments/h12/h12-driver. Run:
```bash
source ~/sedravarch-lab/bin/env.sh
cd ~/sedravarch-lab
python experiments/h12/h12_audit.py --lab "$PWD" --out results/h12-reproduction.jsonl
```
Requires pinned H07b.2 and H10 JSONL and detector. Verify input hashes (local gzip versions can change), use new output path. 
