#!/usr/bin/env python3
"""Multi-file integration and adversarial tests. Uses only isolated temporary files."""
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import zlib

binary = Path(sys.argv[1]).resolve()
passed = 0
def run(*args, ok=True):
    p = subprocess.run([binary, *map(str,args)], capture_output=True, text=True)
    if (p.returncode == 0) != ok:
        raise AssertionError((args,p.returncode,p.stdout,p.stderr))
    return p.stdout
def check(name, condition=True):
    global passed
    if not condition:
        raise AssertionError(name)
    passed += 1
    print("PASS",name,flush=True)
def tree(root):
    return {p.relative_to(root).as_posix(): None if p.is_dir() else p.read_bytes()
            for p in root.rglob("*")}
def mutate_index(original, output, fn):
    data = bytearray(original.read_bytes())
    n = struct.unpack_from("<Q",data,len(data)-12)[0]
    start = len(data)-20-n
    idx=bytearray(data[start:start+n])
    fn(idx)
    output.write_bytes(data[:start]+idx+b"SDAINDEX"+struct.pack("<QI",len(idx),zlib.crc32(idx)))
def positions(idx):
    count=struct.unpack_from("<I",idx)[0]
    i=4
    for _ in range(count):
        kind=idx[i];n=struct.unpack_from("<I",idx,i+1)[0]
        yield kind,i+5,n,i+5+n
        i+=37+n
with tempfile.TemporaryDirectory(prefix="sedravarch-integration-") as tmp:
    root=Path(tmp); src=root/"project"; src.mkdir()
    (src/"nested").mkdir(); (src/"empty-dir").mkdir()
    (src/"nested"/"текст.txt").write_text("Привет, SedravArch!\n"*1000,encoding="utf-8")
    (src/"empty").touch()
    raw=random.Random(123).randbytes(200000)
    (src/"raw.bin").write_bytes(raw)
    note=root/"notes.txt";note.write_text("notes")
    a=root/"archive.sda";run("create",a,src,note);check("create multiple inputs")
    listing=run("list",a);check("list Unicode, empty directory and multiple inputs",all(s in listing for s in ["project/nested/текст.txt","project/empty-dir","notes.txt"]))
    run("test",a);check("verify complete archive")
    restored=root/"restored";run("extract",a,restored)
    check("full tree byte equality",tree(src)==tree(restored/"project") and (restored/"notes.txt").read_bytes()==note.read_bytes())
    single=root/"single";run("extract-file",a,"project/raw.bin",single)
    check("single file extraction",single.read_bytes()==raw)
    run("extract-file",a,"project/raw.bin",single,ok=False);check("no file overwrite",single.read_bytes()==raw)
    run("extract",a,restored,ok=False);check("no directory overwrite",tree(src)==tree(restored/"project"))
    run("create",a,src,ok=False);check("no archive overwrite")
    run("test",a,1,ok=False);check("test output budget")
    small=root/"small";run("extract",a,small,1,ok=False);check("extract output budget",not small.exists())
    run("extract-file",a,"project/raw.bin",small,1,ok=False);check("single output budget",not small.exists())
    run("extract-file",a,"missing",small,ok=False);check("missing file",not small.exists())
    run("extract-file",a,"project/empty-dir",small,ok=False);check("directory is not file",not small.exists())
    run("create",src/"self.sda",src,ok=False);check("output inside input rejected",not (src/"self.sda").exists())
    link=root/"link";link.symlink_to(note)
    run("create",root/"link.sda",link,ok=False);check("symlink input rejected")
    (src/"linked").symlink_to(note)
    run("create",root/"child-link.sda",src,ok=False);check("nested symlink rejected")
    (src/"linked").unlink()
    other=root/"other";other.mkdir();(other/"notes.txt").write_text("different")
    run("create",root/"dup.sda",note,other/"notes.txt",ok=False);check("duplicate root name rejected")
    bad=root/"bad.sda";bad.write_bytes(a.read_bytes()[:-1])
    run("list",bad,ok=False);check("truncated footer rejected")
    corrupt=bytearray(a.read_bytes());corrupt[-1]^=1;bad.write_bytes(corrupt)
    run("list",bad,ok=False);check("index CRC rejected")
    def traversal(idx):
        _,off,n,_=next(positions(idx))
        idx[off:off+n]=b"../evil"
    mutate_index(a,bad,traversal)
    run("extract",bad,small,ok=False);check("traversal with valid CRC rejected",not small.exists() and not (root/"evil").exists())
    def extent(idx):
        _,_,_,off=next(p for p in positions(idx) if p[0]==0)
        struct.pack_into("<Q",idx,off+16,0)
    mutate_index(a,bad,extent)
    run("list",bad,ok=False);check("forged extent with valid CRC rejected")
    def size(idx):
        _,_,_,off=next(p for p in positions(idx) if p[0]==0)
        struct.pack_into("<Q",idx,off,1)
    mutate_index(a,bad,size)
    run("test",bad,ok=False);check("forged decoded size rejected")
    # Break first regular stream magic, keeping the index and other streams intact.
    corrupt=bytearray(a.read_bytes());corrupt[8]^=1;bad.write_bytes(corrupt)
    run("test",bad,ok=False);check("bad payload rejected")
    run("extract",bad,small,ok=False);check("failed full extraction cleanup",not small.exists())
    isolated=root/"isolated";run("extract-file",bad,"notes.txt",isolated)
    check("random access skips damaged unrelated stream",isolated.read_bytes()==note.read_bytes())
    run("list",bad);check("list checks index independently")
    legacy=root/"legacy.sda";run("pack",note,legacy);run("test",legacy)
    legacy_out=root/"legacy-out";run("unpack",legacy,legacy_out)
    check("legacy single-stream commands",legacy_out.read_bytes()==note.read_bytes())
    print("Archive bytes:",a.stat().st_size,"original file bytes:",sum(len(v) for v in tree(src).values() if v is not None)+note.stat().st_size)
    print(f"{passed}/{passed} integration checks PASS",flush=True)
