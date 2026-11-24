#!/usr/bin/env python3
"""H06: bounded numeric transform screening, trusted experimental streams."""
import argparse, ctypes as C, ctypes.util, csv, fcntl, hashlib, io, json, lzma, math, os, pathlib, platform, shutil, struct, subprocess, tempfile, time, zlib
import numpy as np
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
HEAD='<4sBBBBBII';HS=struct.calcsize(HEAD);assert HS==17
PRED=('id','xor1','delta1','delta2','adaptive');SHUF=('none','byte','bit');BACK=('raw','zstd15','xz5')
def sha(x):return hashlib.sha256(x).hexdigest()
def dt(w):return np.dtype('<u'+str(w))
def compress(b,k):
    if k==0:return b
    if k==2:return lzma.compress(b,format=lzma.FORMAT_XZ,preset=5,check=lzma.CHECK_CRC64)
    cap=lib.ZSTD_compressBound(len(b));out=C.create_string_buffer(cap)
    n=lib.ZSTD_compress(out,cap,b,len(b),15)
    assert not lib.ZSTD_isError(n);return out.raw[:n]
def decompress(b,k,n):
    if k==0:return b
    if k==2:return lzma.decompress(b)
    out=C.create_string_buffer(n);m=lib.ZSTD_decompress(out,n,b,len(b))
    assert not lib.ZSTD_isError(m) and m==n;return out.raw
def residuals(x,w):
    p=np.zeros_like(x);p[1:]=x[:-1]
    pp=np.zeros_like(x);pp[2:]=x[:-2]
    def zz(r):return (r<<1) ^ (np.zeros_like(r)-(r>>(8*w-1)))
    return (x,x^p,zz(x-p),zz(x-p-p+pp))
def shuffle(b,w,s):
    if s==0:return b
    x=np.frombuffer(b,dtype=np.uint8).reshape(-1,w)
    if s==1:return x.T.copy().tobytes()
    return np.packbits(np.unpackbits(x,axis=1).T.reshape(-1)).tobytes()
def unshuffle(b,w,s,n):
    if s==0:return b
    if s==1:return np.frombuffer(b,dtype=np.uint8).reshape(w,n).T.copy().tobytes()
    return np.packbits(np.unpackbits(np.frombuffer(b,dtype=np.uint8)).reshape(w*8,n).T,axis=1).tobytes()
def score(x,w):
    b=np.unpackbits(x.view(np.uint8).reshape(-1,w),axis=1)
    p=b.mean(axis=0);q=p[(p>0)&(p<1)]
    return float((-q*np.log2(q)-(1-q)*np.log2(1-q)).sum()*len(x))
def adaptive(rs,w):
    tags=[];y=np.empty_like(rs[0])
    for i in range(0,len(y),256):
        j=min(i+256,len(y))
        k=min(range(4),key=lambda k:(score(rs[k][i:j],w),k))
        tags.append(k);y[i:j]=rs[k][i:j]
    return y,bytes(tags)
def inverse(r,w,p,tags):
    mask=(1<<(8*w))-1;prev=prev2=0;out=[]
    for i,v in enumerate(r.tolist()):
        k=tags[i//256] if p==4 else p
        if k==0:x=v
        elif k==1:x=v^prev
        else:
            d=(v>>1)^-(v&1)
            x=(d+(prev if k==2 else 2*prev-prev2))&mask
        out.append(x);prev2,prev=prev,x
    return np.asarray(out,dtype=dt(w))
def frame(original,w,k,p,s,scale,raw):
    return struct.pack(HEAD,b'H06A',w,k,p,s,scale,len(original)//w,zlib.crc32(original))+compress(raw,k)
def decode(b):
    magic,w,k,p,s,scale,n,crc=struct.unpack_from(HEAD,b);assert magic==b'H06A' and w in (2,4,8) and n<=16384
    nt=(n+255)//256 if p==4 else 0
    payload=decompress(b[HS:],k,n*w+nt);assert len(payload)==n*w+nt
    tags=payload[:nt];assert all(t<4 for t in tags)
    r=np.frombuffer(unshuffle(payload[nt:],w,s,n),dtype=dt(w))
    y=inverse(r,w,p,tags)
    if scale!=255:
        assert w==8 and scale<=6
        out=(y.view('<i8').astype('<f8')/(10**scale)).astype('<f8').tobytes()
    else:out=y.tobytes()
    assert len(out)==n*w and zlib.crc32(out)==crc
    return out
URLS={'ecg':'https://raw.githubusercontent.com/scipy/dataset-ecg/main/ecg.dat','ett':'https://raw.githubusercontent.com/zhouhaoyi/ETDataset/main/ETT-small/ETTh1.csv','m4':'https://raw.githubusercontent.com/Mcompetitions/M4-methods/master/Dataset/Train/Hourly-train.csv'}
def get(group):
    with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h06-') as tmp:
        p=pathlib.Path(tmp)/'source'
        subprocess.run(['curl','--fail','--location','--proto','=https','--max-time','35','--max-filesize','12582912','--silent','--show-error','-o',str(p),URLS[group]],check=True,timeout=40)
        b=p.read_bytes();assert 0<len(b)<=12582912
        src=dict(url=URLS[group],sha256=sha(b),bytes=len(b))
        arr=[]
        if group=='ecg':
            with np.load(io.BytesIO(b),allow_pickle=False) as f:x=f['ecg']
            x=x.reshape(-1);assert len(x)>=65536 and np.all(np.isfinite(x[:65536])) and np.all(x[:65536]==np.trunc(x[:65536])) and x[:65536].min()>=-32768 and x[:65536].max()<=32767
            for i in range(4):arr.append((f'window{i}',x[i*16384:(i+1)*16384].astype('<i2')))
        elif group=='ett':
            cols=['HUFL','HULL','MUFL','MULL','LUFL','LULL','OT'];r=csv.DictReader(io.StringIO(b.decode('utf-8-sig')))
            import itertools
            rows=list(itertools.islice(r,16384));assert len(rows)==16384
            for col in cols:
                v=np.asarray([float(x[col]) for x in rows],dtype='<f8');assert np.all(np.isfinite(v));arr.append((col,v))
        else:
            r=csv.reader(io.StringIO(b.decode('utf-8-sig')));next(r)
            for line in r:
                if len(line)<513 or any(not s.strip() or s.strip().lower() in ('na','nan') for s in line[1:513]):continue
                try:v=np.asarray([float(s) for s in line[1:513]],dtype='<f8')
                except ValueError:continue
                if not np.all(np.isfinite(v)):continue
                arr.append((line[0],v))
                if len(arr)==12:break
            assert len(arr)==12
        return src,arr
def synthetic():
    rng=np.random.default_rng(20261125);i=np.arange(16384,dtype=np.int32)
    return {'seed':20261125},[('random-i16',rng.integers(-32768,32768,len(i),dtype=np.int16).astype('<i2')),('linear-i32',(4*i+rng.integers(-2,3,len(i),dtype=np.int32)).astype('<i4')),('mixed-i32',np.concatenate((i[:8192]*3,rng.integers(-2**31,2**31,8192,dtype=np.int32))).astype('<i4')),('sin-f64',np.sin(i.astype('<f8')/100).astype('<f8')),('decimal-f64',(rng.integers(-10000,10000,len(i))/100).astype('<f8'))]
def measure(group,name,v,src):
    original=v.tobytes();w=v.dtype.itemsize;n=len(v);x=np.frombuffer(original,dtype=dt(w));t=time.process_time_ns();rs=residuals(x,w);pred_cpu=time.process_time_ns()-t
    cands=[]
    def trial(label,k,p,s,scale,raw,pre_ns=0):
        start=time.process_time_ns();b=frame(original,w,k,p,s,scale,raw);enc=time.process_time_ns()-start
        start=time.process_time_ns();out=decode(b);dec=time.process_time_ns()-start
        assert out==original
        cands.append(dict(name=label,bytes=len(b),sha256=sha(b),encode_cpu_ns=enc+pre_ns,decode_cpu_ns=dec))
    trial('raw',0,0,0,255,original)
    for p,r in enumerate(rs):
        for s in range(3):
            t=time.process_time_ns();raw=shuffle(r.tobytes(),w,s);cost=time.process_time_ns()-t
            for k in (1,2):trial(f'{PRED[p]}-{SHUF[s]}-{BACK[k]}',k,p,s,255,raw,cost+(pred_cpu if p else 0))
    t=time.process_time_ns();y,tags=adaptive(rs,w);raw=tags+shuffle(y.tobytes(),w,2);cost=time.process_time_ns()-t+pred_cpu
    for k in (1,2):trial('adaptive-'+BACK[k],k,4,2,255,raw,cost)
    scale=None
    if v.dtype.kind=='f':
        t=time.process_time_ns()
        for j in range(7):
            y=np.rint(v*(10**j))
            if not np.all(np.isfinite(y)) or np.any(np.abs(y)>2**53-1):continue
            yi=y.astype('<i8')
            if (yi.astype('<f8')/(10**j)).astype('<f8').tobytes()!=original:continue
            scale=j
            r=residuals(yi.view('<u8'),8)[2];raw=shuffle(r.tobytes(),8,2);cost=time.process_time_ns()-t
            for k in (1,2):trial('decimal-'+BACK[k],k,2,2,j,raw,cost)
            break
    by={r['name']:r['bytes'] for r in cands};fixed=min(cands[:25],key=lambda r:r['bytes']);base=min(by[k] for k in ('raw','id-none-zstd15','id-none-xz5'))
    return dict(type='sample',group=group,name=name,dtype=v.dtype.str,words=n,input_bytes=len(original),sha256=sha(original),source_sha256=src.get('sha256'),baseline=base,fixed=fixed['bytes'],fixed_name=fixed['name'],adaptive_zstd=by['adaptive-zstd15'],adaptive_xz=by['adaptive-xz5'],tags={str(i):tags.count(i) for i in range(4)},decimal_scale=scale,decimal_best=min(by[k] for k in by if k.startswith('decimal-')) if scale is not None else None,candidates=cands,checks=len(cands))
a.out.parent.mkdir(parents=True,exist_ok=True);rows=[]
with a.out.open('x') as f:
    def log(r):f.write(json.dumps(r)+'\n');f.flush()
    log(dict(type='meta',protocol='H06',python=platform.python_version(),numpy=np.__version__,zstd=lib.ZSTD_versionString().decode(),platform=platform.platform(),affinity=sorted(os.sched_getaffinity(0)),script_sha256=sha(pathlib.Path(__file__).read_bytes())))
    for g in ('synthetic','ecg','ett','m4'):
        try:src,arr=synthetic() if g=='synthetic' else get(g)
        except (OSError,ValueError,KeyError,AssertionError,subprocess.SubprocessError) as e:log(dict(type='skip',group=g,error=repr(e)));print('SKIP',g,repr(e),flush=True);continue
        log(dict(type='source',group=g,**src))
        for name,v in arr:
            r=measure(g,name,v,src);rows.append(r);log(r)
            print(g,name,r['input_bytes'],r['baseline'],r['fixed'],r['fixed_name'],r['adaptive_zstd'],r['adaptive_xz'],r['decimal_scale'],r['decimal_best'],flush=True)
    for g in ('synthetic','ecg','ett','m4'):
        rs=[r for r in rows if r['group']==g]
        if not rs:continue
        b=sum(r['baseline'] for r in rs);fixed=sum(r['fixed'] for r in rs);az=sum(r['adaptive_zstd'] for r in rs);ax=sum(r['adaptive_xz'] for r in rs)
        out=dict(type='summary',group=g,samples=len(rs),input_bytes=sum(r['input_bytes'] for r in rs),baseline=b,fixed=fixed,adaptive_zstd=az,adaptive_xz=ax,fixed_saving=100*(1-fixed/b),adaptive_saving=100*(1-az/fixed),decimal_applicable=sum(r['decimal_scale'] is not None for r in rs),checks=sum(r['checks'] for r in rs))
        log(out);print(json.dumps(out),flush=True)
