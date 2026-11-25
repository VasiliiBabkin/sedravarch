# P03.1 — extended integrity verification (2026-11-25)

Baseline: 82f1bbc683748c117ef6026f1569f9d1c2d00391.
Tested patch: d43f4156bafc3e5103b9e3a662cdaeb6469e36bd.
Linux VDS (kernel 6.8.0-151-generic), Rust 1.85.1, release binary SHA-256 0933a6473c5851eaaafaa32fe09e59620a0394f12630b3fa9070b717b6af245c. Offline Cargo build after temporary toolchain download.

## Defect and fix
The previous multi-file decoder accepted embedded v1 streams even though the outer format specifies v4. Two otherwise valid v1 blocks could be reordered with an unchanged index and valid per-block CRCs. Reproduced on the baseline: both orders passed test and extract-file produced the corresponding distinct bytes. Commit 3ac5a117a82c8f626055377b54b181bc3f9fe222 now requires an embedded v4 header. Standalone v1–v3 remain supported; list still validates only the index. Previously accepted out-of-spec containers with embedded legacy streams are now rejected.

## Results
| Category | Result |
|---|---:|
| Rust tests | 47/47 |
| Existing integration checks | 27/27 |
| P03 regression assertions | 1651 PASS |
| Valid tag fixtures | 16/16 |
| Targeted malformed interior rejections | 16/16 |
| Structured archive mutations | 1024 |
| Random payloads with structured headers | 1024 |
| Invalid index fixtures (valid index CRC) | 13/13 |
| Embedded legacy stream rejection operations | 9/9 |
| Injected ENOSPC write | 5/5 |
| Injected ENOSPC sync | 5/5 |
| SIGKILL before publication | 5/5 |

P03.1 campaign completed all 2117 enumerated scenarios. Four of the 2048 mutation cases were accepted by the decoder; acceptance is not automatically a defect. For mutated valid fixtures the decoded bytes must equal the original if accepted; for random payloads only the normal decoder integrity and resource conditions were enforced. No abnormal exit or failed assertion was observed. No claim of exhaustive coverage or proof of correctness.

The five operations are pack, unpack, create, extract-file and extract. The LD_PRELOAD shim applies only to staging paths within an isolated temporary test directory. ENOSPC write is injected after a 256-byte short write; sync failure is injected at fsync. SIGKILL is sent after a marker confirms blocked writing. The suite checks absence of a published target, original SHA-256 preservation and normal-error staging cleanup. Killed-process staging is expected and removed by the harness. No real disk was filled. Resource limits per decoder child: 256 MiB address space, 8 MiB file size, 4/5 s CPU soft/hard limit, 8 s wall timeout for normal cases, 2 MiB decoded-output limit. Seed 20261125.

Reproduction (Linux, C compiler available):
    cargo test --offline
    cargo build --release --offline
    python3 scripts/test_archive.py target/release/sedravarch
    python3 scripts/test_p03.py target/release/sedravarch
    python3 scripts/test_p031.py target/release/sedravarch

Raw final summary:
```json
{"accepted_mutations":4,"enospc_sync":5,"enospc_write":5,"index_mutations":13,"legacy_embedded_rejections":9,"random_payloads":1024,"sigkill":5,"structured_mutations":1024,"targeted_rejections":16,"valid_tag_fixtures":16}
```

VDS job job_01M8A5TBEE00PATEHZPFP0C25M succeeded (exit 0). Temporary workspace and toolchain removed (du -sh: 594M before cleanup). No server services or global packages changed. No GitHub Actions used.

Decision: P03.1 bounded Linux campaign PASS; conditional GO for further product work. Not a stable-release approval. Remaining: native Windows/macOS publication, real filesystem failure/power loss and directory durability, coverage-guided fuzzing, unsupported filesystem behavior, concurrent hostile path mutations. CRC is not authentication. No performance claim or main merge.
