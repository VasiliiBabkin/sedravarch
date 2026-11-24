#!/usr/bin/env python3
"""H07: section-aware x86 BCJ and exact zlib recipe screening."""
import argparse,fcntl,hashlib,json,lzma,os,pathlib,re,shutil,struct,subprocess,tempfile,time,zlib
P=argparse.ArgumentParser();P.add_argument('--lab',type=pathlib.Path,required=True);P.add_argument('--out',type=pathlib.Path,required=True);a=P.parse_args();root=a.lab.resolve()
os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert shutil.disk_usage(root).free>=5*1024**3
def sha(b):return hashlib.sha256(b).hexdigest()
def xz(b,bcj=False,offset=0):
    return lzma.compress(b,format=lzma.FORMAT_XZ,check=lzma.CHECK_CRC64,filters=([{'id':lzma.FILTER_X86,'start_offset':offset} ] if bcj else [])+[{'id':lzma.FILTER_LZMA2,'preset':5}])
def call(args,**kw):return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,**kw).stdout
def fetch(url):
    with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h07-download-') as td:
        p=pathlib.Path(td)/'data'
        call(['curl','--fail','--silent','--show-error','--location','--proto','=https','--max-time','25','--max-filesize','8388608','-o',str(p),url])
        b=p.read_bytes();assert len(b)<=8388608;return b
def seven(b,work,bcj=False):
    with tempfile.TemporaryDirectory(dir=work,prefix='seven-') as td:
        d=pathlib.Path(td);(d/'input.bin').write_bytes(b)
        methods=['-m0=BCJ2','-m1=LZMA2','-m2=LZMA2','-m3=LZMA2','-mb0:1','-mb0s1:2','-mb0s2:3'] if bcj else ['-m0=LZMA2']
        t=time.process_time_ns();w=time.perf_counter_ns()
        call(['7z','a','-t7z','-mx=5','-mmt=1','-mtc=off','-mta=off','-mtm=off',*methods,'p.7z','input.bin'],cwd=d)
        wall=time.perf_counter_ns()-w;arc=(d/'p.7z').read_bytes()
        assert call(['7z','x','-so','-mmt=1','p.7z','input.bin'],cwd=d)==b
        return dict(bytes=len(arc),sha256=sha(arc),wall_ns=wall)
def sections(b):
    rr=[]
    if b[:2]==b'MZ':
        pe=struct.unpack_from('<I',b,60)[0];assert b[pe:pe+4]==b'PE\0\0'
        machine,n,_,_,_,opt,_=struct.unpack_from('<HHIIIHH',b,pe+4)
        assert machine in (0x14c,0x8664) and 0<n<=96
        start=pe+24+opt;assert start+40*n<=len(b)
        for i in range(n):
            s=start+40*i;size,off=struct.unpack_from('<II',b,s+16);flags=struct.unpack_from('<I',b,s+36)[0]
            if size and flags&0x20000000:rr.append((off,off+size))
    else:
        assert b[:4]==b'\x7fELF' and b[5]==1 and b[4] in (1,2)
        assert struct.unpack_from('<H',b,18)[0] in (3,62)
        if b[4]==2:
            start=struct.unpack_from('<Q',b,40)[0];ents,n=struct.unpack_from('<HH',b,58)
            assert ents>=64 and n and start+ents*n<=len(b)
            for i in range(n):
                s=start+i*ents;typ=struct.unpack_from('<I',b,s+4)[0];flags=struct.unpack_from('<Q',b,s+8)[0];off,size=struct.unpack_from('<QQ',b,s+24)
                if typ!=8 and size and flags&4:rr.append((off,off+size))
        else:
            start=struct.unpack_from('<I',b,32)[0];ents,n=struct.unpack_from('<HH',b,46)
            assert ents>=40 and n and start+ents*n<=len(b)
            for i in range(n):
                s=start+i*ents;typ,flags=struct.unpack_from('<II',b,s+4);off,size=struct.unpack_from('<II',b,s+16)
                if typ!=8 and size and flags&4:rr.append((off,off+size))
    spans=[];p=0
    for s,e in sorted(rr):
        assert p<=s<e<=len(b)
        if p<s:spans.append((p,s,False))
        spans.append((s,e,True));p=e
    if p<len(b):spans.append((p,len(b),False))
    return spans
def splitframe(b,spans,bcj):
    parts=[xz(b[s:e],bcj and exe,s) for s,e,exe in spans]
    return struct.pack('<4sIII',b'H07E',len(parts),len(b),zlib.crc32(b))+b''.join(struct.pack('<I',len(p))+p for p in parts)
def splitdecode(b):
    magic,n,size,crc=struct.unpack_from('<4sIII',b);assert magic==b'H07E' and n<=1000
    p=16;out=bytearray()
    for _ in range(n):
        k=struct.unpack_from('<I',b,p)[0];p+=4;out.extend(lzma.decompress(b[p:p+k]));p+=k
    assert p==len(b) and len(out)==size and zlib.crc32(out)==crc;return bytes(out)
def measured(fn,decode,b):
    t=time.process_time_ns();w=time.perf_counter_ns();p=fn();c=time.process_time_ns()-t;wall=time.perf_counter_ns()-w
    assert decode(p)==b;return dict(bytes=len(p),sha256=sha(p),cpu_ns=c,wall_ns=wall)
def exe(group,name,b,src,work):
    spans=sections(b)
    r={'plain':measured(lambda:xz(b),lzma.decompress,b),'whole-bcj':measured(lambda:xz(b,True),lzma.decompress,b),'section-plain':measured(lambda:splitframe(b,spans,False),splitdecode,b),'section-bcj':measured(lambda:splitframe(b,spans,True),splitdecode,b)}
    r['7z']=seven(b,work)
    try:r['7z-bcj2']=seven(b,work,True)
    except subprocess.CalledProcessError as e:r['7z-bcj2-error']=e.stderr.decode(errors='replace')[:500]
    base=min(r[k]['bytes'] for k in ('plain','whole-bcj','7z','7z-bcj2') if k in r)
    return dict(type='sample',group=group,name=name,source=src,input_bytes=len(b),sha256=sha(b),spans=spans,baseline=base,candidates=r,checks=sum('bytes' in v for v in r.values() if isinstance(v,dict)))
def recipe(b):
    out=bytearray();p=0;expanded=0;seen=0;matched=0;original_bytes=plain_bytes=0;hist={}
    def raw(s):
        if s:out.extend(struct.pack('<BI',0,len(s)));out.extend(s)
    for m in re.finditer(rb'\bstream\r?\n',b):
        i=m.end()
        if i<p or i+2>len(b):continue
        a,c=b[i:i+2]
        if a&15!=8 or a>>4>7 or (a*256+c)%31 or c&32:continue
        try:
            d=zlib.decompressobj();x=d.decompress(b[i:],8388609)
            if not d.eof or len(x)>8388608 or expanded+len(x)>33554432:continue
            end=len(b)-len(d.unused_data)
            if end<=i:continue
        except zlib.error:continue
        seen+=1;expanded+=len(x);old=b[i:end];hit=None
        for lev in range(10):
            for strat in range(5):
                z=zlib.compressobj(lev,zlib.DEFLATED,15,8,strat);v=z.compress(x)+z.flush()
                if v==old:hit=(lev,strat);break
            if hit:break
        if hit:
            raw(b[p:i]);out.extend(struct.pack('<BBBI',1,*hit,len(x)));out.extend(x);p=end;matched+=1;original_bytes+=len(old);plain_bytes+=len(x);hist[str(hit)]=hist.get(str(hit),0)+1
    raw(b[p:]);return struct.pack('<4sII',b'H07P',len(b),zlib.crc32(b))+xz(out),dict(seen=seen,matched=matched,expanded=expanded,matched_compressed_bytes=original_bytes,matched_plain_bytes=plain_bytes,recipes=hist)
def recipe_decode(b):
    magic,size,crc=struct.unpack_from('<4sII',b);assert magic==b'H07P'
    x=lzma.decompress(b[12:]);p=0;out=bytearray()
    while p<len(x):
        tag=x[p]
        if tag==0:
            n=struct.unpack_from('<I',x,p+1)[0];p+=5;assert p+n<=len(x);out.extend(x[p:p+n]);p+=n
        elif tag==1:
            lev,strat,n=struct.unpack_from('<BBI',x,p+1);p+=7;assert p+n<=len(x)
            z=zlib.compressobj(lev,zlib.DEFLATED,15,8,strat);out.extend(z.compress(x[p:p+n])+z.flush());p+=n
        else:raise ValueError('tag')
        assert len(out)<=size
    assert len(out)==size and zlib.crc32(out)==crc;return bytes(out)
def doc(group,name,b,src,work):
    r={'plain':measured(lambda:xz(b),lzma.decompress,b),'7z':seven(b,work)}
    with tempfile.TemporaryDirectory(dir=work,prefix='zstd-') as td:
        d=pathlib.Path(td);(d/'input').write_bytes(b)
        t=time.perf_counter_ns();c=call(['zstd','-q','-T1','-15','-c',str(d/'input')]);wall=time.perf_counter_ns()-t;(d/'packed').write_bytes(c)
        assert call(['zstd','-q','-d','-c',str(d/'packed')])==b
        r['zstd15']=dict(bytes=len(c),sha256=sha(c),wall_ns=wall)
    t=time.process_time_ns();w=time.perf_counter_ns();p,stats=recipe(b);cpu=time.process_time_ns()-t;wall=time.perf_counter_ns()-w
    assert recipe_decode(p)==b;r['recipe']=dict(bytes=len(p),sha256=sha(p),cpu_ns=cpu,wall_ns=wall)
    base=min(r[k]['bytes'] for k in ('plain','7z','zstd15'))
    return dict(type='sample',group=group,name=name,source=src,input_bytes=len(b),sha256=sha(b),baseline=base,candidates=r,stats=stats,checks=4)
def synthetic():
    x=(b'Qwerty data record 1234567890\n'*2048)
    z=zlib.compressobj(9,zlib.DEFLATED,15,8,zlib.Z_FIXED);b=z.compress(x)+z.flush()
    z=zlib.compressobj(6);c=z.compress(x[:len(x)//2])+z.flush(zlib.Z_SYNC_FLUSH)+z.compress(x[len(x)//2:])+z.flush()
    return b'%PDF-test-only\n'+b'\n'.join(b'stream\n'+s+b'\nendstream' for s in (zlib.compress(x,6),b,c))
a.out.parent.mkdir(parents=True,exist_ok=True);rows=[]
with a.out.open('x') as f:
    def log(r):f.write(json.dumps(r)+'\n');f.flush()
    def record(r):
        rows.append(r);log(r);print(r['group'],r['name'],r['input_bytes'],{k:v['bytes'] for k,v in r['candidates'].items() if isinstance(v,dict) and 'bytes' in v},r.get('stats',''),flush=True)
    log(dict(type='meta',protocol='H07',script_sha256=sha(pathlib.Path(__file__).read_bytes()),zlib=zlib.ZLIB_RUNTIME_VERSION,affinity=sorted(os.sched_getaffinity(0))))
    for name in ('git','python3','openssl','bash'):
        p=pathlib.Path('/usr/bin')/name
        if not p.exists():log(dict(type='skip',group='elf',name=name));continue
        record(exe('elf',name,p.read_bytes(),str(p),root/'tmp'))
    for name in ('t32','t64','w32','w64'):
        url='https://raw.githubusercontent.com/pypa/distlib/master/distlib/'+name+'.exe'
        try:b=fetch(url)
        except (subprocess.SubprocessError,OSError,AssertionError) as e:log(dict(type='skip',group='pe',name=name,error=str(e)));print('SKIP',name,flush=True);continue
        record(exe('pe',name,b,url,root/'tmp'))
    p=pathlib.Path('/usr/share/doc/shared-mime-info/shared-mime-info-spec.pdf')
    if p.exists():record(doc('pdf','shared-mime-info',p.read_bytes(),str(p),root/'tmp'))
    else:log(dict(type='skip',group='pdf',name=str(p)))
    try:
        tree=json.loads(fetch('https://api.github.com/repos/py-pdf/sample-files/git/trees/main?recursive=1'));rev=tree['sha'];log(dict(type='source',repo='py-pdf/sample-files',tree_sha=rev))
        # Resolve main to commit via API: tree SHA is not necessarily accepted by raw host.
        # use commit API and pin that commit's tree, not mutable main.
        commit=json.loads(fetch('https://api.github.com/repos/py-pdf/sample-files/commits/main'))
        rev=commit['sha'];tree=json.loads(fetch('https://api.github.com/repos/py-pdf/sample-files/git/trees/'+rev+'?recursive=1'));log(dict(type='source',repo='py-pdf/sample-files',commit=rev))
        paths=[r['path'] for r in tree['tree'] if r['type']=='blob' and r['path'].lower().endswith('.pdf')]
    except (subprocess.SubprocessError,OSError,AssertionError,KeyError,ValueError) as e:
        paths=[];rev='';log(dict(type='skip',group='pdf',name='repository tree',error=str(e)))
    from urllib.parse import quote
    for prefix in ('002','003','004','011','013','021','031'):
        found=sorted(p for p in paths if p.startswith(prefix+'-'))
        if not found:log(dict(type='skip',group='pdf',name=prefix));print('SKIP PDF',prefix,flush=True);continue
        url='https://raw.githubusercontent.com/py-pdf/sample-files/'+rev+'/'+quote(found[0],safe='/')
        try:b=fetch(url);assert b.startswith(b'%PDF')
        except (subprocess.SubprocessError,OSError,AssertionError) as e:log(dict(type='skip',group='pdf',name=prefix,error=str(e)));print('SKIP PDF',prefix,flush=True);continue
        record(doc('pdf',found[0],b,url,root/'tmp'))
    record(doc('synthetic','three-streams',synthetic(),'generated',root/'tmp'))
    for g in ('elf','pe','pdf','synthetic'):
        rr=[r for r in rows if r['group']==g]
        if not rr:continue
        b=sum(r['baseline'] for r in rr);key='section-bcj' if g in ('elf','pe') else 'recipe';s=sum(r['candidates'][key]['bytes'] for r in rr);o=sum(min(r['baseline'],r['candidates'][key]['bytes']) for r in rr)
        res=dict(type='summary',group=g,samples=len(rr),baseline=b,candidate=s,oracle=o,saving=100*(1-s/b),oracle_saving=100*(1-o/b),wins=sum(r['candidates'][key]['bytes']<r['baseline'] for r in rr),checks=sum(r['checks'] for r in rr),bcj2_complete=all('7z-bcj2' in r['candidates'] for r in rr) if g in ('elf','pe') else None)
        log(res);print(json.dumps(res),flush=True)
