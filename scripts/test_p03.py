#!/usr/bin/env python3
"""P03 bounded compatibility and failure-publication regression checks."""
import os
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import time
import zlib

binary=Path(sys.argv[1]).resolve()
checks=0
def check(value, name):
    global checks
    if not value:
        raise AssertionError(name)
    checks+=1
def run(*args, ok=True):
    p=subprocess.run([str(binary),*map(str,args)],capture_output=True,timeout=15)
    check(p.returncode==0 if ok else p.returncode==1,(args,p.returncode,p.stderr))
    return p

def fixture(version, data):
    b=b"SDARCH"+bytes([version,0])
    if data:
        b+=struct.pack("<BIII",0,len(data),len(data),zlib.crc32(data))+data
    b+=b"\xff"
    if version>=2:
        b+=struct.pack("<QQI",len(data),int(bool(data)),zlib.crc32(data))
    return b

with tempfile.TemporaryDirectory(prefix="sda-p03-") as tmp:
    root=Path(tmp)
    data=b"compatibility\x00\xff"*7
    for version in range(1,5):
        for d in (b"",data):
            a=root/"fixture";out=root/"out"
            original=fixture(version,d)
            a.write_bytes(original)
            run("test",a,len(d))
            run("unpack",a,out,len(d))
            check(out.read_bytes()==d,"legacy decoded bytes")
            out.unlink()
            for n in range(len(original)):
                a.write_bytes(original[:n])
                run("unpack",a,out,ok=False)
                check(not out.exists(),"truncation published output")
            a.write_bytes(original+b"x")
            run("unpack",a,out,ok=False)
            check(not out.exists(),"trailing bytes published output")
        a.write_bytes(fixture(version,data))
        run("unpack",a,out,len(data)-1,ok=False)
        check(not out.exists(),"budget violation published output")
        corrupt=bytearray(fixture(version,data));corrupt[21]^=1
        a.write_bytes(corrupt)
        run("unpack",a,out,ok=False)
        check(not out.exists(),"CRC violation published output")
    source=root/"source";source.write_bytes(random.Random(42).randbytes(4096))
    a=root/"packed"
    run("pack",source,a)
    packed=a.read_bytes()
    out.write_bytes(b"sentinel")
    run("unpack",a,out,ok=False)
    check(out.read_bytes()==b"sentinel","overwrote destination")
    run("pack",source,source,ok=False)
    check(source.read_bytes()==random.Random(42).randbytes(4096),"overwrote source")
    if os.name=="posix":
        link=root/"link";link.symlink_to(root/"missing")
        run("unpack",a,link,ok=False)
        check(link.is_symlink() and not (root/"missing").exists(),"followed dangling symlink")
        link.unlink()
    # Deterministic malformed headers and random bit corruption; only count
    # outcomes with normal exits, never treat successful decoding as a failure
    # automatically because some mutations can remain valid.
    rng=random.Random(20261125)
    out.unlink()
    for _ in range(128):
        mutated=bytearray(packed)
        for _ in range(rng.randint(1,4)):
            i=rng.randrange(len(mutated));mutated[i]^=1<<rng.randrange(8)
        a.write_bytes(mutated)
        p=subprocess.run([str(binary),"unpack",str(a),str(out),"65536"],capture_output=True,timeout=15)
        check(p.returncode in (0,1),"crash or abnormal exit")
        if p.returncode==0:
            check(out.exists(),"successful output missing")
            out.unlink()
        else:
            check(not out.exists(),"rejected stream published output")
    check(not list(root.glob(".sedravarch-tmp-*")),"temporary output leaked on normal exit")
    if sys.platform.startswith("linux"):
        fifo=root/"blocked-input";os.mkfifo(fifo)
        fd=os.open(fifo,os.O_RDWR)
        killed=root/"killed-output"
        p=subprocess.Popen([str(binary),"pack",str(fifo),str(killed)],
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+5
            while not list(root.glob(".sedravarch-tmp-*")) and p.poll() is None and time.monotonic()<deadline:
                time.sleep(.02)
            check(bool(list(root.glob(".sedravarch-tmp-*"))),"staging not reached")
            check(not killed.exists(),"partial output visible before kill")
            p.kill();p.communicate(timeout=5)
            check(not killed.exists(),"partial output visible after kill")
        finally:
            if p.poll() is None:
                p.kill();p.communicate(timeout=5)
            os.close(fd)
            for temp in root.glob(".sedravarch-tmp-*"):
                temp.unlink()

print(f"{checks} P03 assertions PASS")
