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

## Prototype 0.4

Each block (32–64 KiB, except the final block) is independently encoded with the smallest of raw, RLE, LZ-style back-references, byte-delta + RLE, and byte-delta + LZ. Two Smart LZ candidates use bounded hash-chain search, lazy parsing and matches up to 65,535 bytes. A native Huffman stage can encode any of the seven base candidates. Block and whole-stream CRC32 plus final counts detect accidental corruption, missing and reordered blocks. The decoder reads formats v1, v2 and v3. Default Gear content-defined chunking resynchronizes boundaries after edits in many inputs. Use pack-fixed for the previous fixed 64 KiB policy. The wire format remains v3; v0.3 can decode v0.4 output. Streaming I/O and bounded block sizes limit memory usage. CRC32 is not cryptographic authentication.

This is a research baseline, not a claim of algorithmic novelty or superiority over existing codecs. The current container holds one byte stream, not a directory tree. No encryption, cross-file deduplication or parallel compression yet. Do not rely on it for sole copies of important data. Format compatibility is not guaranteed during 0.x development.

See [format specification](docs/format.md). Next research: cross-block similarity and dependency selection under explicit decoding budgets, then multi-file archive indexing.
