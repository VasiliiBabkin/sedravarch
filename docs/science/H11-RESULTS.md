# H11 — информационная стоимость поправок preflate

**Решение:** H11a отклонена: разреженные полосы проиграли оригинальному CABAC на каждом потоке. H11b прошла предварительный критерий log loss: смесь уменьшила суммарные потери на 6.04% и улучшила три из пяти панелей. Это основание для отдельного эксперимента реального кодирования, не доказательство преимущества над CABAC. Production NO-GO.

## Воспроизводимость
- [Протокол](H11-PROTOCOL.md), commit 4685e72a8f52a5a2672d31a653c3b51956ffa99f.
- [Инструментирование](../../research/science/h11_instrument.py), commit 87fba5182512a288539dc837ddb780367bb0cc45.
- [Rust driver](../../research/science/h11_driver.rs), commit 28bd26d9bb375094118ba99af1ebe194430e0c0b.
- [Python audit](../../research/science/h11_audit.py), commit 1f3f4a2bdb14bf3ce3621bcc15bf84e034bb565e.
- [JSONL](results/H11-20261124.jsonl), commit fd71bd90abf39459a506083ba22fda1727bd340b.
- Crate preflate-rs 0.7.6 SHA-256 1a2e9d0ac8c6cd9bb134681e11b5a32c7c56b89c5958cf785775080def38537c, неизменённый [Cargo.lock H10](../../research/science/h10-Cargo.lock), SHA-256 8a07a28fb29f4284560156762d4990f1e6349635fac7fc118c11e71dadf60281.
- SHA-256 driver source 47997b7c086d3d7467cfb56297b6981bfdaddd13b8c39f098d6e1adcf0dd0441; instrumentation 6477d4ea8475dc239e67916eaaaa81262c98b14ed180828e9454306a7d120455; Python 707a3cd1aeec2b260af11646025294508120580457345795b64e5e0d2a4aba80; executable 018133afec5b5a899c208e23b8826104e798d21c0a50001c9291f4ac14864a70; JSONL 7bde2d06bc6950665b54ed455db3b2cb1955d0b0b5285a3edd9e0c01dec9e94d.

Сборка cargo --release --locked успешно завершена. Один CPU affinity на этапе измерений, nice +10. Повторно скачаны 15 файлов; SHA-256 совпали с H07b.2, 140 потоков и счётчики всех категорий совпали с H10. Для каждого потока оригинальный CABAC payload, повторно сформированный из записанной последовательности событий, совпал побайтово с payload в instrumented baseline. Три альтернативы декодированы через отдельную реализацию PredictionDecoder, проверено исчерпание всех полос, восстановлены исходные raw DEFLATE bytes. 560 проверок (140 baseline + 420 альтернативных), 140 дополнительных сверок replay; не считать их независимыми наблюдениями. Полные файлы в H11 не перепаковывались. Временные build/cache/input каталоги очищены, tmp содержит только benchmark.lock; 13 GiB свободно. 

## H11a: фактические размеры
В байтах, только данные реконструкции (plaintext общий для всех). Original — полная bitcode ReconstructionData. A/B/C включают собственную рамку и исходные параметры в виде bitcode blob с пустым correction vec. Oracle — per-stream min(A,B,C), не единый реализованный селектор.

| Format | Streams | Original | CABAC payload | A sparse | B zlib | C XZ | Oracle |
|---|---:|---:|---:|---:|---:|---:|---:|
| PDF | 16 | 1934 | 1508 | 5911 | 2733 | 3537 | 2709 |
| DOCX | 74 | 3145 | 1136 | 6440 | 6175 | 10267 | 6166 |
| XLSX | 38 | 1550 | 531 | 3274 | 3163 | 5268 | 3160 |
| ZIP | 9 | 1268 | 1014 | 3126 | 1880 | 2407 | 1880 |
| PNG | 3 | 659 | 577 | 6501 | 1107 | 1239 | 1107 |
| Total | 140 | 8556 | 4766 | 25252 | 15058 | 22718 | 15022 |

Oracle +75.5727% vs Original; 0/140 strict wins. Gate required <=95% and >=70 wins; failed. Sum parameter-only blobs 3646 B; Original minus CABAC = 3790 B (including serialization overhead, not independent additive parameter length). Alternative overhead includes 5 B/frame and 17 lane counts + nonzero counts, even for zero-only lanes. This is a comparison of the specified representation, not a proof that all sparse coding fails.

## Изолированная стоимость CABAC
Оригинальный общий CABAC payload 4766 B. Replaying one category at a time with fresh CABAC contexts gives the following independently serialized sizes across streams. Total 5180 B, NOT an additive decomposition of 4766 B; common flags, ordering and termination differ. Encoder may emit zero bytes for some isolated all-default traces; do not interpret that as zero marginal contribution in combined stream.

| Category | Calls | Nonzero | Isolated bytes | Empirical within-stream H0 bits |
|---|---:|---:|---:|---:|
| ReferencePredictionWrong | 43680 | 6590 | 3067 | 16839.81 |
| LenCorrection | 37154 | 703 | 1022 | 4693.21 |
| TokenCount | 214 | 69 | 284 | 145.16 |
| UncompressBlockLenCorrection | 45 | 45 | 270 | 0 |
| EndOfChunk | 259 | 108 | 162 | 150.86 |
| BlockTypeCorrection | 259 | 96 | 148 | 219.58 |
| Last | 259 | 108 | 109 | 150.86 |
| LiteralPredictionWrong | 268027 | 64 | 106 | 589.23 |
| DistOnlyCorrection | 36451 | 1 | 6 | 7.66 |
| RepeatCountCorrection | 1894 | 1 | 4 | 4.69 |
| DistAfterLenCorrection | 703 | 1 | 2 | 0 |
| Other 6 categories | — | 0 | 0 | 0 |

ReferencePredictionWrong is the largest isolated encoded category; length correction is second. These are direct isolated measurements, not exact bit attribution. Plug-in zero-order entropy of observed category values within each stream is in-sample, excludes parameter cost and does not model sequential dependencies; it is not a bound on arithmetic-coded payload. Event counts are not independent.

## H11b: prequential probability screen
All 43680 predicted-reference decisions. Observed label = actual literal (1) / reference (0). KT models initialized at each stream, update only after observing label; features predicted length/distance are available to original decoder before this decision. Mixture is average of constant and joint model probabilities each event, not Bayesian sequence mixture. Loss in bits (lower is better).

| Format | Constant | Length | Distance | Joint | Mixture | Mixture gain |
|---|---:|---:|---:|---:|---:|---:|
| PDF | 7876.35 | 7521.70 | 7838.62 | 7585.47 | 7567.03 | 3.93% |
| DOCX | 2480.25 | 2907.25 | 2781.01 | 4078.23 | 2998.16 | -20.88% |
| XLSX | 537.75 | 837.16 | 701.94 | 1265.29 | 825.99 | -53.60% |
| ZIP | 2441.60 | 2169.52 | 2246.51 | 2099.61 | 2095.26 | 14.18% |
| PNG | 4033.73 | 2038.80 | 3989.43 | 2113.35 | 2834.35 | 29.73% |
| Total | 17369.67 | 15474.43 | 17557.50 | 17141.96 | 16320.80 | 6.04% |

H11b gate (>=5% total and improvement >=3/5 formats) passed. Absolute reduction vs constant KT = 1048.8784 bits (~131.11 bytes) over all streams, **diagnostic only**. Length alone achieved 10.91% total reduction, better than preregistered mixture, but is exploratory comparative observation; no change to primary gate. Distance alone worsens aggregate by 1.08%. Conditional model heterogeneity: DOCX and XLSX worsen substantially; PNG improvement contributes disproportionately, only three streams. No independent holdout and no direct comparison of these log losses with original CABAC coded size. The original uses zero-run and magnitude contexts, not constant Bernoulli KT; do not translate diagnostic 6.04% into claimed archive saving. 

## Next falsifiable test (H12 proposal)
Replace only the ReferencePredictionWrong entropy channel, keeping exact preflate predictor and other correction channels unchanged. Compare actual complete ReconstructionData sizes with original CABAC, including selection/mode signaling, parameters and stream termination; also compare complete transformed files against strong controls. Test on new independent families, include original H11 diagnostic panel separately; pre-register model variants and gate. Verify all reconstructed DEFLATE and complete files, quantify encode/decode cost and memory. A small reduction in log loss against KT may not justify a separate channel; if it fails, reject. Do not claim novel compression or integrate based on H11. 

## Limitations
Same detected bounded streams as H10/H09, one run; no independent corpus, no official full-file preflate pipeline, no measured per-category marginal bit cost, no independent strategy effect, no RSS/timing comparison, no fuzzing. The statistical screen holds estimated original compressor parameters fixed, does not evaluate correlation with compressor strategy directly. Alternative decoder intended only for trusted lab data. Instrumentation retains original prediction and replay verifies the captured original CABAC payload; no separate uninstrumented binary comparison. Main unchanged. 

## Reproduction
Obtain pinned crate and verify SHA-256, extract, copy h11_driver.rs and apply h11_instrument.py in crate root. Verify Cargo.lock against H10. Build cargo build --release --locked --bin h11-driver --target-dir <temporary-dir>; locate executable from Cargo output and install in lab experiments/h11/h11-driver. Run:
```bash
source ~/sedravarch-lab/bin/env.sh
cd ~/sedravarch-lab
python experiments/h11/h11_audit.py --lab "$PWD" --out results/h11-reproduction.jsonl
```
Requires prior H07b.2 and H10 JSONL and unchanged detector, all checked by script. New output path; source/input hashes must match.
