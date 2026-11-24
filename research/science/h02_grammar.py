#!/usr/bin/env python3
"""H02: bounded greedy pair grammar, two serializations, XZ backend."""
import argparse,hashlib,json,lzma,os,pathlib,platform,struct,time,fcntl,shutil
import numpy as np
P=argparse.ArgumentParser()
P.add_argument('--lab',type=pathlib.Path,required=True)
P.add_argument('--out',type=pathlib.Path,required=True)
a=P.parse_args();root=a.lab.resolve()
os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert shutil.disk_usage(root).free>=5*1024**3
def sha(d):return hashlib.sha256(d).hexdigest()
def xz(d):return lzma.compress(d,format=lzma.FORMAT_XZ,check=lzma.CHECK_CRC64,preset=5)
def states(data):
    seq=np.frombuffer(data,dtype=np.uint8).astype(np.uint16)
    rules=[];stopped=False;cpu=0.
    for target in (16,64,256):
        t=time.process_time()
        while len(rules)<target and not stopped:
            if len(seq)<4:stopped=True;break
            pairs=(seq[:-1].astype(np.uint32)<<16)|seq[1:].astype(np.uint32)
            keys,counts=np.unique(pairs,return_counts=True)
            key=int(keys[np.argmax(counts)]);left=key>>16;right=key&65535
            hit=pairs==key
            if left==right:
                # In a run, take start positions 0,2,4,... relative to run.
                ix=np.arange(len(hit))
                last_false=np.maximum.accumulate(np.where(hit,-1,ix))
                hit=hit&(((ix-last_false)&1)==1)
            starts=np.flatnonzero(hit)
            if len(starts)<3:stopped=True;break
            keep=np.ones(len(seq),dtype=bool)
            keep[starts+1]=False
            seq[starts]=256+len(rules)
            seq=seq[keep]
            rules.append((left,right))
        cpu+=time.process_time()-t
        yield target,tuple(rules),seq.copy(),cpu
def serialize(n,rules,seq,split):
    body=np.concatenate((np.asarray(rules,dtype='<u2').reshape(-1),seq.astype('<u2'))).astype('<u2').tobytes()
    if split:body=body[::2]+body[1::2]
    return struct.pack('<II',n,len(rules))+body
def decode(payload):
    tag=payload[0];raw=lzma.decompress(payload[1:])
    if tag==0:return raw
    if tag not in (1,2):raise ValueError('tag')
    n,r=struct.unpack_from('<II',raw)
    if n>32768 or r>256:raise ValueError('limits')
    body=raw[8:]
    if len(body)%2:raise ValueError('odd body')
    if tag==2:
        k=len(body)//2
        b=bytearray(len(body));b[::2]=body[:k];b[1::2]=body[k:];body=bytes(b)
    tokens=np.frombuffer(body,dtype='<u2')
    if len(tokens)<2*r:raise ValueError('rules')
    expansions=[bytes([i]) for i in range(256)]
    for j in range(r):
        x,y=map(int,tokens[2*j:2*j+2])
        if max(x,y)>=len(expansions):raise ValueError('forward ref')
        s=expansions[x]+expansions[y]
        if len(s)>n:raise ValueError('expansion')
        expansions.append(s)
    output=bytearray()
    for x in tokens[2*r:]:
        if int(x)>=len(expansions):raise ValueError('symbol')
        output.extend(expansions[int(x)])
        if len(output)>n:raise ValueError('length')
    if len(output)!=n:raise ValueError('length')
    return bytes(output)
m=json.loads((root/'corpora/manifest.json').read_text());rows=[]
a.out.parent.mkdir(parents=True,exist_ok=True)
with a.out.open('x') as f:
    def log(row):f.write(json.dumps(row)+'\n');f.flush()
    log(dict(type='meta',protocol='H02',python=platform.python_version(),numpy=np.__version__,platform=platform.platform(),cpu_affinity=sorted(os.sched_getaffinity(0)),xz_preset=5,script_sha256=sha(pathlib.Path(__file__).read_bytes())))
    for item in sorted(m,key=lambda x:(x['group'],x['path'])):
        g=item['group']
        if g not in ('synthetic','canterbury','silesia'):continue
        p=(root/item['path']).resolve();assert p.is_relative_to(root/'corpora')
        data=p.read_bytes();assert sha(data)==item['sha256']
        offset=(len(data)-32768)//2 if g=='silesia' else 0
        original=data[offset:offset+32768];n=len(original)
        t=time.process_time();baseline=xz(original);basecpu=time.process_time()-t
        direct=b'\0'+baseline
        assert decode(direct)==original
        candidates=[dict(name='direct',bytes=len(direct),rules=0,tokens=n,grammar_cpu_s=0.,encode_cpu_s=basecpu)]
        for budget,rules,seq,grammarcpu in states(original):
            for split in (False,True):
                t=time.process_time();raw=serialize(n,rules,seq,split);payload=bytes([2 if split else 1])+xz(raw);cpu=time.process_time()-t
                t=time.process_time();restored=decode(payload);decpu=time.process_time()-t
                if restored!=original:raise RuntimeError('roundtrip failure')
                candidates.append(dict(name=f'{budget}-'+('split' if split else 'interleaved'),bytes=len(payload),rules=len(rules),tokens=len(seq)+2*len(rules),sequence_tokens=len(seq),inner_bytes=len(raw),grammar_cpu_s=grammarcpu,encode_cpu_s=cpu,decode_cpu_s=decpu))
        best=min(candidates,key=lambda x:x['bytes'])
        bestgrammar=min(candidates[1:],key=lambda x:x['bytes'])
        row=dict(type='sample',group=g,path=item['path'],offset=offset,input_bytes=n,sha256=sha(original),file_sha256=item['sha256'],baseline=len(baseline),oracle=best['bytes'],best=best['name'],best_grammar=bestgrammar['bytes'],best_grammar_name=bestgrammar['name'],candidates=candidates)
        rows.append(row);log(row);print(g,p.name,n,row['baseline'],row['oracle'],row['best'],row['best_grammar'],flush=True)
    for g in ('synthetic','canterbury','silesia'):
        r=[x for x in rows if x['group']==g];base=sum(x['baseline'] for x in r);oracle=sum(x['oracle'] for x in r)
        result=dict(type='summary',group=g,samples=len(r),input_bytes=sum(x['input_bytes'] for x in r),baseline=base,oracle=oracle,best_grammar=sum(x['best_grammar'] for x in r),saving_percent=100*(base-oracle)/base,roundtrips=len(r)*7,grammar_wins=sum(x['best_grammar']<x['baseline'] for x in r),baseline_cpu=sum(x['candidates'][0]['encode_cpu_s'] for x in r),search_cpu=sum(max(c['grammar_cpu_s'] for c in x['candidates'])+sum(c['encode_cpu_s'] for c in x['candidates']) for x in r))
        log(result);print(json.dumps(result),flush=True)
