#!/usr/bin/env python3
"""H01: finite transform oracle, not a deployable compressor."""
import argparse, hashlib, json, lzma, os, pathlib, platform, time, fcntl, shutil
import numpy as np
P=argparse.ArgumentParser()
P.add_argument('--lab',type=pathlib.Path,required=True)
P.add_argument('--out',type=pathlib.Path,required=True)
a=P.parse_args(); root=a.lab.resolve()
os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert shutil.disk_usage(root).free>=5*1024**3
m=json.loads((root/'corpora/manifest.json').read_text())
menu=[('identity',0,0)]+[(f'shuffle-{w}',0,w) for w in (2,4,8,16)]+[(f'delta-{w}',w,0) for w in (1,2,4,8,16)]+[(f'delta-shuffle-{w}',w,w) for w in (2,4,8,16)]
def shuffle(x,w,inv=False):
    n=len(x)//w*w
    if inv:y=x[:n].reshape(w,-1).T.flatten()
    else:y=x[:n].reshape(-1,w).T.flatten()
    return np.concatenate((y,x[n:]))
def transform(data,lag,w,inv=False):
    x=np.frombuffer(data,dtype=np.uint8).copy()
    if inv:
        if w:x=shuffle(x,w,True)
        if lag:
            for j in range(lag): x[j::lag]=np.cumsum(x[j::lag],dtype=np.uint64).astype(np.uint8)
    else:
        if lag:x[lag:]=x[lag:]-x[:-lag]
        if w:x=shuffle(x,w)
    return x.tobytes()
def sha(d):return hashlib.sha256(d).hexdigest()
rows=[]
a.out.parent.mkdir(parents=True,exist_ok=True)
with a.out.open('x') as out:
    meta={'type':'meta','protocol':'H01','python':platform.python_version(),'numpy':np.__version__,'platform':platform.platform(),'cpu_affinity':sorted(os.sched_getaffinity(0)),'menu':menu,'xz_preset':5,'check':'CRC64','script_sha256':sha(pathlib.Path(__file__).read_bytes())}
    out.write(json.dumps(meta)+'\n');out.flush()
    for item in sorted(m,key=lambda x:(x['group'],x['path'])):
        g=item['group']
        if g not in ('synthetic','canterbury','silesia'):continue
        p=(root/item['path']).resolve();assert p.is_relative_to(root/'corpora')
        data=p.read_bytes();assert sha(data)==item['sha256']
        n=len(data);w=262144
        windows=[(0,data)] if g!='silesia' else [(i,data[i:i+w]) for i in (0,(n-w)//2,n-w)]
        for offset,original in windows:
            candidates=[]
            for idx,(name,lag,width) in enumerate(menu):
                cpu=time.process_time();wall=time.perf_counter()
                payload=bytes([idx])+lzma.compress(transform(original,lag,width),format=lzma.FORMAT_XZ,check=lzma.CHECK_CRC64,preset=5)
                enc_cpu=time.process_time()-cpu;enc_wall=time.perf_counter()-wall
                cpu=time.process_time()
                ident=payload[0];_,l,b=menu[ident]
                restored=transform(lzma.decompress(payload[1:]),l,b,True)
                dec_cpu=time.process_time()-cpu
                if restored!=original:raise RuntimeError('roundtrip failure')
                candidates.append(dict(name=name,bytes=len(payload),encode_cpu_s=enc_cpu,encode_wall_s=enc_wall,decode_cpu_s=dec_cpu))
            best=min(candidates,key=lambda x:x['bytes'])
            row=dict(type='sample',group=g,path=item['path'],offset=offset,input_bytes=len(original),sha256=sha(original),baseline=candidates[0]['bytes']-1,best=best['name'],oracle=best['bytes'],candidates=candidates)
            rows.append(row);out.write(json.dumps(row)+'\n');out.flush()
            print(g,pathlib.Path(item['path']).name,offset,row['baseline'],row['oracle'],row['best'],flush=True)
    for g in ('synthetic','canterbury','silesia'):
        r=[x for x in rows if x['group']==g];base=sum(x['baseline'] for x in r);oracle=sum(x['oracle'] for x in r)
        result=dict(type='summary',group=g,samples=len(r),input_bytes=sum(x['input_bytes'] for x in r),baseline=base,oracle=oracle,saving_percent=100*(base-oracle)/base,roundtrips=len(r)*len(menu),baseline_cpu=sum(x['candidates'][0]['encode_cpu_s'] for x in r),search_cpu=sum(c['encode_cpu_s'] for x in r for c in x['candidates']))
        out.write(json.dumps(result)+'\n');out.flush();print(json.dumps(result),flush=True)
