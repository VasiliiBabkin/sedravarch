#!/usr/bin/env python3
"""H22-H24 numeric-lane ablation, trusted public logs only."""
import argparse,collections,fcntl,gzip,hashlib,importlib.util,json,lzma,os,pathlib,resource,shutil,struct,subprocess,sys,tarfile,tempfile,zipfile,zlib,io
MAX=2*1024**2;CAP=32*1024**2
SOURCES=[('HealthApp','HealthApp.tar.gz', [('dev',6*1024**2),('confirmation',12*1024**2)]),('HPC','HPC.zip',[('dev',6*1024**2),('confirmation',12*1024**2)]),('OpenSSH','OpenSSH.tar.gz',[('confirmation',None)]),('Zookeeper','Zookeeper.tar.gz',[('confirmation',None)])]
CONTROLS=('xz5','zstd19','ppmd5','7z5','logfold','logfold-xz','clp3','clp19','clp19-xz')
def sha(b):return hashlib.sha256(b).hexdigest()
def module(path,expected):
 assert sha(path.read_bytes())==expected
 spec=importlib.util.spec_from_file_location(path.stem,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def zig(x):return 2*x if x>=0 else -2*x-1
def unzig(x):return x//2 if x%2==0 else -(x//2)-1
def num(col,m):
 if not all(m.CAN.fullmatch(x) for x in col):return None
 a=list(map(int,col));return a if max(a)<=2**63-1 else None
def bits(a,w):
 out=bytearray();buf=nb=0
 for x in a:
  assert 0<=x<(1<<w) if w else x==0
  buf|=x<<nb;nb+=w
  while nb>=8:out.append(buf&255);buf>>=8;nb-=8
 if nb:out.append(buf)
 return bytes(out)
def numeric(m,a):
 direct=b''.join(map(m.v,a));d=[y-x for x,y in zip(a,a[1:])]
 delta=m.v(a[0])+b''.join(m.v(zig(x)) for x in d)
 d2=m.v(a[0])+(m.v(zig(d[0])) if d else b'')+b''.join(m.v(zig(y-x)) for x,y in zip(d,d[1:]))
 base=min(a);w=(max(a)-base).bit_length();forr=m.v(base)+bytes([w])+bits((x-base for x in a),w)
 return [(2,delta),(3,direct),(4,d2),(5,forr)],d
def encode(m,b):
 groups,order=m.group_rows(b,2);out=bytearray(m.v(len(order))+m.v(len(groups)))
 stats=dict(groups=len(groups),rows=len(order),numeric_columns=0,numeric_values=0,numeric_value_bytes=0,numeric_raw_lane_bytes=0,zero_delta=0,deltas=0,zero_delta2=0,delta2s=0,distinct_sum=0,selected_counts=[0]*6,selected_bytes=[0]*6,D_choices=[0]*6,D_lane_bytes=0,E_lane_bytes=0)
 for rows in groups:
  cols=list(zip(*rows));assert all(len(x)==len(cols) for x in rows)
  out.extend(m.v(len(rows))+m.v(len(cols)))
  for col in cols:
   if all(x==col[0] for x in col):out.extend(b'\0'+m.pack(col[0]));continue
   raw=b''.join(m.pack(x) for x in col);opts=[(1,raw)];a=num(col,m)
   if a is not None:
    q,d=numeric(m,a);opts+=q
    stats['numeric_columns']+=1;stats['numeric_values']+=len(a);stats['numeric_value_bytes']+=sum(map(len,col));stats['numeric_raw_lane_bytes']+=len(raw);stats['zero_delta']+=sum(x==0 for x in d);stats['deltas']+=len(d);stats['zero_delta2']+=sum(x==y for x,y in zip(d,d[1:]));stats['delta2s']+=max(0,len(d)-1);stats['distinct_sum']+=len(set(a))
   cost=lambda t:1+len(m.v(len(t[1])))+len(t[1])
   old=min(opts[:2],key=cost);k,x=min(opts,key=cost)
   stats['D_choices'][old[0]]+=1;stats['D_lane_bytes']+=cost(old);stats['E_lane_bytes']+=cost((k,x));stats['selected_counts'][k]+=1;stats['selected_bytes'][k]+=cost((k,x))
   out.extend(bytes([k])+m.pack(x))
 out.extend(b''.join(map(m.v,order)));stats['inner_bytes']=len(out)
 stats['numeric_heavy']=stats['numeric_value_bytes']>=.1*len(b) and len(groups)<=.1*len(order)
 assert stats['E_lane_bytes']<=stats['D_lane_bytes']
 return bytes(out),stats
def decode(m,body):
 r=m.Reader(body);nr=r.var();ng=r.var();assert ng<=nr<=MAX;groups=[]
 for _ in range(ng):
  n=r.var();nf=r.var();assert 0<n<=nr and nf<=MAX;cols=[]
  for _ in range(nf):
   tag=r.take(1)[0];b=r.blob()
   if tag==0:col=[b]*n
   else:
    q=m.Reader(b)
    if tag==1:col=[q.blob() for _ in range(n)]
    else:
     if tag==2:
      a=[q.var()]
      for i in range(n-1):a.append(a[-1]+unzig(q.var()))
     elif tag==3:a=[q.var() for _ in range(n)]
     elif tag==4:
      a=[q.var()]
      if n>1:
       d=unzig(q.var());a.append(a[-1]+d)
       for i in range(n-2):d+=unzig(q.var());a.append(a[-1]+d)
     elif tag==5:
      base=q.var();w=q.take(1)[0];assert w<=63
      packed=q.take((n*w+7)//8);a=[];buf=nb=j=0
      for i in range(n):
       while nb<w:buf|=packed[j]<<nb;nb+=8;j+=1
       a.append(base+(buf&((1<<w)-1)));buf>>=w;nb-=w
      assert buf==0
     else:raise ValueError('tag')
     assert all(0<=x<=2**63-1 for x in a);col=[str(x).encode() for x in a]
    q.end()
   cols.append(col)
  groups.append(collections.deque(b''.join(row) for row in zip(*cols)) if nf else collections.deque([b'']*n))
 out=bytearray()
 for _ in range(nr):
  k=r.var();assert k<ng;out.extend(groups[k].popleft());assert len(out)<=MAX
 assert not any(groups);r.end();return bytes(out)
def frameE(m,b,body):return struct.pack('<4sBII',b'H22E',4,len(b),zlib.crc32(b))+m.xz(body)
def unframeE(m,c):
 magic,mode,n,crc=struct.unpack_from('<4sBII',c);assert magic==b'H22E' and mode==4;x=decode(m,lzma.decompress(c[13:]));assert len(x)==n and zlib.crc32(x)==crc;return x
def call(cmd,w,t=90):
 return subprocess.run(cmd,cwd=w,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=t).stdout
def source(w,name):
 url='https://zenodo.org/records/8196385/files/'+name+'?download=1';p=w/'source'
 call(['curl','-fLsS','--proto','=https','--max-time','40','--retry','1','--max-filesize',str(CAP),'-o',str(p),url],w,90)
 assert 0<p.stat().st_size<=CAP
 if name.endswith('.zip'):
  with zipfile.ZipFile(p) as f:
   e=sorted([x for x in f.infolist() if not x.is_dir() and x.filename.lower().endswith('.log')],key=lambda x:(-x.file_size,x.filename))[0];assert e.file_size<=128*1024**2;raw=f.read(e);member=e.filename
 else:
  with tarfile.open(p,'r:gz') as f:
   e=sorted([x for x in f.getmembers() if x.isfile() and x.name.lower().endswith('.log')],key=lambda x:(-x.size,x.name))[0];assert e.size<=128*1024**2;raw=f.extractfile(e).read();member=e.name
 return raw,dict(url=url,archive_sha256=sha(p.read_bytes()),archive_bytes=p.stat().st_size,member=member,member_bytes=len(raw),member_sha256=sha(raw))
def window(raw,off):
 if off is None:
  off=0
  for _ in range(2000):i=raw.find(b'\n',off);assert i>=0;off=i+1
 else:i=raw.find(b'\n',off);assert i>=0;off=i+1
 b=raw[off:off+MAX];i=b.rfind(b'\n');assert i>=0
 return b[:i+1],off
def clp_control(root,m,w,b,sizes,hashes,fail):
 clp=str(root/'experiments/h22/clp/usr/bin/clp');config=w/'empty-clp.rc';config.write_text('')
 def run(*args):return call([clp,'--config-file',str(config),*args],w)
 for level in (3,19):
  k='clp'+str(level);arc=w/k;rest=w/(k+'-restore');arc.mkdir();rest.mkdir()
  try:
   run('c','--compression-level',str(level),str(arc),'input.bin');run('x',str(arc),str(rest));assert (rest/'input.bin').read_bytes()==b
   fs=sorted(x for x in arc.rglob('*') if x.is_file());assert fs
   sizes[k]=sum(x.stat().st_size for x in fs);hashes[k]=sha(b''.join(sha(x.read_bytes()).encode() for x in fs))
  except (OSError,AssertionError,subprocess.SubprocessError) as e:fail[k]=repr(e);continue
  if level==19:
   try:
    tar=io.BytesIO()
    with tarfile.open(fileobj=tar,mode='w',format=tarfile.PAX_FORMAT) as tf:
     for x in fs:
      info=tf.gettarinfo(str(x),arcname=x.relative_to(arc).as_posix());info.uid=info.gid=info.mtime=0;info.uname=info.gname='';info.pax_headers={}
      with x.open('rb') as f:tf.addfile(info,f)
    c=m.xz(tar.getvalue());packed=w/'clp-tar-restore';packed.mkdir()
    with tarfile.open(fileobj=io.BytesIO(lzma.decompress(c)),mode='r:') as tf:tf.extractall(packed,filter='data')
    dest=w/'clp-tar-output';dest.mkdir();run('x',str(packed),str(dest));assert (dest/'input.bin').read_bytes()==b
    sizes['clp19-xz']=len(c);hashes['clp19-xz']=sha(c)
   except (OSError,AssertionError,subprocess.SubprocessError,tarfile.TarError) as e:fail['clp19-xz']=repr(e)
def measure(root,m,h21,w,b):
 (w/'input.bin').write_bytes(b);sizes={};hashes={};stats={};fail={}
 for mode,k in [(2,'C'),(3,'D')]:
  body,st=m.encode(b,mode);c=m.frame(b,mode,body);assert m.unframe(c)==b;sizes[k]=len(c);hashes[k]=sha(c);stats[k]=st
 body,st=encode(m,b);c=frameE(m,b,body);assert unframeE(m,c)==b;sizes['E']=len(c);hashes['E']=sha(c);stats['E']=st
 assert st['groups']==stats['D']['groups'] and st['rows']==stats['D']['rows']
 c=m.xz(b);assert lzma.decompress(c)==b;sizes['xz5']=len(c);hashes['xz5']=sha(c)
 c=call(['zstd','-q','-T1','-19','-c','input.bin'],w);(w/'control.zst').write_bytes(c);assert call(['zstd','-q','-d','-c','control.zst'],w)==b;sizes['zstd19']=len(c);hashes['zstd19']=sha(c)
 for k,method in [('ppmd5','PPMd'),('7z5','LZMA2')]:
  call(['7z','a','-t7z','-m0='+method,'-mx=5','-mmt=1','-mtc=off','-mta=off','-mtm=off',k+'.7z','input.bin'],w)
  c=(w/(k+'.7z')).read_bytes();assert call(['7z','x','-so','-mmt=1',k+'.7z'],w)==b;sizes[k]=len(c);hashes[k]=sha(c)
 # reuse exact H21 core API worker, but point its expected Logfold directory at H21.
 try:
  p=root/'experiments/h21/h21_coarsen.py';sp=json.loads(call([sys.executable,str(p),'specialized',str(root),str(w)],w))
  for k,q in sp.items():
   if q['exact']:sizes[k]=q['bytes'];hashes[k]=q['sha256']
   else:fail[k]='roundtrip mismatch'
 except (OSError,subprocess.SubprocessError,ValueError) as e:fail['logfold']=repr(e)
 clp_control(root,m,w,b,sizes,hashes,fail)
 return dict(sizes=sizes,hashes=hashes,stats=stats,fail=fail,checks=len(sizes))
def main():
 p=argparse.ArgumentParser();p.add_argument('--lab',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();root=a.lab.resolve()
 lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 assert shutil.disk_usage(root).free>=5*1024**3 and int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))>=1024**2
 resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,)*2);resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024**2,)*2)
 m=module(root/'experiments/h18/h18_h20_logs.py','1b71aaa8778c46ef4b82f16162f32304df58df8b42d99f49b111a80fab911298');h21=module(root/'experiments/h21/h21_coarsen.py','07d1ff28850023a68a2839a4072924472a03a9503c45e434dd17ed38a55f0778')
 assert sha((root/'experiments/h22/clp/usr/bin/clp').read_bytes())=='fe3e1cf508c996c94de0a39d96a2113d5a475590e5048511ddfa7cb68d695718'
 assert call(['git','-C',str(root/'experiments/h21/logfold'),'rev-parse','HEAD'],root).decode().strip()=='0330396bbe2bc7c44ea07e24d0c57b8725f7bbc2'
 rows=[]
 with a.out.open('x') as f:
  def log(r):f.write(json.dumps(r,separators=(',',':'))+'\n');f.flush()
  log(dict(type='meta',protocol='H22-H24',script_sha256=sha(pathlib.Path(__file__).read_bytes()),affinity=sorted(os.sched_getaffinity(0)),clp='0.14.1',logfold='0330396bbe2bc7c44ea07e24d0c57b8725f7bbc2'))
  for name,archive,windows in SOURCES:
   with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h22-source-') as td:
    try:raw,src=source(pathlib.Path(td),archive)
    except (OSError,ValueError,AssertionError,IndexError,subprocess.SubprocessError,tarfile.TarError,zipfile.BadZipFile) as e:
     for g,off in windows:log(dict(type='skip',group=g,name=name,error=repr(e)))
     print('SKIP',name,repr(e),flush=True);continue
    for g,off in windows:
     try:b,start=window(raw,off)
     except AssertionError:log(dict(type='skip',group=g,name=name,error='window unavailable'));continue
     with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h22-window-') as wd:r=measure(root,m,h21,pathlib.Path(wd),b)
     r.update(type='sample',group=g,name=name,input_bytes=len(b),lines=b.count(b'\n'),offset=start,sha256_input=sha(b),**src);rows.append(r);log(r);print(g,name,r['sizes'],r['fail'],flush=True)
  ss=[]
  for g in ('dev','confirmation'):
   rr=[r for r in rows if r['group']==g];strong=[min(r['sizes'][k] for k in CONTROLS if k in r['sizes']) for r in rr]
   q=dict(type='summary',group=g,files=len(rr),sizes={k:sum(r['sizes'][k] for r in rr) for k in 'CDE'},strong=sum(strong),wins={k:sum(r['sizes'][k]<s for r,s in zip(rr,strong)) for k in 'CDE'},checks=sum(r['checks'] for r in rr),complete=all(all(k in r['sizes'] for k in CONTROLS) for r in rr),input_bytes=sum(r['input_bytes'] for r in rr));ss.append(q);log(q);print(json.dumps(q),flush=True)
  def gate(q,n,w):return q['files']==n and q['complete'] and q['sizes']['E']<=.97*q['sizes']['D'] and q['sizes']['E']<=.95*q['strong'] and q['wins']['E']>=w
  d,h=ss;q=dict(type='gate',h23=gate(d,2,2),h24_confirmation=gate(h,4,3),h24=gate(d,2,2) and gate(h,4,3),checks=sum(r['checks'] for r in rows));log(q);print(json.dumps(q),flush=True)
if __name__=='__main__':main()
