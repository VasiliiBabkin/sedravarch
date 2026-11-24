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
