# H04b.2 — результаты вероятностного предсказания

**Решение:** H04b.2a и H04b.2b не прошли предварительный отбор. Не реализовывать новый арифметический поток для этого меню, как предписано протоколом. Модель совпадений улучшает предсказания относительно собственной модели B; это не доказательство превосходства над существующими компрессорами.

## Воспроизводимость
- [Протокол до вычислений](H04B2-PROTOCOL.md), commit 06ba64839f47ad2586301aac2c1c080423c3772d.
- [C++ предиктор](../../research/science/h04b2_predict.cpp), commit bccfe0dccbc3461ad7d70e8d0b57d44a16a5d957.
- [Драйвер](../../research/science/h04b2_screen.py), commit 759e51337ba1339e9db5dc4c5de91e2be92763e0.
- [Полные измерения](results/H04B2-20261124.jsonl), commit f88bd8d4c37e9a514117618085485dfb08fbaa2a.
- SHA-256 C++: 9a5730e252dcb74e5d1dacbfad7c9b2fea7cf4f24711c81f62628e5a96030ad5.
- SHA-256 driver: eb20e1dd389283e83315c42fd009d28eddcb627b721fb71101db8925c1bad7b2.
- SHA-256 H04 source dependency: 9081b8cb8b30c1f4db03a7faaf1b76b0e4d07f999eff1088bd7898b2d0abdb80 (совпадает с H04).
- SHA-256 binary: 244c38762f07c77b4ee926243c4de96dee513e10396cdb96100f446de7009ad8.
- SHA-256 JSONL: fa98e10c9edd11b6222cfa9082e32cab04ddeda7547631cf7a619c632ccb1fa7.

VDS, g++ C++17 -O2, один CPU affinity, nice +10, 20/20 запланированных образцов, 80 измерений моделей, 60/60 проверок побайтового восстановления внешних контролей (XZ5, PPMd5, Zstd15). Собственный кодер не реализован, поэтому для собственных предсказаний нет roundtrip. ZPAQ отсутствовал в PATH и не измерен; это необязательный дополнительный контроль по протоколу. Временные каталоги удалены. 

## Результаты
Диагностические байты = ceil(loss_bits/8)+15 для каждого образца, затем суммирование. Это оценка, не действительный поток и не доказанная верхняя граница. Strong = сумма per-sample минимумов трёх внешних кодеров. Все указанные размеры в байтах.

| Панель | Образцов | Исходный размер | A | B | C | D | Strong |
|---|---:|---:|---:|---:|---:|---:|---:|
| Silesia | 12 | 786432 | 320176 | 304173 | 290169 | 293156 | 234721 |
| Local text/code | 4 | 213055 | 70605 | 66180 | 58419 | 61527 | 43658 |
| Local binary | 4 | 262144 | 124672 | 122534 | 119499 | 118535 | 93530 |

| Панель | B vs A loss saving | C vs B | D vs C | D vs A | D diagnostic size vs strong |
|---|---:|---:|---:|---:|---:|
| Silesia | 5.0010% | 4.6069% | -1.0299% | 8.4442% | +24.8955% |
| Local text/code | 6.2750% | 11.7364% | -5.3252% | 12.8697% | +40.9295% |
| Local binary | 1.7156% | 2.4774% | 0.8070% | 4.9240% | +26.7347% |

H04b.2a (>=10% gain on each panel) fails Silesia and binary. H04b.2b (>=5% size saving against strong on each panel) fails all three. Even best among B/C/D per panel loses to strong by 23.62%, 33.81%, 26.73%. No post-hoc change of main model or criteria.

## Ablations
B changes three things together (hash, capacity, added order 8); cannot isolate each effect. C adds only match predictor, reduces loss on all three panels; largest effect on local text/code. D changes only mixer weights by bit position; worsens Silesia and local text, improves local binary slightly. This refutes the assumption that finer mixer conditioning necessarily improves the studied model. It does not prove the cause (e.g. sample sparsity) without another experiment.
Model D match coverage: Silesia 60.62%, text 74.17%, binary 46.55%. Conditional observed prediction accuracy on covered bits: 96.31%, 97.03%, 95.42%. Coverage includes the first mismatching bit, then match is disabled for remaining bits of that byte. Accuracy is not a compression ratio; mismatch costs and mixer weights affect log loss.

## Limitations
First 64 KiB, local files and reused Silesia source families, not independent blind holdout; one run. Models use fixed hash tables, fixed-share linear probability mixture, match confidence 31/32, no CTW/PAQ equivalence. A implementation reused H04 Model but no new arithmetic stream. Timings are wall time of predictor construction and evaluation (not CPU as planned), no peak RSS; no actual codec performance claims. All external controls verified, but ZPAQ/PAQ not tested. Formats have different overheads. No novelty established. No changes to stable/main.

## Next direction
The screened context models are too weak to justify full codec engineering. A separate fundamental experiment may examine exact DEFLATE token reconstruction, not byte XOR: quantify the information cost of reproducing LZ77 choices, dynamic Huffman code lengths, block boundaries and padding, relative to established preflate. First isolate the feasible representation and strong control; do not start a full archive format without measurable potential. This is a research proposal, not an implemented result.
