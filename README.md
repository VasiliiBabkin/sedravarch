# SedravArch

Experimental lossless compression engine and single-file archival container written in Rust.
No third-party compression libraries or runtime dependencies.

## Build and use

```sh
cargo build --release
cargo test
target/release/sedravarch pack input.bin output.sda
target/release/sedravarch test output.sda
target/release/sedravarch unpack output.sda restored.bin
cmp input.bin restored.bin
```

The decoder limits output to 8 GiB by default. Supply a different maximum byte count as the last argument to unpack or test. Existing output files are never overwritten. On an ordinary reported error, the CLI attempts to remove its incomplete output.

## Prototype 0.1

Each 64 KiB block is independently encoded with the smallest of raw, RLE, LZ-style back-references, byte-delta + RLE, and byte-delta + LZ. CRC32 detects accidental corruption. Streaming I/O and bounded block sizes limit memory usage. CRC32 is not cryptographic authentication.

This is a research baseline, not a claim of algorithmic novelty or superiority over existing codecs. The current container holds one byte stream, not a directory tree. No encryption, entropy coder, cross-file deduplication or parallel compression yet. Do not rely on it for sole copies of important data. Format compatibility is not guaranteed during 0.x development.

See [format specification](docs/format.md). Next research: entropy coding, content-defined chunking, cross-block similarity and dependency selection under explicit decoding budgets, then multi-file archive indexing.
