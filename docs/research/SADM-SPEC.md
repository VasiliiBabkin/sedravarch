# SADM v1

SADM is a self-contained Rust research package. This version stores ordered byte strings addressed by zero-based ordinal. Applications keep names and filesystem metadata out of band. The stable SedravArch package continues to use its own format.

## Wire format

All integers use little-endian byte order. The first eight bytes are `53 41 44 4d 01 0d 0a 00`. A u32 file count follows. Each file has a u32 decoded length and a u32 block count, followed by its block records. An empty file has zero blocks. The final u32 is CRC-32/ISO-HDLC over all preceding archive bytes. EOF follows immediately.

Each block has a 15-byte header.

| Field | Type |
|---|---|
| Codec | u8 |
| Decoded length | u16 |
| Payload length | u32 |
| Global base block ordinal | u32 |
| Decoded block CRC-32/ISO-HDLC | u32 |

Payload bytes follow each header. Independent records set base to `0xffffffff`. All other bases belong to earlier files. All block lengths are in 1..16384. Nonfinal lengths are multiples of 4096. Payload length is at most decoded length. The parser checks exact extents, cumulative length, codec validity, depth, references and archive CRC at open.

| Codec | Payload |
|---|---|
| 0 | Raw bytes, length equals decoded length |
| 1 | Order-0 byte rANS |
| 2 | Empty, copies an equal-length base |
| 3 | Copy/add script using the named base |
| 4–7 | Order-0 byte rANS after modulo-256 subtraction at lag 1, 2, 4 or 8 |

A copy/add script uses operation 0 followed by a u16 length and literal bytes, or operation 1 followed by u16 base offset and u16 length. Copies may visit base regions in any order. All operation lengths are positive. The script exhausts its payload and yields exactly the declared output length. In a prediction block the first lag bytes are unchanged. The inverse adds earlier reconstructed bytes modulo 256.

An rANS payload begins with a u8 precision `R ∈ {8,10,12}`, a u16 alphabet size and that many `(u8 symbol, u16 frequency)` entries in increasing symbol order. Frequencies are positive and sum to `2^R`. Cumulative start offsets derive from table order. A u32 initial decoder state and renormalization bytes follow. Put `L = 2^23`. Initial state lies in `[L,256L)`. For slot `s = x mod 2^R` with frequency `f` and start `c`, emit its symbol and compute `x = f floor(x/2^R) + s − c`. While `x < L`, shift by eight and append the next byte. After the declared number of symbols the decoder requires state `L` and payload exhaustion. The inverse emits low bytes before each update while `x ≥ 256(L/2^R)f` and inserts symbols in reverse order. The stored bytes are consumed forward.

The encoder normalizes frequencies by allocating one unit per observed symbol, then dividing remaining mass in proportion to observed counts. The largest fractional remainders get residual units, with ascending symbol as tie-break. Every candidate precision incurs full model cost. Equal payload sizes retain the first candidate.

## Limits and commands

At most 1024 files, 64 MiB decoded total, 68 MiB archive input and three reference edges per block. One selected block visits at most four blocks and expands at most 64 KiB of decoded block data including ancestors. Parent validation and CRC checks apply during extraction. Archive opening reads and checks the full encoded byte stream. CRC detects ordinary corruption and is unkeyed.

```sh
cargo build --release --manifest-path research/sadm/Cargo.toml
sadm encode experiment.sadm input0 input1
sadm stats experiment.sadm
sadm verify experiment.sadm
sadm extract experiment.sadm 1 restored
sadm encode one.sadm input0
sadm decode one.sadm restored-single
sadm analyze input0
```

The CLI creates new output paths exclusively. A failed write or verification during extraction removes the new output when possible. Library consumers must discard partial output on extraction error. Experimental versions may change the wire format.
