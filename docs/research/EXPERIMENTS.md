# Experiments and audit

## Baseline audit

Baseline is SedravArch 0.7 at `05a1c26662a15b10ce60cc56d568fb410051cfe0`. The stable stream has raw, RLE, Smart LZ, byte delta, Huffman wrapping, Gear chunking and bounded backward references. Its archive layer independently compresses named files and validates its index and metadata. The GUI branch is separate. Its status notes include user-reported Windows examples whose original input bytes were unavailable for verification here. Earlier VDS measurements include a corrected RSS measurement in the 0.7 report. We reran the baseline in the shared execution environment with the same inputs and measurement method as the SADM comparison. [Archive formats](../format.md) · [Historical 0.7 report](../benchmarks/2026-11-24-v07.md)

Existing scripts cover earlier comparisons, chunking, archive integration and profiling. The pilot reuses the native `wait4` measurement launcher. Baseline verification produced 45 passing Rust unit tests and 27 passing Python integration checks. The SADM checks cover rANS endpoints, property-style generated roundtrips and determinism, malformed records with recalculated CRC, truncations, reference depth and a deterministic 20,000-case mutation campaign that attempts archive, entropy and delta decoders. The mutation campaign is bounded and in-process.

## Data and protocol

Single-file inputs are all 11 standard Canterbury files and all 12 Silesia members, each packed separately. Extra cases include the baseline source tar, SQLite rows created by the script, strided integer values, fixed-seed pseudorandom bytes, the local Git ELF and its XZ encoding. Structure probes include a PE, ELF, PDF, PNG and DOCX. The family comparison intentionally keeps duplicate and related versions in the same test family. It measures true ordinal extraction for SADM, named extraction for stable SedravArch and solid/non-solid 7-Zip. These formats have different metadata costs.

No model is trained across files for the single-file comparison. Parameters were fixed in code and smoke-tested on generated data. These are exploratory results. There is no preregistered, independently held-out collection of real version families, and the local ELF and its XZ derivative stay in the same suite. The input ledger includes byte counts and SHA-256 hashes. The selected external codec settings are one point per tool, with one encode thread where configurable. The time and RSS measurements include process startup, file I/O and archive parsing. Each decoded output is compared byte for byte outside the measured interval. No target executable is launched. Disk cache state was not controlled, and the shared environment was not isolated from other load.

## Reproduction

Run from the repository root with Rust 1.100, Python 3.12+, a Linux C compiler and `7zz`, `zstd`, `lz4`, `brotli`, `gzip` and `xz` available. The corpus mirrors and pinned revisions below are recorded in the result ledger. Extract only the requested corpus members in your own scratch directory.

```sh
cargo test
cargo build --release
python3 scripts/test_archive.py target/release/sedravarch
cargo test --locked --manifest-path research/sadm/Cargo.toml
cargo build --locked --release --manifest-path research/sadm/Cargo.toml

scratch=$(mktemp -d)
git clone https://github.com/pfalcon/canterbury-corpus "$scratch/canterbury"
git -C "$scratch/canterbury" checkout c380ef9dc1dc62691757fdfeebdc2f85710e1e46
git clone https://github.com/jungwonkim/silesia "$scratch/silesia"
git -C "$scratch/silesia" checkout 85596ee9d0a95526603086abadf126c08e07ef8a
mkdir "$scratch/silesia-data"
unzip -p "$scratch/silesia/silesia_tar.zip" silesia.tar | tar -x -C "$scratch/silesia-data"
python3 research/sadm/scripts/bench.py \
  --canterbury "$scratch/canterbury/canterbury" --silesia "$scratch/silesia-data" \
  --out "$scratch/pilot.json"
python3 research/sadm/scripts/summarize.py "$scratch/pilot.json" > "$scratch/summary.json"
```

The test for the mathematical model is the serialized byte count, including checksums, record and file headers, rANS tables and scripts. The numbers in the structural ledger contain complete archives for both engines, plus standalone BCJ/XZ and DEFLATE probes. Reproduce them with `structure.py --out RESULTS LABEL:KIND:PATH ...` using the input paths and fingerprints from that ledger. Matching DEFLATE levels require equality over the entire original compressed stream.

The full pilot uses SADM commit `beac3ad258f4f0cfaf6b2b5e95d5eaf73d11786c`. To reproduce its timings after the rANS optimization, add a detached worktree for that commit, build its research package in release mode and pass the resulting executable through `--sadm`. The optimizer comparison interleaves the two executables in alternating order and checks bytes of both archived and decoded data on each run.

### Structural controls

The PE inputs are the distlib x64 launcher and a copy compressed with UPX 5.0.2. Prepare the latter with `upx -o packed-w64.exe w64.exe`. The commands do not execute either PE file. The BCJ probe uses liblzma's X86 filter before LZMA2 at preset 6 and checks full XZ round trips. The u32 probe transposes byte lanes of the same integer sequence used in the benchmark and includes a byte for the transform selector on each compared path. The diagnostic PNG/ZIP scanner imposes per-input, per-stream and aggregate ZIP limits. It never writes ZIP member paths to disk.

For the preflate comparison, use a new scratch checkout of Microsoft preflate-rs at `e97efb0031ff67e5c8f0154726422e31f6ed8424`. Copy `research/sadm/scripts/preflate_probe.rs` to `util/examples/` in that checkout and build it with `cargo build --locked --release -p preflate_util --example preflate_probe`. Pass its binary via `--preflate` and the pinned revision via `--preflate-revision`. It verifies byte equality on the entire file and reports full serialized container size. The reference is direct Zstandard at level 9. The zlib positive control is a ZIP file whose sole member is named `control`, timestamped 2000-01-01, and contains the bytes of `b"control data " * 700` written with zlib level 6.

For the recorded full pilot, also pass `--legacy-policy` when using its old SADM executable. The current release defaults to fixed blocks. The selected-profile rerun at `02513be05c5f97418f8845c69c14e95f4df63985` uses `--sadm-only` to rerun SADM against the same corpora; external comparisons are drawn from the pilot. The native launcher and selection measurements are unchanged.

The second version family contains `deflate.c` from tagged zlib releases v1.2.13, v1.3 and v1.3.1. Obtain those files from the upstream tags, name them `v0-deflate-1.2.13.c`, `v1-deflate-1.3.c` and `v2-deflate-1.3.1.c`, and pass their directory with `--only-family --family-directory DIRECTORY`. The recorded family uses the post-optimization executable at `0affe624389a742604a89cec49b7b313b6b677f9` with the pilot policy and corresponding `--legacy-policy` switch. These three revisions form a single evaluation group. [zlib upstream repository](https://github.com/madler/zlib)
