# SedravArch

Experimental lossless compression engine and indexed multi-file archival container written in Rust.
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

## Prototype 0.6

Each block (32–64 KiB, except the final block) is independently encoded with the smallest of raw, RLE, LZ-style back-references, byte-delta + RLE, and byte-delta + LZ. Two Smart LZ candidates use bounded hash-chain search, lazy parsing and matches up to 65,535 bytes. A native Huffman stage can encode any of the seven base candidates. Block and whole-stream CRC32 plus final counts detect accidental corruption, missing and reordered blocks. The decoder reads formats v1 through v4. Default Gear content-defined chunking resynchronizes boundaries after edits in many inputs. Use pack-fixed for the previous fixed 64 KiB policy. Default format v4 adds backward exact and sparse replacement dependencies within the last 128 blocks (at most 8 MiB of retained raw data), with maximum dependency depth 4. Equal-length candidates are sampled at 64 positions, up to three are patched, and independent encoding remains a fallback. Use pack-independent to emit compatible v3 streams with adaptive chunking. Streaming I/O and bounded block sizes limit memory usage. CRC32 is not cryptographic authentication.

This is a research baseline, not a claim of algorithmic novelty or superiority over existing codecs. Multi-file archives support regular files, directories (including empty directories), UTF-8 paths, sizes and informational modification timestamps. Each file is an independent v4 stream for direct extraction; no cross-file deduplication yet. No encryption, unbounded deduplication or parallel compression yet. Do not rely on it for sole copies of important data. Format compatibility is not guaranteed during 0.x development.

See [format specification](docs/format.md). Next research: performance, solid groups with cross-file deduplication, shifted-block similarity, and cost/speed optimization.

## Multi-file commands

```sh
sedravarch create backup.sda project/ notes.txt
sedravarch list backup.sda
sedravarch test backup.sda
sedravarch extract backup.sda new-directory
sedravarch extract-file backup.sda project/README.md restored.md
```

Extraction requires a new directory or new output file; existing paths are not overwritten. Only regular files and directories are archived; symlinks and special files are rejected. UTF-8 portable names only; absolute paths, traversal, reserved Windows names, case collisions and duplicate names are rejected. Index is limited to 16 MiB, 100000 entries, 64 path components and 4096 path bytes. Extraction defaults to 8 GiB output limit; optional final MAX_BYTES overrides it. Timestamps are listed (Unix seconds), not restored; permissions, ownership, xattrs, hard links and symlinks are not preserved. Use a trusted destination parent and no concurrent changes to source/destination. This is not a race-hardened sandbox. The legacy single-stream commands remain unchanged. Listing validates index metadata, not file payloads; test checks all streams.
