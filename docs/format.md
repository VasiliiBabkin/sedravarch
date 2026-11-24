# Experimental format v1

All integers are unsigned little endian. Header: eight bytes 53 44 41 52 43 48 01 00 (SDARCH, version 1, reserved zero).

Each record starts with a codec byte. 255 terminates the stream and must be followed by EOF. Otherwise the record contains decoded length (u32), payload length (u32), CRC32/ISO-HDLC of the original decoded bytes (u32), then payload. Decoded length is 1..65536, payload length is 1..decoded length.

Codecs: 0 raw (equal lengths), 1 RLE, 2 LZ, 3 delta + RLE, 4 delta + LZ. RLE is a sequence of nonzero u8 count and u8 value pairs. LZ tokens 0..127 are followed by token+1 literal bytes; tokens 128..255 encode (token & 127)+3 bytes copied from the prior output at a following u16 nonzero backward distance. Overlapping copies are permitted. Delta is modulo 256 subtraction from the previous original byte, initially zero; reverse by cumulative addition. Each block resets the dictionary and delta state.

The decoder rejects invalid lengths, distances, tags, checksums, missing terminators and trailing data, and enforces a caller-provided total output budget. There is no global integrity digest: deletion or reordering of valid blocks is not detected by per-block CRC alone.
