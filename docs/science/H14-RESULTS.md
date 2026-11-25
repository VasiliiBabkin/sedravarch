# H14 — результаты ограниченного LZ-парсинга и представления команд

**Решение: H14 отклонена.** Раздельное представление улучшает собственный interleaved baseline, но ни на одном реальном файле не превосходит сильный прямой контроль. Не интегрировать исследованные представления. Не заявлять новизну: разделение литералов, последовательностей и повторных расстояний известно, в частности, из RFC 8878.

## Воспроизводимость
- [Протокол](H14-PROTOCOL.md), commit ec70f2b6cd03ef8bccbde6e29217e77d11c71eaa.
- [Код](../../research/science/h14_bounded_lz.py), первоначальный commit dfe00201cf8b14ca9ccec0ef077836f2846e39e7, исправленный commit 26501d9112b1273b078e23487f3935847146275a.
- [JSONL](results/H14-20261125.jsonl), commit b4d49e77433b4e214a6093543c8bf3e9e3d1a7b5.
- SHA256 исправленного скрипта 6e17c43d344a63aafecbb63f063cebf1109fedde5a18590953b75179727ab404, JSONL c99728c86316e91170c8cf766aee31a138fcedc480c72649778faa5b3b85493e (24319 B, 25 lines).
- Zstd library 1.5.5 SHA256 0a2128bc10841fb29e76d08d945864dfb0b6a66da5df6df5d8299197439e54bb; CPU0, nice+10, lab lock, RLIMIT_AS2GiB.
- Первоначальный job job_01M89TF1NV0008ND2AE9VFDFY3 остановился до первого sample: ctypes не принимал bytearray при вызове ZSTD_decompress. Исправлена только конвертация в bytes, проверено наличие единственной metadata-строки в первом JSONL. Второй job job_01M89TG4QZ00JG8GQHC1MZAA38 успешно завершён на отдельном output. Протокол и параметры не менялись.
- 19 файлов, 7 представлений каждого, 133/133 точных восстановлений. 12 реальных, 7 synthetic; 6 Silesia окон по 524288 B и 6 локальных файлов/окон. Хеши исходников/окон и архивов в JSONL. Повторно использованы семейства Silesia; локальные файлы не являются blind holdout. Никакого исполнения исследуемых ELF. Временный каталог лаборатории содержит только benchmark.lock, 12 GiB свободно.

## Полный размер архивов
A = interleaved; B = split runs/lengths/distances/literals; C = split + 4-entry MTF distance cache with escapes; D = direct block Zstd3. A/B/C use identical greedy parse, same block limit 262144, max distance65535, min match4/max258, last4 exact-key candidate positions. A/B/C/D use identical experimental framing and backend Zstd3. Direct Zstd6/9 and XZ5 whole-input codec formats deliberately omit experimental frame.

| Group | Input | A | B | C | D | Zstd6 | Zstd9 | XZ5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Silesia | 3145728 | 1420337 | 1326420 | 1328737 | 1216620 | 1134647 | 1124553 | 957672 |
| Local | 1926862 | 922206 | 883556 | 884710 | 824391 | 795394 | 789738 | 683684 |
| Real | 5072590 | 2342543 | 2209976 | 2213447 | 2041011 | 1930041 | 1914291 | 1641356 |
| Synthetic | 1310811 | 721790 | 721247 | 721233 | 718994 | 718835 | 718128 | 568932 |

B reduces A by 6.6123%/4.1910% (Silesia/local), 5.6591% combined. C reduces A by 6.4492%/4.0659%, 5.5109% combined; C is 0.1571% larger than B combined (only 3/12 wins vs B). C is 9.2154%/7.3168% larger than matched framing D, 8.4486% combined. Per-file min of direct Zstd6/9 = 1124553/789738, total 1914291 B; C is 18.1569%/12.0258% larger, 15.6275% combined, 0/12 wins. B is also larger than D on all real files. XZ5 is size-only reference, not work-matched. No direct proof of which difference in parsing, coding and framing explains the gap against whole-input Zstd.

## Decoder work and distance cache
Real panel: 497076 matches, 4019990 match bytes (79.2493% of input), 1052600 literal bytes, 497098 literal runs including final runs, 513520 actual overlap-safe copy slices. Mean match length 8.0873 bytes. All three decoders verified identical counts for every block. In specified doubling-copy implementation, copy slices per 100 output bytes = 9.9498/10.4069, both under registered 25 cap. Total 10.1234/100. This is an implementation-specific logical work proxy, not instruction count, throughput, total memory traffic or total decoder work. Backend Zstd decompression, bytearray allocation/copy overhead, metadata parsing and CRC not included in that metric. Source reads and writes of logical LZ stage each N bytes (excluding metadata); actual memory accesses not measured. Max distance65534, max serialized C block272100 B (bound 2*block_len+64). These are format bounds, not measured RSS.

Uncompressed lane sums across real files:
- B: run lengths 497326 B; match lengths 497076 B; offsets 994152 B; literals 1052600 B.
- C: run lengths 497326 B; match lengths 497076 B; cache symbols 497076 B; escaped offsets 914022 B; literals 1052600 B.
- 457011 misses (914022/2), 40065 hits; hit fraction 8.0601%. Fixed one-byte rank plus u16 escape costs more before backend than plain u16 offsets. Outer Zstd absorbs most difference, but C still worse in aggregate. Cache hit fraction is measured for this parser and MTF rule; not a claim that repeated-offset coding generally fails. Zstandard already uses other repeated-offset semantics and entropy-coded sequence representation (RFC 8878).
- Serialized inner totals A/B/C 3041242/3041594/3458628 B, before backend and outer framing. A vs B same parse and almost same pre-backend size, so the B reduction after Zstd reflects layout effects in this particular backend, not a new compression principle.

## Gate
Required C <=95% A and <=95% per-file direct Zstd6/9 oracle in EACH real panel, >=6/12 direct wins, copy slices <=N/4 each. Work criterion passed; local C/A fails; both C/direct and win count fail. Gate=false. Reject specific representation; no production GO. Do not lower thresholds or combine rejected prototypes.

## Limitations and next step
One run, no timing or RSS measurement by design; no direct resource-matched Zstd control for logical work counts, no fuzzing; Python decoder for trusted bounded research input only. Local files and reused Silesia not independent representative validation. Compression speed, decompression speed and practical latency advantage not established. Raw fallback not included by protocol; cannot infer adaptive selection gains. 
Proposed H15: before building another compressor, use identical-token cost diagnostics and independently compare *parse quality* rather than serialization alone. Consider a bounded-cost shortest-path parse against greedy, using real coded output with strong native Zstd controls. Optimal LZ parsing is prior art; examine the known literature and quantify remaining opportunity rather than claim novelty. If no meaningful improvement, close this direction as well. 
## Reproduction
```bash
source ~/sedravarch-lab/bin/env.sh
cd ~/sedravarch-lab
python experiments/h14/h14_bounded_lz.py --lab "$PWD" --out results/h14-reproduction.jsonl
```
Verify manifest, local file and library hashes. Use new output path. No main changes.
