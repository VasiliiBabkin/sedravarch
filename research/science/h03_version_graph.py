#!/usr/bin/env python3
"""H03: version graph with independently seekable payloads; trusted experimental data only."""
import argparse,collections,fcntl,hashlib,itertools,json,lzma,os,pathlib,platform,shutil,struct,subprocess,tempfile,time,zlib
P=argparse.ArgumentParser()
P.add_argument('--lab',type=pathlib.Path,required=True)
P.add_argument('--out',type=pathlib.Path,required=True)
a=P.parse_args();root=a.lab.resolve()
os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert shutil.disk_usage(root).free>=5*1024**3
seven=shutil.which('7z');assert seven
families={'zstd':('facebook/zstd',['v1.5.5','v1.5.6','v1.5.7'],'lib/compress/zstd_compress.c'),'libpng':('pnggroup/libpng',['v1.6.43','v1.6.44','v1.6.45'],'pngread.c'),'curl':('curl/curl',['curl-8_10_1','curl-8_11_1','curl-8_12_1'],'lib/http.c'),'git':('git/git',['v2.45.0','v2.46.0','v2.47.0'],'diff.c')}
def sha(x):return hashlib.sha256(x).hexdigest()
def xz(x):return lzma.compress(x,format=lzma.FORMAT_XZ,check=lzma.CHECK_CRC64,preset=5)
def delta(base,data):
    idx={}
    for i in range(0,len(base)-15,4):
        k=base[i:i+16];hits=idx.setdefault(k,[])
        if len(hits)<8:hits.append(i)
    out=bytearray();p=lit=0
    def add(end):
        if end>lit:out.extend(struct.pack('<BI',0,end-lit));out.extend(data[lit:end])
    while p+16<=len(data):
        best=0;at=0
        for i in idx.get(data[p:p+16],[]):
            lo=16;hi=min(len(base)-i,len(data)-p)
            while lo<hi:
                mid=(lo+hi+1)//2
                if base[i:i+mid]==data[p:p+mid]:lo=mid
                else:hi=mid-1
            if lo>best:best=lo;at=i
        if best:
            add(p);out.extend(struct.pack('<BII',1,at,best));p+=best;lit=p
        else:p+=1
    add(len(data))
    return bytes(out)
def undelta(base,script,n):
    out=bytearray();p=0
    while p<len(script):
        tag=script[p];p+=1
        if tag==0:
            (k,)=struct.unpack_from('<I',script,p);p+=4
            if k==0 or p+k>len(script):raise ValueError('literal')
            out.extend(script[p:p+k]);p+=k
        elif tag==1:
            i,k=struct.unpack_from('<II',script,p);p+=8
            if k==0 or i+k>len(base):raise ValueError('copy')
            out.extend(base[i:i+k])
        else:raise ValueError('tag')
        if len(out)>n:raise ValueError('extent')
    if len(out)!=n:raise ValueError('length')
    return bytes(out)
def build(path,data,names,parents,payloads):
    with path.open('wb') as f:
        f.write(b'H03ARC1\0'+struct.pack('<I',len(data)))
        for i,(d,n,p) in enumerate(zip(data,names,parents)):
            b=n.encode();f.write(struct.pack('<H',len(b))+b+struct.pack('<iIII',p,len(d),len(payloads[i,p]),zlib.crc32(d)))
        for i,p in enumerate(parents):f.write(payloads[i,p])
def extract(path,member):
    reads=0;restored_bytes=0;cache={}
    with path.open('rb') as f:
        def read(n):
            nonlocal reads
            x=f.read(n);reads+=len(x)
            if len(x)!=n:raise ValueError('short read')
            return x
        if read(8)!=b'H03ARC1\0':raise ValueError('magic')
        count,=struct.unpack('<I',read(4));assert count==3
        rec=[]
        for i in range(count):
            k,=struct.unpack('<H',read(2));name=read(k).decode()
            p,n,s,c=struct.unpack('<iIII',read(16))
            assert -1<=p<i and n<=2*1024**2
            rec.append((name,p,n,s,c))
        start=f.tell();offsets=[]
        for _,_,_,s,_ in rec:offsets.append(start);start+=s
        assert start==path.stat().st_size
        def visit(i):
            nonlocal restored_bytes
            if i in cache:return cache[i]
            _,p,n,s,c=rec[i]
            f.seek(offsets[i]);raw=lzma.decompress(read(s))
            out=raw if p<0 else undelta(visit(p),raw,n)
            assert len(out)==n and zlib.crc32(out)==c
            restored_bytes+=len(out);cache[i]=out;return out
        out=visit(member)
    return out,reads,restored_bytes
def choose(payloads,n,D):
    best=None
    for ps in itertools.product(*(range(-1,i) for i in range(n))):
        depths=[]
        for p in ps:depths.append(0 if p<0 else depths[p]+1)
        if max(depths)>D:continue
        cost=sum(len(payloads[i,p]) for i,p in enumerate(ps))
        q=(cost,ps,depths)
        if best is None or q<best:best=q
    return best
def call(argv,cwd):
    t=time.perf_counter()
    r=subprocess.run(argv,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=90)
    return r.stdout,time.perf_counter()-t
def measure(group,data,source,work):
    n=len(data);names=[f'v{i+1}.bin' for i in range(n)]
    for name,d in zip(names,data):(work/name).write_bytes(d)
    payloads={};edges=[];t=time.process_time()
    for i,d in enumerate(data):
        for p in range(-1,i):
            start=time.process_time()
            raw=d if p<0 else delta(data[p],d)
            b=xz(raw);rest=lzma.decompress(b)
            assert (rest if p<0 else undelta(data[p],rest,len(d)))==d
            payloads[i,p]=b
            edges.append(dict(child=i,parent=p,script_bytes=len(raw),payload_bytes=len(b),cpu_s=time.process_time()-start))
    search_cpu=time.process_time()-t
    profiles={}
    for D in (0,1,2):
        cost,ps,depth=choose(payloads,n,D)
        arc=work/f'D{D}.h03';build(arc,data,names,ps,payloads)
        results=[]
        for i,d in enumerate(data):
            start=time.perf_counter();out,reads,expanded=extract(arc,i);elapsed=time.perf_counter()-start
            assert out==d
            results.append(dict(member=i,read_bytes=reads,reconstructed_bytes=expanded,wall_s=elapsed))
        profiles[f'D{D}']=dict(bytes=arc.stat().st_size,parents=ps,depths=depth,extract=results)
    for solid in (True,False):
        arc=work/('solid.7z' if solid else 'non-solid.7z')
        cmd=[seven,'a','-t7z','-m0=lzma2','-mx=5','-mmt=1','-ms='+('on' if solid else 'off'),'-mtc=off','-mta=off','-mtm=off',str(arc),*names]
        _,elapsed=call(cmd,work)
        results=[]
        for i,d in enumerate(data):
            out,secs=call([seven,'x','-so','-mmt=1',str(arc),names[i]],work)
            assert out==d
            results.append(dict(member=i,wall_s=secs))
        profiles['7z-solid' if solid else '7z-nonsolid']=dict(bytes=arc.stat().st_size,encode_wall_s=elapsed,extract=results)
    return dict(type='family',group=group,source=source,input_bytes=sum(map(len,data)),files=[dict(name=n,bytes=len(d),sha256=sha(d)) for n,d in zip(names,data)],unique=len(set(data)),edges=edges,search_cpu_s=search_cpu,profiles=profiles,checks=len(edges)+5*n)
a.out.parent.mkdir(parents=True,exist_ok=True)
rows=[]
with a.out.open('x') as f:
    def log(r):f.write(json.dumps(r)+'\n');f.flush()
    log(dict(type='meta',protocol='H03',python=platform.python_version(),platform=platform.platform(),affinity=sorted(os.sched_getaffinity(0)),script_sha256=sha(pathlib.Path(__file__).read_bytes()),seven_version=call([seven,'i'],root)[0].decode(errors='replace').splitlines()[:4]))
    for group in ['synthetic',*families]:
        with tempfile.TemporaryDirectory(prefix='h03-',dir=root/'tmp') as tmp:
            work=pathlib.Path(tmp);data=[];source=[]
            if group=='synthetic':
                for i in range(1,4):
                    p=root/'corpora/versions'/f'v{i}.bin';d=p.read_bytes();data.append(d);source.append(str(p.relative_to(root)))
            else:
                repo,tags,p=families[group]
                try:
                    for i,tag in enumerate(tags):
                        url=f'https://raw.githubusercontent.com/{repo}/{tag}/{p}';dest=work/f'download{i}'
                        subprocess.run(['curl','--fail','--location','--proto','=https','--max-time','15','--max-filesize','2097152','--silent','--show-error','-o',str(dest),url],check=True,timeout=20)
                        d=dest.read_bytes();assert 0<len(d)<=2097152
                        data.append(d);source.append(url)
                except (subprocess.SubprocessError,OSError,AssertionError) as e:
                    log(dict(type='skip',group=group,reason=str(e),sources=source));print('SKIP',group,str(e),flush=True);continue
            r=measure(group,data,source,work);rows.append(r);log(r)
            print(group,r['input_bytes'],r['unique'],{k:v['bytes'] for k,v in r['profiles'].items()},'parents',r['profiles']['D1']['parents'],'checks',r['checks'],flush=True)
    real=[r for r in rows if r['group']!='synthetic'];keys=['D0','D1','D2','7z-solid','7z-nonsolid']
    totals={k:sum(r['profiles'][k]['bytes'] for r in real) for k in keys}
    summary=dict(type='summary',real_families=len(real),totals=totals,checks=sum(r['checks'] for r in rows),wins=sum(r['profiles']['D1']['bytes']<r['profiles']['7z-solid']['bytes'] for r in real),saving_percent=100*(1-totals['D1']/totals['7z-solid']) if real else None)
    summary['gate_pass']=len(real)==4 and summary['wins']>=2 and summary['saving_percent']>=10
    log(summary);print(json.dumps(summary),flush=True)
