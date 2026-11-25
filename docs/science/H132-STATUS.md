# H13.2 — статус: VDS BLOCKED, локальная проверка PASS

**Основной эксперимент НЕ запущен.** Критерии A/B не проверены, никакого вывода об эффективности нового алгоритма или устойчивости скоростей на VDS нет. H13.1 остаётся последним завершённым основным экспериментом (6295 проверок суммарно). Локальные smoke-проверки не прибавляются к этому счётчику.

## Инфраструктурный блокер
Gateway на popizdim-ru (srv_01M7WZV88J00SQG3B285ZE9VHJ) не смог создать рабочий каталог задания: `mkdir: cannot create directory ...: No space left on device`. Начальная проверка окружения job_01M88DQ97T001R2DS2EJPFVX7K; типизированная read-only storage.usage job_01M88DQJFZ00TX7WPBREDXC3WJ завершилась той же ошибкой; повторный df/df -i job_01M88DVW9E00TRDGWSJEMT1JK9 завершился status 125. Поэтому текущие bytes/inodes не установлены. Последние 13 GiB свободного места относились к H13.1 и не являются текущим измерением. Ничего на VDS не удалялось и не изменялось, другие проекты не затронуты.

## Подготовка
- [Протокол до тестов](H132-PROTOCOL.md), commit cfd0342e3f95dcd49d8cae5aa735a358588e0757.
- [Калибровочный стенд](../../research/science/h132_calibrate.py), initial commit c85e3bac6718187b5ecc824a24819b5c9789977b; corrected commit 95e98202abf828d65d44563141e73bfac7e0725e.
- Final source blob SHA-1 007da5a82dc42f62736aea55d850a9e2adcc561a; verified by local git hash-object, SHA-256 af97553b4daea05c886b70ac23d22d650aea4ea0e62498132942030ad72d2eed.
- Correction before main trial: release ctypes pointer reference to previous output buffer before next allocation, treat inaccessible CPU frequency as optional. No gate/data/profile changes. Python ctypes instead of H13.1 C++ harness; small FFI overhead and Python worker RSS included; no direct RSS comparability to previous experiment.

## Local smoke (NOT VDS)
Initial extracted worker 24/24 passed; after correction complete script smoke invoked in container. First complete-script invocation interrupted by 30s local tool limit after 9 pairs; restarted with separate output, 12/12 pairs passed, **24/24 measured exact decodes** (one warmup, two measured calls per pair). Only final complete smoke reported below. Same synthetic 1124288 B (524288 B deterministic random plus repeated string, seed 20261125), SHA256 70d66757c5a350d1d6f3ef24f6d0b8a7919989b246e0178cfeca4c25a38262ed. All repeated encoded bytes and cross-mode archive hashes identical, decoder checked every reconstructed byte. GNU time RSS and wall/CPU collection executed; temporary input/archives removed in local container. Python 3.13.5, liblz4 1.10.0, libzstd 1.5.7, libdeflate 1.23, zlib 1.3.1 packages differ from VDS. No comparison of timing/RSS or compression efficacy.

| Profile | Archive bytes, prealloc = alloc | Measured decodes |
|---|---:|---:|
| LZ4 acceleration1 | 530640 | 4/4 |
| Zstd3 | 524396 | 4/4 |
| Zstd6 | 524392 | 4/4 |
| Zstd9 | 524821 | 4/4 |
| Zstd12 | 524821 | 4/4 |
| libdeflate6 | 526036 | 4/4 |

Raw local smoke JSONL H132-local-smoke-complete.jsonl SHA256 3470bc53f594435d501b12a540b08edf336f12f91575528d08a874de061b5827, 10577 B, supplied separately in conversation. Local timing and RSS are only instrumentation checks. Full real corpus/reference branches and aggregation gates not executed. No claim of main gate pass or fail.

## Run after restoring VDS capacity
First inspect bytes and inodes (df -hT /; df -i /), identify growth before deletion. Maintain >=5 GiB free and >=1 GiB MemAvailable as registered. No blind cleanup of production sites, databases or unrelated build caches. Copy the pinned corrected source into lab experiments/h132/h132_calibrate.py and run:
```bash
source ~/sedravarch-lab/bin/env.sh
cd ~/sedravarch-lab
python experiments/h132/h132_calibrate.py --lab "$PWD" --out results/h132-20261125.jsonl
```
Use sufficiently bounded job duration (e.g. <=900 s), watch progress, preserve partial if interrupted. 344 planned exact decodes/checks incl references. Failures must be recorded, missing measurements cannot count as completed. No algorithm development before the registered calibration gate is evaluated. Production unchanged.
