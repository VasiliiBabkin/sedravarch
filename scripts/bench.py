#!/usr/bin/env python3
"""Compare whole-file sizes, wall time and verified restoration; no benchmark claims."""
import gzip, lzma, subprocess, pathlib, tempfile, time, sys
def timed(fn):
    start = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - start
def main():
    binary = pathlib.Path(sys.argv[1]).resolve()
    print("file,codec,input_bytes,output_bytes,encode_seconds,decode_seconds", flush=True)
    for name in sys.argv[2:]:
        p = pathlib.Path(name).resolve()
        data = p.read_bytes()
        for label, enc, dec in [("gzip-6", lambda: gzip.compress(data, compresslevel=6), gzip.decompress), ("xz-6", lambda: lzma.compress(data, preset=6), lzma.decompress)]:
            a, t = timed(enc)
            b, dt = timed(lambda: dec(a))
            assert b == data
            print(f"{p.name},{label},{len(data)},{len(a)},{t:.6f},{dt:.6f}", flush=True)
        with tempfile.TemporaryDirectory() as tmp:
            a = pathlib.Path(tmp)/"archive.sda"
            b = pathlib.Path(tmp)/"restored"
            _, t = timed(lambda: subprocess.run([binary,"pack",p,a],check=True))
            _, dt = timed(lambda: subprocess.run([binary,"unpack",a,b,str(len(data))],check=True))
            assert b.read_bytes() == data
            print(f"{p.name},sedravarch,{len(data)},{a.stat().st_size},{t:.6f},{dt:.6f}", flush=True)
if __name__ == "__main__":
    main()
