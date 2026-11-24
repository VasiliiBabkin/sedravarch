#!/usr/bin/env python3
"""Bounded format probes. Executables are read as bytes."""
import argparse
import hashlib
import io
import json
import lzma
from pathlib import Path
import struct
import subprocess
import tempfile
import zipfile
import zlib

LIMIT = 16 * 1024 * 1024
REPO = Path(__file__).resolve().parents[3]


def bounded_read(path):
    with path.open("rb") as stream:
        data = stream.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("input budget")
    return data


def deflate_probe(stream, mode):
    decoder = zlib.decompressobj(mode)
    plain = decoder.decompress(stream, LIMIT + 1)
    if len(plain) > LIMIT or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("invalid or oversized DEFLATE stream")
    matches = []
    for level in range(1, 10):
        encoder = zlib.compressobj(level, wbits=mode)
        if encoder.compress(plain) + encoder.flush() == stream:
            matches.append(level)
    return {"compressed": len(stream), "inflated": len(plain), "zlib_exact_levels": matches}


def zip_probes(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        results = []
        total = 0
        for member in archive.infolist():
            if member.compress_type != zipfile.ZIP_DEFLATED or member.flag_bits & 1:
                continue
            total += member.file_size
            if total > LIMIT or len(results) >= 256:
                raise ValueError("ZIP member budget")
            offset = member.header_offset
            header = data[offset:offset+30]
            if len(header) != 30 or header[:4] != b"PK\x03\x04":
                raise ValueError("ZIP local header")
            name, extra = struct.unpack_from("<HH", header, 26)
            start = offset + 30 + name + extra
            end = start + member.compress_size
            if end > len(data):
                raise ValueError("ZIP member extent")
            # ZipFile validates the member's local filename and CRC independently.
            result = deflate_probe(data[start:end], -15)
            checked = archive.read(member)
            if len(checked) != result["inflated"] or len(checked) != member.file_size:
                raise ValueError("ZIP member size mismatch")
            results.append(result)
        return results


def png_probe(data):
    position = 8
    streams = bytearray()
    while position + 12 <= len(data):
        length, kind = struct.unpack_from(">I4s", data, position)
        end = position + 8 + length
        if end + 4 > len(data):
            raise ValueError("PNG chunk extent")
        payload = data[position+8:end]
        checksum, = struct.unpack_from(">I", data, end)
        if zlib.crc32(kind + payload) != checksum:
            raise ValueError("PNG chunk CRC")
        position = end + 4
        if kind == b"IDAT":
            streams.extend(payload)
        if kind == b"IEND" and length == 0 and position == len(data):
            return deflate_probe(streams, 15)
    raise ValueError("missing PNG terminator")


def x86_probe(data):
    filters = [{"id": lzma.FILTER_X86}, {"id": lzma.FILTER_LZMA2, "preset": 6}]
    transformed = lzma.compress(data, filters=filters)
    direct = lzma.compress(data, preset=6)
    assert lzma.decompress(transformed) == data
    assert lzma.decompress(direct) == data
    return {"xz_bytes": len(direct), "xz_bcj_bytes": len(transformed),
            "choose_bcj": len(transformed) < len(direct)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("samples", metavar="LABEL:KIND:PATH", nargs="+")
    args = parser.parse_args()
    rows = []
    with tempfile.TemporaryDirectory(prefix="sadm-structure-") as temp:
        for spec in args.samples:
            label, kind, path = spec.split(":", 2)
            path = Path(path)
            data = bounded_read(path)
            result = {"label": label, "kind": kind, "input_bytes": len(data),
                      "sha256": hashlib.sha256(data).hexdigest(), "path": str(path)}
            if kind == "x86":
                if data[:2] != b"MZ" and data[:4] != b"\x7fELF":
                    raise ValueError("executable magic")
                result["bcj"] = x86_probe(data)
            if kind == "zip":
                result["members"] = zip_probes(data)
            if kind == "png":
                if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("PNG magic")
                result["idat"] = png_probe(data)
            archive = Path(temp) / "archive"
            restored = Path(temp) / "restored"
            sadm = REPO / "research/sadm/target/release/sadm"
            release = REPO / "target/release/sedravarch"
            for name, encode, decode in [
                ("sadm", [sadm, "encode", archive, path], [sadm, "decode", archive, restored]),
                ("sedravarch", [release, "pack-profile", "balanced", "1", path, archive],
                 [release, "unpack", archive, restored]),
            ]:
                subprocess.run(encode, check=True)
                subprocess.run(decode, check=True)
                assert restored.read_bytes() == data
                result[f"{name}_bytes"] = archive.stat().st_size
                archive.unlink()
                restored.unlink()
            rows.append(result)
    args.out.write_text(json.dumps({"zlib": zlib.ZLIB_RUNTIME_VERSION, "rows": rows}, indent=2) + "\n")


if __name__ == "__main__":
    main()
