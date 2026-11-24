#!/usr/bin/env python3
"""Compare v0.3 and v0.4 fixed/adaptive modes with exact roundtrips."""
import argparse
import hashlib
from pathlib import Path
import random
import statistics
import struct
import subprocess
import tempfile
import time

def chunks(archive, data):
    pos, off, result = 8, 0, []
    while archive[pos] != 255:
        n, p, crc = struct.unpack_from("<III", archive, pos+1)
        result.append((n, hashlib.sha256(data[off:off+n]).digest()))
        off += n
        pos += 13+p
    if off != len(data):
        raise ValueError("chunk lengths do not cover original")
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("runs must be positive")
    old, new = args.baseline.resolve(), args.candidate.resolve()
    print("input,bytes,mode,archive,blocks,pack_median_s,unpack_median_s", flush=True)
    with tempfile.TemporaryDirectory(prefix="sedravarch-chunks-") as td:
        root = Path(td)
        a, b = root/"a", root/"b"
        for p in args.files:
            p = p.resolve()
            data = p.read_bytes()
            for label, binary, mode in [("v3",old,"pack"),("v4-fixed",new,"pack-fixed"),("v4-adaptive",new,"pack")]:
                es, ds = [], []
                for _ in range(args.runs):
                    a.unlink(missing_ok=True)
                    b.unlink(missing_ok=True)
                    t=time.perf_counter()
                    subprocess.run([binary,mode,p,a],check=True)
                    es.append(time.perf_counter()-t)
                    t=time.perf_counter()
                    subprocess.run([binary,"unpack",a,b,str(len(data))],check=True)
                    ds.append(time.perf_counter()-t)
                    if b.read_bytes()!=data:
                        raise RuntimeError("roundtrip mismatch")
                print(f"{p.name},{len(data)},{label},{a.stat().st_size},{len(chunks(a.read_bytes(),data))},{statistics.median(es):.6f},{statistics.median(ds):.6f}",flush=True)
                b.unlink()
                other=new if binary==old else old
                subprocess.run([other,"unpack",a,b,str(len(data))],check=True)
                if b.read_bytes()!=data:
                    raise RuntimeError("cross-version mismatch")
        original=random.Random(2026).randbytes(2*1024*1024)
        edited=original[:100000]+b"X"*137+original[100000:]
        for mode in ["pack-fixed","pack"]:
            p=root/"insertion.bin"
            sets=[]
            for d in [original,edited]:
                p.write_bytes(d)
                a.unlink(missing_ok=True)
                subprocess.run([new,mode,p,a],check=True)
                sets.append(chunks(a.read_bytes(),d))
            common=set(sets[0])&set(sets[1])
            print(f"INSERT {mode}: {len(common)}/{len(sets[0])} shared blocks, {sum(n for n,h in common)}/{len(original)} shared bytes",flush=True)

if __name__ == "__main__":
    main()
