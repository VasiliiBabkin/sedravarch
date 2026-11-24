# H10 — аудит preflate-rs 0.7.6: статистика поправок

**Решение:** специализированный raw-DEFLATE контроль получен, успешно проверен и инструментирован. Новый конкурентоспособный алгоритм не получен. Частоты поправок выявляют кандидата для следующей абляции, но не доказывают недостаток preflate или преимущество альтернативной модели.

## Воспроизводимость
- [Протокол](H10-PROTOCOL.md), commit ea1b27e07adb5e9a872fa1be173729ceeb57930c.
- [Rust driver](../../research/science/h10_driver.rs), commit cba9582986835f820a7b8991376deaf1a5514859.
- [Инструментирование](../../research/science/h10_instrument.py), commit 00a7feb04e78bee06194b2fe66ab0e2a16feeffc.
- [Python audit](../../research/science/h10_audit.py), commit 54e8ed9a4a2ecb3e6379199688e453a9ac4d239b.
- [Полный JSONL](results/H10-20261124.jsonl), commit fd4400197d2a27b1fd5dc196ebd3f4b3d4f6d207.
- [Cargo.lock](../../research/science/h10-Cargo.lock), commit e0d3aaa38afed971ea1958a59dca92b798ebd89b.
- Crate https://static.crates.io/crates/preflate-rs/preflate-rs-0.7.6.crate, SHA-256 1a2e9d0ac8c6cd9bb134681e11b5a32c7c56b89c5958cf785775080def38537c.
- SHA-256 driver source 8e0d451b5d19658498ad9939ed984a96588b3c4406bd930745f9c13eec4eb514; instrumentation 2ced3fb87637a7452a08814cf9345e550d03ed294ff41a0ac268097d4769d143; Python 28b6a53a41cca2fe1572e2296253c2745df42f482c178a31ca40381a33e2397e; lock 8a07a28fb29f4284560156762d4990f1e6349635fac7fc118c11e71dadf60281; driver executable 06bbad89f62a955f192fefbd3cb036909eced39675f885b9975769ae2ea730d5; JSONL 31da13486fc461e4d8a4beb7a304072a72fe0c856310f21f5589e2c64ade4dcd.

## Source audit
Source inspected in the published crate (Apache-2.0). `stream_processor.rs`: parse exact tokens, estimate parameters, predict blocks, encode reconstruction parameters and CABAC corrections via bitcode; verification replays and compares compressed bytes. `token_predictor.rs`: predict token type using estimated parameters and hash chains; for references separately encode length error and rank/hops of alternative matching distances. `tree_predictor.rs`: predict Huffman representation from token frequencies. `statistical_codec.rs`: 17 correction categories, including framing and termination; `cabac_codec.rs`: prediction encoder. Source reference: https://docs.rs/preflate-rs/0.7.6/preflate_rs/ and https://github.com/microsoft/preflate-rs. The hypothesis of encoding decisions conditionally on plaintext is already prior art.

## Build and experimental method
Initial GitHub source archive at e97efb0031ff67e5c8f0154726422e31f6ed8424 exceeded 20 MB download cap, so used smaller official published crate (72883 bytes), not claiming that these two source revisions coincide. First cargo --release --locked --lib build succeeded but copying the artifacts from the expected target directory failed; temporary build cleaned. Second build specified --target-dir and located the executable from Cargo JSON compiler-artifact output; succeeded. Instrumentation adds relaxed atomic counters on entry to encode_correction and exported counts; no intended change to predictor/codec, no byte-by-byte comparison of uninstrumented vs instrumented output performed. Rust driver per stream, max_chain_length=4096, plain_text_limit=262144, verify=true. Explicit recreation and full file byte equality checked. All input hashes match H07b.2, same 140 streams as H09. 140/140 streams pass, 15/15 files pass, 155 checks by protocol accounting. No rejects. Temporary checkout/cache/target and input directories cleaned; tmp contains only benchmark.lock, 13 GiB disk free at end. VDS no sudo, one CPU affinity for benchmark, nice +10.

## Full file sizes
Bytes. Strong = per-file min of old XZ5, Zstd15, 7z, Precomp+XZ5 by matched SHA-256; Ordinary without Precomp. H10 = our local selection of raw vs plaintext+preflate reconstruction data, XZ5 over complete record stream. This is NOT the official preflate whole-file pipeline, nor a new compressor. Old controls not rerun.

| Format | Strong | Ordinary | H09 P | H10 |
|---|---:|---:|---:|---:|
| PDF | 494164 | 499350 | 499920 | 496132 |
| DOCX | 130292 | 185763 | 188032 | 169076 |
| XLSX | 479276 | 587039 | 587432 | 586192 |
| ZIP | 665683 | 677183 | 677528 | 677892 |
| PNG | 24833 | 25629 | 25892 | 24892 |
| Total | 1794248 | 1974964 | 1978804 | 1954184 |

H10 selected 31/140 structural records (PDF5 DOCX17 XLSX5 ZIP2 PNG2); improves H09 P by 1.2442% and Ordinary by 1.0522%, remains 8.9138% larger than Strong. Only one strict per-file win (ibasn6a16.png 3924→3912 B). Different precompression coverage/selection/outer representation prevents ranking modern preflate library against Precomp as an algorithm; specifically, our wrapper limits streams and doesn't implement Precomp's other transformations. Full frame overhead included. Local record XZ totals: raw 353432 B, plaintext+reconstruction records 345624 B (2.2092% smaller), before selection/whole file interaction.

## Correction frequencies
140 streams, compressed payloads 344806 B, plaintext 934398 B. Total serialized reconstruction blobs 8556 B (2.4814% of original compressed payloads); includes estimated parameters and CABAC data. Individual XZ5 of plaintext 335392 B, individual XZ5 of reconstruction blobs 16648 B (additional per-stream headers make these sizes non-additive). H09 explicit match records 130472 B individually XZ-compressed, different format and overhead. It is not a controlled comparison of solely the match cost.

| Correction category | Calls | Nonzero | Nonzero % |
|---|---:|---:|---:|
| TokenCount | 214 | 69 | 32.2430 |
| BlockTypeCorrection | 259 | 96 | 37.0656 |
| LenCorrection | 37154 | 703 | 1.8921 |
| DistOnlyCorrection | 36451 | 1 | 0.0027 |
| DistAfterLenCorrection | 703 | 1 | 0.1422 |
| TreeCodeBitLengthCorrection | 2308 | 0 | 0 |
| LDTypeCorrection | 18728 | 0 | 0 |
| RepeatCountCorrection | 1894 | 1 | 0.0528 |
| LDBitLengthCorrection | 16834 | 0 | 0 |
| TreeCodeCountCorrection | 0 | 0 | n/a |
| LiteralCountCorrection | 141 | 0 | 0 |
| DistanceCountCorrection | 141 | 0 | 0 |
| UncompressBlockLenCorrection | 45 | 45 | 100 |
| Last | 259 | 108 | 41.6988 |
| EndOfChunk | 259 | 108 | 41.6988 |
| LiteralPredictionWrong | 268027 | 64 | 0.0239 |
| ReferencePredictionWrong | 43680 | 6590 | 15.0870 |
| Total | 427097 | 7786 | 1.8230 |

Counts refer to actual encoder correction events, not independently distributed errors or bits. Last/EndOfChunk and stored block length include required structural values; nonzero does not necessarily mean prediction failure. DistAfterLenCorrection encodes hops minus one: zero does not imply the original prediction was correct. Among the two token-type event categories, 6654 nonzero / 311707 calls (2.1347%). 6590 predicted-reference→actual-literal corrections, 64 predicted-literal→actual-reference corrections. Rates of predicted-reference→actual-literal by group: PDF 2309/10946, DOCX 407/18966, XLSX 81/4204, ZIP 665/3941, PNG 3128/5623. PNG accounts for 47.47% of this type of nonzero event and three files only. Strong heterogeneity; not enough to infer universal improvement.

## Next falsifiable research question
Before attempting a different predictor, attribute actual coding cost: capture per-category CABAC event sequence and measure a separately reproducible alternative entropy representation or controlled predictor ablation; compare actual serialized corrections under same plaintext, same exact reconstruction, same parameters overhead and CPU/memory. Frequency is not cost: frequent nonzero values can be cheap under CABAC; 8556 B total correction data against much larger full-file gap suggests limited room in this component alone on this panel, not a mathematical upper bound on whole-file savings. Possible experiment: match-vs-literal decision conditioned on length/distance/entropy features and inferred compression strategy, without target-token leakage; compare held-out families, pre-register gate, verify byte-exact reconstruction. If no meaningful advantage, abandon. No novelty assertion.

## Limitations
Reused H07b.2/H09 screening corpus, not independent. Detected subset only, caps as H09, no arbitrary DEFLATE guarantee, no per-category bit attribution, no official full-container preflate pipeline, no uninstrumented-output equivalence test, no repeated measurements/RSS/fuzzing. No direct performance claim. Main unchanged. No production GO.

## Reproduction
Download and verify the pinned crate; extract, copy h10_driver.rs, apply h10_instrument.py from its root, use the published lock and cargo build --release --locked --bin h10-driver --target-dir <temporary-dir>. Copy resulting executable into lab experiments/h10/h10-driver. Then:
```bash
source ~/sedravarch-lab/bin/env.sh
cd ~/sedravarch-lab
python experiments/h10/h10_audit.py --lab "$PWD" --out results/h10-reproduction.jsonl
```
Requires H07b.2 detector and prior JSONL (hash verified). Record build environment and compare input/output hashes.