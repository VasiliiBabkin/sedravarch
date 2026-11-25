# P03 integrity audit — 2026-11-25

Baseline: 05a1c26662a15b10ce60cc56d568fb410051cfe0 (0.7.0).
Patched and tested: 4796d64ced8748702b1f32e92118e9b73d330522.
Linux VDS; temporary Rust 1.85.1, offline Cargo tests/build after toolchain download.

| Check | Baseline | Patched |
|---|---:|---:|
| Rust unit tests | 45/45 | 47/47 |
| Release build | PASS | PASS |
| Existing archive integration suite | 27/27 | 27/27 |
| P03 regression assertions | not run | 1651 PASS |

P03 tests cover hand-built raw v1–v4 fixtures, empty streams, every truncated prefix of these fixtures, trailing bytes, CRC and output-budget failures, preservation of existing paths, dangling symlink on POSIX, 128 deterministic random corruption cases with bounded output and normal exits, Linux SIGKILL during blocked packing, and staged file/tree publication unit tests including injected error and concurrent destination creation. Counts are assertions, not distinct archives or independent security findings. Existing integration suite covers multi-file index validation, traversal, forged extents and decoded sizes, extraction rollback and random access.

Changes: staged file output, sync_all before no-replace hard-link publication; Linux full extraction stages a directory and uses renameat2(RENAME_NOREPLACE). No wire changes. See format.md for filesystem and trust requirements.

Decision: CONDITIONAL GO for further Linux engineering; no stable release or production security certification. Not independently tested on Windows/macOS, unsupported filesystems, power loss, full-tree SIGKILL, hostile concurrent namespace mutation, source-file snapshot consistency, or exhaustive fuzzing. CRC is not authentication; v1 has weaker completeness checks. Non-Linux full-tree extraction retains prior behavior. No performance claims. No main merge.

Both VDS jobs completed successfully (baseline job_01M8A2T32J00EZA68AVDN44RVH, patched job_01M8A300G700QFPH8ZFBFN1DYJ); temporary workspace including toolchain removed, measured size before cleanup 644 MiB (du -sh output 644M). No services or global packages changed. Next: cross-platform no-replace publication, interruption/ENOSPC tests, bounded fuzzing and explicit durability contract before stable release.
