#!/usr/bin/env python3
"""H07b2: exact recipes vs equal-length XOR corrections, Precomp control."""
import argparse,fcntl,hashlib,io,json,lzma,os,pathlib,re,resource,shutil,struct,subprocess,tempfile,time,zipfile,zlib
from urllib.parse import quote
P=argparse.ArgumentParser();P.add_argument('--lab',type=pathlib.Path,required=True);P.add_argument('--out',type=pathlib.Path,required=True);a=P.parse_args();root=a.lab.resolve()
os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert shutil.disk_usage(root).free>=5*1024**3
precomp=root/'experiments/h07b2/precomp'
def sha(b):return hashlib.sha256(b).hexdigest()
assert sha(precomp.read_bytes())=='6a5289ba81ea658e8e7984bf32791635f53b8e7cee4aafc26b853c7cd5b018f8'
def xz(b):return lzma.compress(b,preset=5,check=lzma.CHECK_CRC64)
def limits():
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))
def call(args,cwd=None,ok=(0,)):
    r=subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,preexec_fn=limits)
    if r.returncode not in ok:raise RuntimeError(str(r.returncode)+': '+r.stderr[-500:].decode(errors='replace')+' '+r.stdout[-500:].decode(errors='replace'))
    return r.stdout
T='tika-parsers/tika-parsers-standard/tika-parsers-standard-modules/'
M=T+'tika-parser-microsoft-module/src/test/resources/test-documents/'
PDF=T+'tika-parser-pdf-module/src/test/resources/test-documents/'
TIKA='https://raw.githubusercontent.com/apache/tika/823ec17c0817ffcb09fba3a6905abcdeb4373031/'
PNG='https://raw.githubusercontent.com/pnggroup/libpng/e88e1735a26788df76a570c59d1183c883e71401/'
SOURCES={
 'pdf':[(TIKA,PDF+p) for p in ('testPDF_Version.10.x.pdf','testPDF_rotated.pdf','testPDF_AdobeIllustrator.pdf')],
 'docx':[(TIKA,M+p) for p in ('footnotes.docx','testWORD_3imgs.docx','testWORD_2006ml.docx')],
 'xlsx':[(TIKA,M+p) for p in ('testEXCEL_supSub.xlsx','testEXCEL_headers_footers.xlsx')]+[(TIKA,'tika-server/tika-server-standard/src/test/resources/test-documents/pic.xlsx')],
 'zip':[(TIKA,T+'tika-parser-miscoffice-module/src/test/resources/test-documents/testOpenOfficeInAZip.zip'),(TIKA,T+'tika-parser-pkg-module/src/test/resources/test-documents/test-documents.zip'),(TIKA,T+'tika-parser-pkg-module/src/test/resources/test-documents/moby.zip')],
 'png':[(PNG,p) for p in ('contrib/pngsuite/ibasn6a16.png','pngtest.png','contrib/gregbook/toucan.png')]}
MAX=2*1024**2
def inflate(c,mode):
    d=zlib.decompressobj(mode);p=d.decompress(c,MAX+1)
    if not d.eof or len(p)>MAX:return None
    return p,len(c)-len(d.unused_data)
def wrap(c,lengths):
    if not lengths:return c
    out=bytearray();i=0
    for n in lengths:
        v=c[i:i+n];assert len(v)==n
        out.extend(struct.pack('>I',n)+b'IDAT'+v+struct.pack('>I',zlib.crc32(b'IDAT'+v)));i+=n
    assert i==len(c);return bytes(out)
def spans(b,g):
    rr=[]
    if g=='pdf':
        for m in re.finditer(rb'\bstream\r?\n',b):
            i=m.end()
            if i+2>len(b):continue
            a,c=b[i:i+2]
            if a&15!=8 or a>>4>7 or (a*256+c)%31 or c&32:continue
            try:r=inflate(b[i:],15)
            except zlib.error:continue
            if r:
                p,n=r;rr.append((i,i+n,b[i:i+n],p,15,[]))
    elif g in ('zip','docx','xlsx'):
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            for v in z.infolist():
                if v.compress_type!=8 or v.flag_bits&1 or v.file_size>MAX:continue
                o=v.header_offset
                if b[o:o+4]!=b'PK\x03\x04' or o+30>len(b):continue
                n,e=struct.unpack_from('<HH',b,o+26);i=o+30+n+e;j=i+v.compress_size
                if j>len(b):continue
                try:r=inflate(b[i:j],-15)
                except zlib.error:continue
                if r and r[1]==j-i and len(r[0])==v.file_size and zlib.crc32(r[0])==v.CRC:rr.append((i,j,b[i:j],r[0],-15,[]))
    elif g=='png':
        assert b[:8]==b'\x89PNG\r\n\x1a\n'
        i=8;parts=[];start=None
        while i+12<=len(b):
            n=struct.unpack_from('>I',b,i)[0];typ=b[i+4:i+8];j=i+n+12
            assert j<=len(b)
            if typ==b'IDAT':
                if start is None:start=i
                parts.append(b[i+8:i+8+n])
            elif parts:
                c=b''.join(parts);lengths=list(map(len,parts))
                try:r=inflate(c,15)
                except zlib.error:r=None
                if r and r[1]==len(c) and wrap(c,lengths)==b[start:i]:rr.append((start,i,c,r[0],15,lengths))
                parts=[];start=None
            i=j
            if typ==b'IEND':break
    out=[];end=total=0
    for r in sorted(rr,key=lambda x:x[0]):
        if r[0]<end or total+len(r[3])>16*1024**2:continue
        out.append(r);end=r[1];total+=len(r[3])
    return out
def raw(b):return struct.pack('<BI',0,len(b))+b
def recompress(p,mode,lev,strat):
    z=zlib.compressobj(lev,zlib.DEFLATED,mode,8,strat);return z.compress(p)+z.flush()
def rec(p,c,mode,lev,strat,lengths,mask=None):
    return struct.pack('<BBBBBIII',1 if mask is None else 2,int(bool(lengths)),0 if mode==15 else 1,lev,strat,len(p),len(c),len(lengths))+b''.join(struct.pack('<I',x) for x in lengths)+p+(mask or b'')
def recipes(b,rr):
    exact=bytearray();patch=bytearray();i=0;stats=dict(found=len(rr),exact_match=0,patch_possible=0,exact_selected=0,patch_selected=0,matched_bytes=0,patch_nonzero=0)
    for s,e,c,p,mode,lengths in rr:
        if s>i:exact.extend(raw(b[i:s]));patch.extend(raw(b[i:s]))
        original=raw(b[s:e]);chosen=original;best=None;hit=None
        for lev in range(10):
            for strat in range(5):
                v=recompress(p,mode,lev,strat)
                if v==c:hit=(lev,strat);break
                if len(v)==len(c):
                    mask=bytes(x^y for x,y in zip(v,c));score=len(mask)-mask.count(0)
                    if best is None or score<best[0]:best=(score,lev,strat,mask)
            if hit:break
        if hit:
            stats['exact_match']+=1;stats['matched_bytes']+=len(c)
            trial=rec(p,c,mode,*hit,lengths)
            if len(xz(trial))<len(xz(original)):chosen=trial;stats['exact_selected']+=1
        exact.extend(chosen)
        if not hit and best:
            stats['patch_possible']+=1;score,lev,strat,mask=best
            trial=rec(p,c,mode,lev,strat,lengths,mask)
            if len(xz(trial))<len(xz(original)):chosen=trial;stats['patch_selected']+=1;stats['patch_nonzero']+=score
        patch.extend(chosen);i=e
    if i<len(b):exact.extend(raw(b[i:]));patch.extend(raw(b[i:]))
    head=struct.pack('<4sII',b'H7B2',len(b),zlib.crc32(b))
    return head+xz(exact),head+xz(patch),stats
def decode(b):
    magic,n,crc=struct.unpack_from('<4sII',b);assert magic==b'H7B2';x=lzma.decompress(b[12:]);i=0;out=bytearray()
    while i<len(x):
        tag=x[i]
        if tag==0:
            k=struct.unpack_from('<I',x,i+1)[0];i+=5;out.extend(x[i:i+k]);i+=k
        else:
            assert tag in (1,2)
            _,wrapper,mode,lev,strat,pl,cl,nc=struct.unpack_from('<BBBBBIII',x,i);i+=17
            lens=list(struct.unpack_from('<'+'I'*nc,x,i));i+=4*nc;assert bool(lens)==bool(wrapper)
            p=x[i:i+pl];i+=pl;c=recompress(p,15 if mode==0 else -15,lev,strat);assert len(c)==cl
            if tag==2:c=bytes(v^m for v,m in zip(c,x[i:i+cl]));i+=cl
            out.extend(wrap(c,lens))
        assert len(out)<=n
    assert len(out)==n and zlib.crc32(out)==crc;return bytes(out)
def measure(g,name,b,work,url):
    p=work/'input.bin';p.write_bytes(b);r={}
    def record(k,fn,inv):
        t=time.perf_counter_ns();v=fn();enc=time.perf_counter_ns()-t
        t=time.perf_counter_ns();out=inv(v);dec=time.perf_counter_ns()-t
        assert out==b
        r[k]=dict(bytes=len(v),sha256=sha(v),encode_wall_ns=enc,decode_wall_ns=dec)
    record('xz5',lambda:xz(b),lzma.decompress)
    def zd(v):
        q=work/'packed.zst';q.write_bytes(v);return call(['zstd','-q','-d','-c',str(q)])
    record('zstd15',lambda:call(['zstd','-q','-T1','-15','-c',str(p)]),zd)
    def seven():
        call(['7z','a','-t7z','-m0=LZMA2','-mx=5','-mmt=1','-mtc=off','-mta=off','-mtm=off','packed.7z','input.bin'],work);return (work/'packed.7z').read_bytes()
    record('7z',seven,lambda v:call(['7z','x','-so','-mmt=1','packed.7z','input.bin'],work))
    try:
        def pc():
            call([str(precomp),'-cn','-opacked.pcf','input.bin'],work,ok=(0,2));return xz((work/'packed.pcf').read_bytes())
        def pd(v):
            (work/'packed.pcf').write_bytes(lzma.decompress(v));call([str(precomp),'-r','-orestored.bin','packed.pcf'],work);return (work/'restored.bin').read_bytes()
        record('precomp-xz5',pc,pd)
    except (RuntimeError,subprocess.TimeoutExpired,OSError) as e:r['precomp-error']=repr(e)
    t=time.perf_counter_ns();rr=spans(b,g);ex,pa,stats=recipes(b,rr);wall=time.perf_counter_ns()-t
    for k,v in [('exact',ex),('patch',pa)]:
        t=time.perf_counter_ns();out=decode(v);dec=time.perf_counter_ns()-t;assert out==b
        r[k]=dict(bytes=len(v),sha256=sha(v),decode_wall_ns=dec)
    return dict(type='sample',group=g,name=name,url=url,input_bytes=len(b),sha256=sha(b),candidates=r,stats=stats,joint_recipe_search_wall_ns=wall,checks=sum(isinstance(v,dict) and 'bytes' in v for v in r.values()))
a.out.parent.mkdir(parents=True,exist_ok=True);rows=[]
with a.out.open('x') as f:
    def log(r):f.write(json.dumps(r)+'\n');f.flush()
    log(dict(type='meta',protocol='H07B2',script_sha256=sha(pathlib.Path(__file__).read_bytes()),zlib=zlib.ZLIB_RUNTIME_VERSION,precomp_sha256=sha(precomp.read_bytes()),affinity=sorted(os.sched_getaffinity(0))))
    for g,paths in SOURCES.items():
        for base,path in paths:
            with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h07b2-') as td:
                w=pathlib.Path(td);url=base+quote(path,safe='/')
                try:
                    call(['curl','-fLsS','--proto','=https','--max-time','25','--max-filesize','750000','-o',str(w/'source'),url]);b=(w/'source').read_bytes();assert 0<len(b)<=750000
                except (RuntimeError,subprocess.TimeoutExpired,OSError,AssertionError) as e:log(dict(type='skip',group=g,url=url,error=repr(e)));print('SKIP',path,repr(e),flush=True);continue
                r=measure(g,path.rsplit('/',1)[-1],b,w,url);rows.append(r);log(r)
                print(g,r['name'],{k:v['bytes'] for k,v in r['candidates'].items() if isinstance(v,dict)},r['stats'],flush=True)
    def summary(g,rs):
        ordinary=sum(min(r['candidates'][k]['bytes'] for k in ('xz5','zstd15','7z')) for r in rs)
        full=[r for r in rs if 'precomp-xz5' in r['candidates']]
        best=sum(min(r['candidates'][k]['bytes'] for k in ('xz5','zstd15','7z','precomp-xz5')) for r in full)
        p=sum(r['candidates']['patch']['bytes'] for r in full)
        return dict(type='summary',group=g,samples=len(rs),complete=len(full),ordinary=ordinary,precomp=sum(r['candidates']['precomp-xz5']['bytes'] for r in full),best_control=best,patch_on_complete=p,exact=sum(r['candidates']['exact']['bytes'] for r in rs),patch=sum(r['candidates']['patch']['bytes'] for r in rs),wins=sum(r['candidates']['patch']['bytes']<min(r['candidates'][k]['bytes'] for k in ('xz5','zstd15','7z','precomp-xz5')) for r in full),checks=sum(r['checks'] for r in rs),stats={k:sum(r['stats'][k] for r in rs) for k in ('found','exact_match','patch_possible','exact_selected','patch_selected','matched_bytes','patch_nonzero')})
    for g in SOURCES:
        r=summary(g,[x for x in rows if x['group']==g]);log(r);print(json.dumps(r),flush=True)
    r=summary('all',rows);r['gate']=len(rows)==15 and r['complete']==15 and r['patch_on_complete']<=.95*r['best_control'] and r['wins']>=8;log(r);print(json.dumps(r),flush=True)
