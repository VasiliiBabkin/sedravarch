#!/usr/bin/env python3
"""H08: indexed page-based deduplication versus Git pack and 7z."""
import argparse,collections,fcntl,hashlib,json,lzma,os,pathlib,random,shutil,statistics,struct,subprocess,sys,tempfile,time,zlib
def sha(b):return hashlib.sha256(b).hexdigest()
def table():
    r=random.Random(20261124);return [r.getrandbits(64) for _ in range(256)]
GEAR=table()
def chunks(b,cdc):
    if not cdc:
        for i in range(0,len(b),4096):yield b[i:i+4096]
    else:
        h=0;start=0
        for i,x in enumerate(b,1):
            h=((h<<1)+GEAR[x])&((1<<64)-1)
            if i-start>=8192 or (i-start>=1024 and h&4095==0):
                yield b[start:i];start=i;h=0
        if start<len(b):yield b[start:]
def build(path,files,cdc,single):
    unique=[];by={};records=[]
    for name,b in files:
        refs=[]
        for c in chunks(b,cdc):
            h=sha(c);i=by.get(h)
            if i is None:i=len(unique);by[h]=i;unique.append(c)
            else:assert unique[i]==c
            refs.append(i)
        records.append((name,len(b),zlib.crc32(b),refs))
    pages=[];cur=bytearray();entries=[]
    for c in unique:
        if cur and (single or len(cur)+len(c)>32768):pages.append(bytes(cur));cur.clear()
        entries.append((len(pages),len(cur),len(c)));cur.extend(c)
    if cur:pages.append(bytes(cur))
    packed=[lzma.compress(p,preset=5,check=lzma.CHECK_CRC64) for p in pages]
    idx=bytearray(struct.pack('<III',len(pages),len(entries),len(records)))
    for p in packed:idx.extend(struct.pack('<I',len(p)))
    for e in entries:idx.extend(struct.pack('<III',*e))
    for name,n,crc,refs in records:
        key=name.encode();idx.extend(struct.pack('<H',len(key))+key+struct.pack('<III',n,crc,len(refs)))
        idx.extend(struct.pack('<'+'I'*len(refs),*refs))
    index=zlib.compress(idx,9)
    with path.open('wb') as f:
        f.write(b'H08A'+struct.pack('<I',len(index))+index)
        for p in packed:f.write(p)
    return dict(bytes=path.stat().st_size,index_bytes=len(index)+8,unique_chunks=len(unique),total_chunks=sum(len(r[3]) for r in records),pages=len(pages),unique_raw=sum(map(len,unique)))
def extract(path,name):
    readbytes=0
    with path.open('rb') as f:
        def read(n):
            nonlocal readbytes
            b=f.read(n);assert len(b)==n;readbytes+=n;return b
        magic,n=struct.unpack('<4sI',read(8));assert magic==b'H08A'
        idx=zlib.decompress(read(n));p=0
        def take(fmt):
            nonlocal p
            v=struct.unpack_from(fmt,idx,p);p+=struct.calcsize(fmt);return v
        np,nc,nf=take('<III');assert np<=100000 and nc<=100000 and nf<=1000
        sizes=[take('<I')[0] for _ in range(np)];entries=[take('<III') for _ in range(nc)]
        rec={}
        for _ in range(nf):
            k,=take('<H');nm=idx[p:p+k].decode();p+=k;n,crc,count=take('<III');refs=take('<'+'I'*count);rec[nm]=(n,crc,refs)
        assert p==len(idx)
        offsets=[];off=f.tell()
        for s in sizes:offsets.append(off);off+=s
        assert off==path.stat().st_size
        n,crc,refs=rec[name];cache={};out=bytearray();expanded=0
        for i in refs:
            j,o,k=entries[i]
            if j not in cache:
                f.seek(offsets[j]);cache[j]=lzma.decompress(read(sizes[j]));expanded+=len(cache[j])
            v=cache[j][o:o+k];assert len(v)==k;out.extend(v)
        assert len(out)==n and zlib.crc32(out)==crc
        return bytes(out),readbytes,expanded
def call(argv,cwd=None,inp=None):
    return subprocess.run(argv,cwd=cwd,input=inp,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=45).stdout
def buildgit(work,files):
    src=work/'source.git';dest=work/'packed.git'
    call(['git','init','--bare','--object-format=sha1',str(src)])
    call(['git','init','--bare','--object-format=sha1',str(dest)])
    ids=[];mapping=bytearray(struct.pack('<I',len(files)))
    for name,b in files:
        oid=call(['git','--git-dir='+str(src),'hash-object','-w','--stdin'],inp=b).strip().decode()
        ids.append(oid);key=name.encode();mapping.extend(struct.pack('<H',len(key))+key+bytes.fromhex(oid))
    path=dest/'objects'/'pack'/'data'
    packid=call(['git','--git-dir='+str(src),'pack-objects','--window=32','--depth=2','--threads=1','--compression=6','--no-reuse-delta','--no-reuse-object','--delta-base-offset',str(path)],inp=('\n'.join(dict.fromkeys(ids))+'\n').encode()).strip().decode()
    pack=path.with_name('data-'+packid+'.pack');idx=path.with_name('data-'+packid+'.idx')
    assert pack.exists() and idx.exists()
    m=work/'git.map';m.write_bytes(mapping)
    # Parse actual serialized mapping and verify it is complete.
    p=4;decoded={};n=struct.unpack_from('<I',m.read_bytes())[0];raw=m.read_bytes()
    for _ in range(n):
        k,=struct.unpack_from('<H',raw,p);p+=2;nm=raw[p:p+k].decode();p+=k;decoded[nm]=raw[p:p+20].hex();p+=20
    assert p==len(raw) and len(decoded)==len(files)
    shutil.rmtree(src)
    return dict(bytes=pack.stat().st_size+idx.stat().st_size+m.stat().st_size,pack_bytes=pack.stat().st_size,idx_bytes=idx.stat().st_size,map_bytes=m.stat().st_size,unique_objects=len(set(ids))),dest,decoded
def measure(group,files,sources,work):
    names=[n for n,b in files]
    for n,b in files:(work/n).write_bytes(b)
    profiles={};cmds={};own={}
    for name,cdc,single in [('fixed-page32',False,False),('cdc-page32',True,False),('cdc-single',True,True)]:
        p=work/(name+'.h08');t=time.perf_counter_ns();c=time.process_time_ns();r=build(p,files,cdc,single)
        r.update(encode_wall_ns=time.perf_counter_ns()-t,encode_cpu_ns=time.process_time_ns()-c);profiles[name]=r;own[name]=p
        cmds[name]=lambda n,p=p:[sys.executable,str(pathlib.Path(__file__).resolve()),'--extract',str(p),n]
    for solid in (True,False):
        name='7z-solid' if solid else '7z-nonsolid';p=work/(name+'.7z');t=time.perf_counter_ns()
        call(['7z','a','-t7z','-m0=lzma2','-mx=5','-mmt=1','-ms='+('on' if solid else 'off'),'-mtc=off','-mta=off','-mtm=off',str(p),*names],cwd=work)
        profiles[name]=dict(bytes=p.stat().st_size,encode_wall_ns=time.perf_counter_ns()-t)
        cmds[name]=lambda n,p=p:['7z','x','-so','-mmt=1',str(p),n]
    t=time.perf_counter_ns();r,dest,m=buildgit(work,files);r['encode_wall_ns']=time.perf_counter_ns()-t;profiles['git-pack']=r
    cmds['git-pack']=lambda n:['git','--git-dir='+str(dest),'cat-file','blob',m[n]]
    for r in profiles.values():r['extract']=[]
    checks=0
    for n,b in files:
        results={k:[] for k in profiles}
        for rep in range(3):
            order=list(profiles);random.Random(n+str(rep)).shuffle(order)
            for k in order:
                t=time.perf_counter_ns();out=call(cmds[k](n),cwd=work);elapsed=time.perf_counter_ns()-t
                assert out==b;checks+=1;results[k].append(elapsed)
        for k in profiles:
            r=dict(name=n,requested_bytes=len(b),wall_ns=results[k])
            if k in own:
                out,rb,exp=extract(own[k],n);assert out==b;checks+=1
                r.update(read_bytes=rb,decoded_bytes=exp)
            profiles[k]['extract'].append(r)
    for k,r in profiles.items():
        r['extract_median_sum_ns']=sum(statistics.median(e['wall_ns']) for e in r['extract'])
        if k in own:
            r['read_fraction']=sum(e['read_bytes'] for e in r['extract'])/(len(files)*r['bytes'])
            r['amplification']=sum(e['decoded_bytes'] for e in r['extract'])/sum(len(b) for n,b in files)
    r=profiles['cdc-page32'];ratio=r['bytes']/min(profiles['7z-solid']['bytes'],profiles['git-pack']['bytes'])
    return dict(type='family',group=group,files=[dict(name=n,bytes=len(b),sha256=sha(b),source=s) for (n,b),s in zip(files,sources)],input_bytes=sum(len(b) for n,b in files),unique_versions=len({sha(b) for n,b in files}),profiles=profiles,checks=checks,ratio=ratio,gate_a=ratio<=1.1 and r['read_fraction']<=.35 and r['amplification']<=2,gate_b=ratio<=1.1 and all(r['extract_median_sum_ns']<=.7*profiles[k]['extract_median_sum_ns'] for k in ('7z-solid','git-pack')))
def main():
    p=argparse.ArgumentParser();p.add_argument('--lab',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();root=a.lab.resolve()
    os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);assert shutil.disk_usage(root).free>=5*1024**3
    groups={'zlib':('madler/zlib','inflate.c',['v'+x for x in ('1.2.3','1.2.4','1.2.5','1.2.6','1.2.7','1.2.8','1.2.9','1.2.11','1.2.12','1.2.13','1.3','1.3.1')]),'libpng':('pnggroup/libpng','pngwrite.c',[f'v1.6.{i}' for i in range(30,42)]),'git':('git/git','read-cache.c',[f'v2.{i}.0' for i in range(30,42)])}
    a.out.parent.mkdir(parents=True,exist_ok=True);rows=[]
    with a.out.open('x') as f:
        def log(r):f.write(json.dumps(r)+'\n');f.flush()
        log(dict(type='meta',protocol='H08',script_sha256=sha(pathlib.Path(__file__).read_bytes()),python=sys.version,git=call(['git','--version']).decode().strip(),affinity=sorted(os.sched_getaffinity(0))))
        for g in ('synthetic',*groups):
            with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h08-') as td:
                work=pathlib.Path(td);files=[];sources=[]
                if g=='synthetic':
                    rng=random.Random(20261124);b=bytearray(rng.randbytes(131072))
                    for i in range(12):
                        if i:
                            for _ in range(64):b[rng.randrange(len(b))]=rng.randrange(256)
                            pos=rng.randrange(len(b)+1);b[pos:pos]=rng.randbytes(31)
                        files.append((f'v{i+1:02}.bin',bytes(b)));sources.append('seed 20261124')
                else:
                    repo,path,tags=groups[g]
                    try:
                        for i,tag in enumerate(tags):
                            url=f'https://raw.githubusercontent.com/{repo}/{tag}/{path}';p=work/'download'
                            call(['curl','--fail','--silent','--show-error','--location','--proto','=https','--max-time','15','--max-filesize','2097152','-o',str(p),url])
                            b=p.read_bytes();assert 0<len(b)<=2097152
                            files.append((f'v{i+1:02}.bin',b));sources.append(url)
                    except (OSError,AssertionError,subprocess.SubprocessError) as e:
                        log(dict(type='skip',group=g,error=repr(e),completed=len(files)));print('SKIP',g,len(files),repr(e),flush=True);continue
                print('BENCH',g,len(files),flush=True)
                r=measure(g,files,sources,work);rows.append(r);log(r)
                print(g,'bytes',{k:v['bytes'] for k,v in r['profiles'].items()},'gate',r['gate_a'],r['gate_b'],'checks',r['checks'],flush=True)
        rr=[r for r in rows if r['group']!='synthetic'];summary=dict(type='summary',families=len(rr),checks=sum(r['checks'] for r in rows),gate_a=len(rr)==3 and all(r['gate_a'] for r in rr),gate_b=len(rr)==3 and all(r['gate_b'] for r in rr))
        log(summary);print(json.dumps(summary),flush=True)
if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--extract':
        sys.stdout.buffer.write(extract(pathlib.Path(sys.argv[2]),sys.argv[3])[0])
    else:main()
