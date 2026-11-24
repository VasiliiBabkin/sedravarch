#!/usr/bin/env python3
"""Compare two SedravArch executables and standard CLI codecs, with byte verification."""
import argparse
import hashlib
from pathlib import Path
import shutil
import statistics
import subprocess
import tempfile
import time
import csv
import sys

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    old, new = args.baseline.resolve(), args.candidate.resolve()
    writer = csv.writer(sys.stdout)
    writer.writerow(["input", "sha256", "bytes", "codec", "compressed", "pack_median_s", "unpack_median_s"])
    for source in args.files:
        source = source.resolve()
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory(prefix="sedravarch-bench-") as td:
            a, b = Path(td)/"a", Path(td)/"b"
            codecs = [
                ("baseline", [old,"pack",source,a], [old,"unpack",a,b,str(len(data))], False),
                ("candidate", [new,"pack",source,a], [new,"unpack",a,b,str(len(data))], False),
                ("gzip-6", ["gzip","-6","-c",source], ["gzip","-dc",a], True),
                ("xz-6", ["xz","-6","-T1","-c",source], ["xz","-dc",a], True),
                ("zstd-3", ["zstd","-3","-T1","-q","-c",source], ["zstd","-q","-dc",a], True),
            ]
            for label, enc, dec, redirected in codecs:
                if redirected and shutil.which(enc[0]) is None:
                    print(f"skip {label}: executable not found", file=sys.stderr)
                    continue
                def run(cmd, output):
                    start = time.perf_counter()
                    if redirected:
                        with output.open("wb") as fp:
                            subprocess.run(cmd, stdout=fp, check=True)
                    else:
                        subprocess.run(cmd, check=True)
                    return time.perf_counter() - start
                es, ds = [], []
                for _ in range(args.runs):
                    a.unlink(missing_ok=True)
                    b.unlink(missing_ok=True)
                    es.append(run(enc,a))
                    ds.append(run(dec,b))
                    if b.read_bytes() != data:
                        raise RuntimeError(f"byte mismatch: {source} {label}")
                writer.writerow([source.name, digest, len(data), label, a.stat().st_size,
                                 f"{statistics.median(es):.6f}", f"{statistics.median(ds):.6f}"])
                sys.stdout.flush()

if __name__ == "__main__":
    main()
