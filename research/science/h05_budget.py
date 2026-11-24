#!/usr/bin/env python3
"""H05: real, repeated adaptive codec selection, with complete decision cost."""
import argparse, ctypes as C, ctypes.util, fcntl, hashlib, json, lzma, math, os, pathlib, platform, random, shutil, statistics, struct, time, zlib
P=argparse.ArgumentParser();P.add_argument('--lab',type=pathlib.Path,required=True);P.add_argument('--out',type=pathlib.Path,required=True)
a=P.parse_args();root=a.lab.resolve();os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert shutil.disk_usage(root).free>=5*1024**3
lib=C.CDLL(ctypes.util.find_library('zstd') or 'libzstd.so.1')
lib.ZSTD_versionString.restype=C.c_char_p
lib.ZSTD_compressBound.argtypes=[C.c_size_t];lib.ZSTD_compressBound.restype=C.c_size_t
lib.ZSTD_compress.argtypes=[C.c_void_p,C.c_size_t,C.c_char_p,C.c_size_t,C.c_int];lib.ZSTD_compress.restype=C.c_size_t
lib.ZSTD_decompress.argtypes=[C.c_void_p,C.c_size_t,C.c_char_p,C.c_size_t];lib.ZSTD_decompress.restype=C.c_size_t
lib.ZSTD_isError.argtypes=[C.c_size_t];lib.ZSTD_isError.restype=C.c_uint
def sha(x):return hashlib.sha256(x).hexdigest()
def codec(x,t):
    if t==0:return x
    if t==3:return lzma.compress(x,format=lzma.FORMAT_XZ,preset=5,check=lzma.CHECK_CRC64)
    cap=lib.ZSTD_compressBound(len(x));out=C.create_string_buffer(cap)
    n=lib.ZSTD_compress(out,cap,x,len(x),3 if t==1 else 15)
    if lib.ZSTD_isError(n):raise RuntimeError('zstd compress')
    return out.raw[:n]
def encode(x,policy):
    tried={0:x};probes={};selected=None
    def run(t):
        if t not in tried:tried[t]=codec(x,t)
    if policy in ('Z3','Z15','XZ5'):
        run({'Z3':1,'Z15':2,'XZ5':3}[policy])
    elif policy=='Exhaustive':
        for t in (1,2,3):run(t)
    elif policy=='Adaptive':
        run(1)
        if len(x)<=12288:
            run(2);run(3)
        else:
            n=len(x);probe=b''.join(x[i:i+4096] for i in (0,(n-4096)//2,n-4096))
            probes={t:len(codec(probe,t)) for t in (0,1,2,3)}
            base=min(probes[0],probes[1]);best=min((2,3),key=lambda t:(probes[t],t))
            if base-probes[best]>=max(32,math.ceil(.01*base)):
                selected=best;run(best)
    else:raise ValueError(policy)
    tag=min(tried,key=lambda t:(len(tried[t]),t))
    frame=struct.pack('<4sBII',b'H05A',tag,len(x),zlib.crc32(x))+tried[tag]
    return frame,dict(tag=tag,full_sizes={t:len(p) for t,p in tried.items()},probe_sizes=probes,selected=selected)
def decode(b):
    magic,tag,n,crc=struct.unpack_from('<4sBII',b)
    assert magic==b'H05A' and tag in (0,1,2,3) and n<=131072
    p=b[13:]
    if tag==0:x=p
    elif tag==3:x=lzma.decompress(p)
    else:
        out=C.create_string_buffer(n);k=lib.ZSTD_decompress(out,n,p,len(p))
        assert not lib.ZSTD_isError(k) and k==n
        x=out.raw
    assert len(x)==n and zlib.crc32(x)==crc
    return x
policies=('Z3','Z15','XZ5','Exhaustive','Adaptive')
manifest=json.loads((root/'corpora/manifest.json').read_text());rows=[]
a.out.parent.mkdir(parents=True,exist_ok=True)
with a.out.open('x') as f:
    def log(r):f.write(json.dumps(r)+'\n');f.flush()
    log(dict(type='meta',protocol='H05',python=platform.python_version(),platform=platform.platform(),affinity=sorted(os.sched_getaffinity(0)),script_sha256=sha(pathlib.Path(__file__).read_bytes()),zstd=lib.ZSTD_versionString().decode(),repetitions=3))
    for item in sorted(manifest,key=lambda x:(x['group'],x['path'])):
        group=item['group']
        if group not in ('synthetic','canterbury','silesia'):continue
        p=(root/item['path']).resolve();assert p.is_relative_to(root/'corpora')
        data=p.read_bytes();assert sha(data)==item['sha256']
        offset=(len(data)-131072)//2 if group=='silesia' else 0
        orig=data[offset:offset+131072];digest=sha(orig);runs={k:[] for k in policies}
        for rep in range(3):
            order=list(policies);random.Random(int(digest,16)+rep).shuffle(order)
            for policy in order:
                c=time.process_time_ns();w=time.perf_counter_ns();frame,detail=encode(orig,policy);enc=time.process_time_ns()-c;wall=time.perf_counter_ns()-w
                c=time.process_time_ns();w=time.perf_counter_ns();rest=decode(frame);dec=time.process_time_ns()-c;dwall=time.perf_counter_ns()-w
                assert rest==orig
                runs[policy].append(dict(rep=rep,bytes=len(frame),sha256=sha(frame),encode_cpu_ns=enc,encode_wall_ns=wall,decode_cpu_ns=dec,decode_wall_ns=dwall,**detail))
        for k,v in runs.items():assert len(set(r['sha256'] for r in v))==1
        r=dict(type='sample',group=group,path=item['path'],offset=offset,input_bytes=len(orig),sha256=digest,file_sha256=item['sha256'],runs=runs)
        rows.append(r);log(r);print(group,p.name,len(orig),{k:v[0]['bytes'] for k,v in runs.items()},flush=True)
    for g in ('synthetic','canterbury','silesia'):
        rs=[r for r in rows if r['group']==g];totals={}
        for k in policies:
            totals[k]=dict(bytes=sum(r['runs'][k][0]['bytes'] for r in rs),encode_cpu_ns=sum(statistics.median(x['encode_cpu_ns'] for x in r['runs'][k]) for r in rs),encode_wall_ns=sum(statistics.median(x['encode_wall_ns'] for x in r['runs'][k]) for r in rs),decode_cpu_ns=sum(statistics.median(x['decode_cpu_ns'] for x in r['runs'][k]) for r in rs))
        A=totals['Adaptive'];E=totals['Exhaustive'];X=totals['XZ5']
        result=dict(type='summary',group=g,samples=len(rs),input_bytes=sum(r['input_bytes'] for r in rs),totals=totals,checks=len(rs)*len(policies)*3,adaptive_over_exhaustive_size=A['bytes']/E['bytes'],adaptive_over_exhaustive_cpu=A['encode_cpu_ns']/E['encode_cpu_ns'],adaptive_over_xz_size=A['bytes']/X['bytes'],adaptive_over_xz_cpu=A['encode_cpu_ns']/X['encode_cpu_ns'],dominating_fixed=[k for k in ('Z3','Z15','XZ5') if totals[k]['bytes']<=A['bytes'] and totals[k]['encode_cpu_ns']<=A['encode_cpu_ns'] and (totals[k]['bytes']<A['bytes'] or totals[k]['encode_cpu_ns']<A['encode_cpu_ns'])],adaptive_full_evaluations=sum(len(r['runs']['Adaptive'][0]['full_sizes'])-1 for r in rs),exhaustive_full_evaluations=3*len(rs))
        result['gate_a']=result['adaptive_over_exhaustive_size']<=1.01 and result['adaptive_over_exhaustive_cpu']<=.70
        result['gate_b']=result['adaptive_over_xz_size']<=1.01 and result['adaptive_over_xz_cpu']<=.70
        log(result);print(json.dumps(result),flush=True)
