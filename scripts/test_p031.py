#!/usr/bin/env python3
"""Deterministic bounded P03.1 decoder campaign and Linux fault injection."""
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib

BIN=Path(sys.argv[1]).resolve()
SEED=20261125
LIMIT=2*1024*1024
rng=random.Random(SEED)
stats={"valid_tag_fixtures":0,"targeted_rejections":0,"structured_mutations":0,
       "random_payloads":0,"index_mutations":0,"accepted_mutations":0,
       "enospc_write":0,"enospc_sync":0,"sigkill":0}
def require(value,msg):
    if not value: raise AssertionError(msg)
def limits():
    resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2)
    resource.setrlimit(resource.RLIMIT_FSIZE,(8*1024**2,)*2)
    resource.setrlimit(resource.RLIMIT_CPU,(4,5))
def run(*args,env=None):
    p=subprocess.run([str(BIN),*map(str,args)],capture_output=True,
                     timeout=8,preexec_fn=limits,env=env)
    require(p.returncode in (0,1),(args,p.returncode,p.stderr))
    return p
def block(tag,p,d,n=None,crc=None):
    return struct.pack("<BIII",tag,len(d) if n is None else n,len(p),
                       zlib.crc32(d) if crc is None else crc)+p
def stream(records,expected):
    return b"SDARCH\x04\x00"+b"".join(records)+b"\xff"+struct.pack("<QQI",len(expected),len(records),zlib.crc32(expected))
def huffman(data):
    # Independent, simple balanced tree; not the production encoder.
    codes={}
    def tree(symbols,path=""):
        if len(symbols)==1:
            codes[symbols[0]]=path
            return "1"+format(symbols[0],"08b")
        m=len(symbols)//2
        return "0"+tree(symbols[:m],path+"0")+tree(symbols[m:],path+"1")
    bits=tree(sorted(set(data)))+"".join(codes[b] for b in data)
    bits+="0"*(-len(bits)%8)
    return struct.pack("<I",len(data))+bytes(int(bits[i:i+8],2) for i in range(0,len(bits),8))
def fixtures():
    raw=b"A"*1024
    rle=bytes([255,65])*4+bytes([4,65])
    lz=b"\x00A"+bytes([254,1,0])*7+bytes([245,1,0])
    # 1+7*129+120 = 1024
    smart=b"\x00A\xff"+struct.pack("<HH",1023,1)
    ramp=bytes((65*(i+1))%256 for i in range(1024))
    bases={0:(raw,raw),1:(rle,raw),2:(lz,raw),3:(rle,ramp),
           4:(lz,ramp),10:(smart,raw),11:(smart,ramp)}
    for t in (0,1,2,3,4,10,11):
        p,d=bases[t]
        yield t,[block(t,p,d)],d
        yield (t+5 if t<=4 else t+2),[block(t+5 if t<=4 else t+2,huffman(p),d)],d
    base=block(1,rle,raw)
    yield 14,[base,block(14,b"\x01\x00",raw)],raw+raw
    patched=b"B"+raw[1:]
    yield 15,[base,block(15,struct.pack("<HHH",1,0,1)+b"B",patched)],raw+patched
def index_container(payload, entries):
    idx=struct.pack("<I",len(entries))
    for kind,path,size,off,packed in entries:
        idx+=struct.pack("<BI",kind,len(path))+path+struct.pack("<QQQQ",size,2**64-1,off,packed)
    return b"SDAMULT\x01"+payload+idx+b"SDAINDEX"+struct.pack("<QI",len(idx),zlib.crc32(idx))
def clean_stage(root):
    for p in root.glob(".sedravarch-*"):
        if p.is_dir(): shutil.rmtree(p)
        else: p.unlink()
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix="sda-p031-") as tmp:
    root=Path(tmp).resolve()
    archive=root/"input.sda";out=root/"output"
    def decode(blob,expected=None,must_reject=False):
        archive.write_bytes(blob)
        p=run("unpack",archive,out,LIMIT)
        if p.returncode==0:
            require(not must_reject,"invalid fixture accepted")
            require(out.is_file() and out.stat().st_size<=LIMIT,"invalid published output")
            if expected is not None:
                require(out.read_bytes()==expected,"accepted mutation changed decoded bytes")
            out.unlink()
        else:
            require(expected is None or must_reject or p.stderr,"missing error")
            require(not out.exists(),"failure published partial output")
        require(not list(root.glob(".sedravarch-*")),"staging leak on ordinary exit")
        return p.returncode
    all_fixtures=[]
    for tag,records,data in fixtures():
        blob=stream(records,data)
        require(decode(blob,data)==0,("valid tag",tag))
        all_fixtures.append((tag,blob,data))
        stats["valid_tag_fixtures"]+=1
    require({t for t,_,_ in all_fixtures}==set(range(16)),"missing tag")
    bad=[
        block(1,b"\x00A",b"A"*8),block(1,b"\xffA",b"A"*8),
        block(2,b"\x80\x00\x00",b"A"*8),
        block(2,b"\x7fA",b"A"*8),
        block(10,b"\xff\x81\x00\x01\x00",b"A"*8),
        block(10,b"\x00A\xff\xff\xff\x01\x00",b"A"*8),
        block(5,struct.pack("<I",2**32-1)+b"\x80",b"A"*8),
        block(5,struct.pack("<I",8)+b"\x00"*32,b"A"*64),
        block(14,b"\x01\x00",b"A"*8),
        block(15,struct.pack("<HHH",1,0,1)+b"B",b"A"*8),
        block(16,b"A",b"A"),block(0,b"A",b"A",n=65537),
        block(0,b"A",b"A",n=0),block(0,b"A",b"A",crc=0)]
    for rec in bad:
        decode(stream([rec],b""),must_reject=True)
        stats["targeted_rejections"]+=1
    # Valid history followed by illegal patch range and excessive depth.
    base=block(0,b"A"*16,b"A"*16)
    for records in ([base,block(15,struct.pack("<HHH",1,16,1)+b"B",b"A"*16)],
                    [base]+[block(14,b"\x01\x00",b"A"*16)]*5):
        decode(stream(records,b"A"*16*len(records)),must_reject=True)
        stats["targeted_rejections"]+=1
    # Mutate across all real tag fixtures, including interior payloads.
    for tag,blob,data in all_fixtures:
        for _ in range(64):
            mut=bytearray(blob)
            for _ in range(rng.randint(1,4)):
                i=rng.randrange(8,len(mut));mut[i]^=1<<rng.randrange(8)
            rc=decode(mut,data)
            stats["structured_mutations"]+=1
            stats["accepted_mutations"]+=int(rc==0)
    # Structurally valid headers drive random payloads into each codec.
    for tag in range(16):
        for _ in range(64):
            n=rng.randint(8,512)
            p=rng.randbytes(n if tag==0 else rng.randint(1,n))
            # CRC deliberately not an oracle for random compressed bytes.
            b=stream([block(tag,p,b"\0"*n)],b"\0"*n)
            rc=decode(b)
            stats["random_payloads"]+=1
            stats["accepted_mutations"]+=int(rc==0)
    # Recompute outer index CRC so invalid metadata reaches parser.
    data=b"A"*16;payload=stream([block(0,data,data)],data);n=len(payload)
    good=(0,b"file",len(data),8,n)
    invalid_entries=[
        [(0,b"../x",16,8,n)],[(0,b"/abs",16,8,n)],[(0,b"C:x",16,8,n)],
        [(0,b"CON",16,8,n)],[(0,b"file.",16,8,n)],[(0,b"a/b",16,8,n)],
        [(0,b"\xff",16,8,n)],[(2,b"file",16,8,n)],[(0,b"file",16,9,n)],
        [(0,b"file",16,8,2**64-1)],[(1,b"dir",1,0,0),good],
        [(1,b"FILE",0,0,0),good],[(1,b"dir",0,0,0),(0,b"DIR/x",16,8,n)]]
    for entries in invalid_entries:
        archive.write_bytes(index_container(payload,entries))
        require(run("list",archive).returncode==1,"invalid index accepted")
        require(run("extract",archive,out,LIMIT).returncode==1,"invalid index extracted")
        require(not out.exists(),"invalid index published root")
        stats["index_mutations"]+=1
    print("DECODER",json.dumps(stats),flush=True)
    source=root/"source";source.write_bytes(rng.randbytes(65536))
    packed=root/"packed";multi=root/"multi"
    require(run("pack",source,packed).returncode==0,"pack fixture")
    require(run("create",multi,source).returncode==0,"multi fixture")
    originals={p:digest(p) for p in (source,packed,multi)}
    shim=root/"fault.so"
    subprocess.run(["cc","-shared","-fPIC","-Wall","-Wextra","-Werror","-O2",
                    str(Path(__file__).with_name("p031_fault.c")),"-ldl","-o",str(shim)],check=True,timeout=30)
    commands=[("pack",source,out),("unpack",packed,out,LIMIT),
              ("create",out,source),("extract-file",multi,"source",out,LIMIT),
              ("extract",multi,out,LIMIT)]
    for args in commands:
        for mode in ("write","sync"):
            env=dict(os.environ,LD_PRELOAD=str(shim),SDA_FAULT_ROOT=str(root),SDA_FAULT_MODE=mode)
            p=run(*args,env=env)
            require(p.returncode==1 and ("P031 ENOSPC "+mode.upper()).encode() in p.stderr,(args,mode,p.stderr))
            require(not out.exists(),"ENOSPC published output")
            require(not list(root.glob(".sedravarch-*")),"ENOSPC staging leak")
            require(all(digest(p)==h for p,h in originals.items()),"original changed")
            stats["enospc_"+mode]+=1
        env=dict(os.environ,LD_PRELOAD=str(shim),SDA_FAULT_ROOT=str(root),SDA_FAULT_MODE="block")
        p=subprocess.Popen([str(BIN),*map(str,args)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           env=env,preexec_fn=limits)
        try:
            ready,_,_=select.select([p.stderr],[],[],8)
            require(ready and b"P031 BLOCK REACHED" in p.stderr.readline(),"kill injection not reached")
            require(not out.exists(),"partial output visible before kill")
            p.kill();p.communicate(timeout=5)
            require(p.returncode==-9 and not out.exists(),"partial output visible after kill")
            require(all(digest(p)==h for p,h in originals.items()),"kill changed original")
            require(bool(list(root.glob(".sedravarch-*"))),"expected interrupted staging")
            stats["sigkill"]+=1
        finally:
            if p.poll() is None: p.kill();p.communicate(timeout=5)
            clean_stage(root)
    print("P031_RESULT",json.dumps(stats,sort_keys=True),flush=True)
