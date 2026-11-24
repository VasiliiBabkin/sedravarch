#!/usr/bin/env python3
"""H04: bounded binary-context models and fixed-share mixture, actual arithmetic streams."""
import argparse, collections, fcntl, hashlib, json, lzma, math, os, pathlib, platform, shutil, struct, subprocess, tempfile, time, zlib
P=argparse.ArgumentParser();P.add_argument('--lab',type=pathlib.Path,required=True);P.add_argument('--out',type=pathlib.Path,required=True)
a=P.parse_args();root=a.lab.resolve();os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert shutil.disk_usage(root).free>=5*1024**3
Q=32768; MASK=2**32-1; HALF=2**31; QUARTER=2**30; THREE=3*QUARTER
ORDERS=(0,1,2,4); MASKS=tuple((1<<(8*k))-1 for k in ORDERS)
def sha(d):return hashlib.sha256(d).hexdigest()
class Model:
    def __init__(self,idx):
        self.masks=MASKS if idx==4 else (MASKS[idx],)
        self.counts=[([0]*65536,[0]*65536) for _ in self.masks]
        self.w=[16384]*4 if idx==4 else None
        self.history=0;self.prefix=1
    def predict(self):
        keys=[];probs=[]
        for m,(zeros,ones) in zip(self.masks,self.counts):
            key=((((self.history&m)*257+self.prefix)*2654435761)&MASK)>>16
            n0=zeros[key];n1=ones[key];p=max(1,min(Q-1,((2*n1+1)*Q)//(2*(n0+n1)+2)))
            keys.append(key);probs.append(p)
        self.keys=keys;self.probs=probs
        if self.w is None:return probs[0]
        return max(1,min(Q-1,sum(w*p for w,p in zip(self.w,probs))//sum(self.w)))
    def update(self,b):
        for key,(zeros,ones) in zip(self.keys,self.counts):
            if b:ones[key]+=1
            else:zeros[key]+=1
            if zeros[key]+ones[key]>=4096:zeros[key]//=2;ones[key]//=2
        if self.w is not None:
            weighted=[w*(p if b else Q-p) for w,p in zip(self.w,self.probs)]
            s=sum(weighted);self.w=[64+65280*v//s for v in weighted]
        self.prefix=2*self.prefix+b
        if self.prefix>=256:self.history=((self.history<<8)|(self.prefix-256))&MASK;self.prefix=1
def encode(data,idx):
    m=Model(idx);lo=0;hi=MASK;pending=0;buf=bytearray();acc=nb=0;loss=0.
    def emit(b):
        nonlocal acc,nb
        acc=(acc<<1)|b;nb+=1
        if nb==8:buf.append(acc);acc=nb=0
    def flush(b):
        nonlocal pending
        emit(b)
        for _ in range(pending):emit(1-b)
        pending=0
    for byte in data:
        for shift in range(7,-1,-1):
            b=(byte>>shift)&1;p=m.predict();loss-=math.log2((p if b else Q-p)/Q)
            cut=lo+((hi-lo+1)*(Q-p)//Q)-1
            if b:lo=cut+1
            else:hi=cut
            while True:
                if hi<HALF:flush(0)
                elif lo>=HALF:flush(1);lo-=HALF;hi-=HALF
                elif lo>=QUARTER and hi<THREE:pending+=1;lo-=QUARTER;hi-=QUARTER
                else:break
                lo<<=1;hi=(hi<<1)|1
            m.update(b)
    pending+=1;flush(0 if lo<QUARTER else 1)
    if nb:buf.append(acc<<(8-nb))
    return struct.pack('<4sBII',b'H04A',idx,len(data),zlib.crc32(data))+bytes(buf),loss
def decode(stream):
    magic,idx,n,crc=struct.unpack_from('<4sBII',stream);assert magic==b'H04A' and idx<=4 and n<=8192
    payload=stream[13:];pos=0
    def read():
        nonlocal pos
        b=((payload[pos>>3]>>(7-(pos&7)))&1) if pos<8*len(payload) else 0
        pos+=1;return b
    lo=0;hi=MASK;val=0
    for _ in range(32):val=(val<<1)|read()
    m=Model(idx);out=bytearray()
    for _ in range(n):
        byte=0
        for _ in range(8):
            p=m.predict();cut=lo+((hi-lo+1)*(Q-p)//Q)-1
            b=int(val>cut)
            if b:lo=cut+1
            else:hi=cut
            while True:
                if hi<HALF:pass
                elif lo>=HALF:lo-=HALF;hi-=HALF;val-=HALF
                elif lo>=QUARTER and hi<THREE:lo-=QUARTER;hi-=QUARTER;val-=QUARTER
                else:break
                lo<<=1;hi=(hi<<1)|1;val=(val<<1)|read()
            byte=2*byte+b;m.update(b)
        out.append(byte)
    assert zlib.crc32(out)==crc
    return bytes(out)
def ppmd(data):
    with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h04-') as td:
        d=pathlib.Path(td);(d/'input.bin').write_bytes(data);arc=d/'p.7z'
        t=time.perf_counter()
        subprocess.run(['7z','a','-t7z','-m0=PPMd','-mx=5','-mmt=1','-mtc=off','-mta=off','-mtm=off',str(arc),'input.bin'],cwd=d,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        sec=time.perf_counter()-t
        restored=subprocess.run(['7z','x','-so','-mmt=1',str(arc),'input.bin'],cwd=d,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30).stdout
        assert restored==data
        return arc.stat().st_size,sec
manifest=json.loads((root/'corpora/manifest.json').read_text());rows=[]
a.out.parent.mkdir(parents=True,exist_ok=True)
with a.out.open('x') as f:
    def log(x):f.write(json.dumps(x)+'\n');f.flush()
    log(dict(type='meta',protocol='H04',python=platform.python_version(),platform=platform.platform(),affinity=sorted(os.sched_getaffinity(0)),script_sha256=sha(pathlib.Path(__file__).read_bytes()),orders=ORDERS,table_size=65536,prob_total=Q,seven_version=subprocess.check_output(['7z','i']).decode(errors='replace').splitlines()[:4]))
    for item in sorted(manifest,key=lambda x:(x['group'],x['path'])):
        group=item['group']
        if group not in ('synthetic','canterbury','silesia'):continue
        p=(root/item['path']).resolve();assert p.is_relative_to(root/'corpora')
        data=p.read_bytes();assert sha(data)==item['sha256']
        offset=(len(data)-8192)//2 if group=='silesia' else 0
        orig=data[offset:offset+8192];candidates=[]
        for idx,name in enumerate(('order0','order1','order2','order4','mixture')):
            t=time.process_time();stream,loss=encode(orig,idx);enc=time.process_time()-t
            t=time.process_time();rest=decode(stream);dec=time.process_time()-t
            assert rest==orig
            candidates.append(dict(name=name,bytes=len(stream),loss_bits=loss,encode_cpu_s=enc,decode_cpu_s=dec))
        t=time.process_time();xz=lzma.compress(orig,format=lzma.FORMAT_XZ,check=lzma.CHECK_CRC64,preset=5);xz_cpu=time.process_time()-t
        assert lzma.decompress(xz)==orig
        pb,pt=ppmd(orig)
        r=dict(type='sample',group=group,path=item['path'],offset=offset,input_bytes=len(orig),sha256=sha(orig),file_sha256=item['sha256'],xz=len(xz),xz_encode_cpu_s=xz_cpu,ppmd=pb,ppmd_encode_wall_s=pt,strong=min(len(xz),pb),candidates=candidates,oracle=min(c['bytes'] for c in candidates))
        rows.append(r);log(r);print(group,p.name,len(orig),len(xz),pb,[c['bytes'] for c in candidates],flush=True)
    for g in ('synthetic','canterbury','silesia'):
        rs=[r for r in rows if r['group']==g]
        sizes={name:sum(r['candidates'][i]['bytes'] for r in rs) for i,name in enumerate(('order0','order1','order2','order4','mixture'))}
        strong=sum(r['strong'] for r in rs);fixed=min(sizes[n] for n in ('order0','order1','order2','order4'))
        result=dict(type='summary',group=g,samples=len(rs),input_bytes=sum(r['input_bytes'] for r in rs),xz=sum(r['xz'] for r in rs),ppmd=sum(r['ppmd'] for r in rs),strong=strong,sizes=sizes,oracle=sum(r['oracle'] for r in rs),fixed_best=fixed,mixture_saving_strong=100*(1-sizes['mixture']/strong),mixture_saving_fixed=100*(1-sizes['mixture']/fixed),checks=7*len(rs),model_cpu={name:sum(r['candidates'][i]['encode_cpu_s'] for r in rs) for i,name in enumerate(('order0','order1','order2','order4','mixture'))})
        log(result);print(json.dumps(result),flush=True)
