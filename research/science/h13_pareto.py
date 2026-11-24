#!/usr/bin/env python3
import argparse,fcntl,hashlib,json,os,pathlib,random,resource,shutil,signal,statistics,subprocess,tempfile,time,gzip
p=argparse.ArgumentParser();p.add_argument('--lab',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();root=a.lab.resolve()
lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
assert shutil.disk_usage(root).free>=5*1024**3
assert int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))>=1024**2
N=1048576
def sha(b):return hashlib.sha256(b).hexdigest()
profiles={}
def add(k,e,d,es=True,ds=True):profiles[k]=(e,d,es,ds)
for n in [1,9]:add('lz4-'+str(n),['lz4','-q','-'+str(n),'-c','input.bin'],['lz4','-q','-d','-c','packed'])
add('gzip6',['gzip','-n','-6','-c','input.bin'],['gzip','-dc','packed'])
for n in [1,3,9,19]:add('zstd'+str(n),['zstd','-q','-T1','-'+str(n),'-c','input.bin'],['zstd','-q','-dc','packed'])
for n in [1,5,9]:add('xz'+str(n),['xz','-T1','-'+str(n),'-c','input.bin'],['xz','-T1','-dc','packed'])
add('brotli9',['brotli','-q','9','-c','input.bin'],['brotli','-d','-c','packed'])
for k,m in [('7z5','LZMA2'),('ppmd5','PPMd')]:add(k,['7z','a','-t7z','-m0='+m,'-mx=5','-mmt=1','-mtc=off','-mta=off','-mtm=off','packed.7z','input.bin'],['7z','x','-so','-mmt=1','packed.7z'],False)
add('sda-balanced',['sedravarch-v07','pack-profile','balanced','1','input.bin','packed'],['sedravarch-v07','unpack','packed','restored'],False,False)
assert len(profiles)==14
def limits():
 resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,)*2);resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,)*2);resource.setrlimit(resource.RLIMIT_CPU,(31,32))
def run(cmd,w,out,stage):
 with (w/out).open('wb') if out else open(os.devnull,'wb') as dest,(w/'err').open('wb') as err:
  t=time.perf_counter_ns()
  child=subprocess.Popen([str(root/'bin/time'),'-f','%U %S %M','-o','metrics','--',*cmd],cwd=w,stdout=dest,stderr=err,preexec_fn=limits,start_new_session=True)
  try: rc=child.wait(timeout=30)
  except subprocess.TimeoutExpired:
   os.killpg(child.pid,signal.SIGKILL);child.wait();raise RuntimeError(stage+' timeout')
  ns=time.perf_counter_ns()-t
 if rc:raise RuntimeError(stage+' exit '+str(rc)+': '+(w/'err').read_text(errors='replace')[-500:])
 u,s,r=(w/'metrics').read_text().split()
 return dict(wall_ns=ns,cpu_s=float(u)+float(s),peak_rss_kib=int(r))
def sources():
 m=json.loads((root/'corpora/manifest.json').read_text())
 for name in ('dickens','mozilla','mr','osdb','samba','x-ray'):
  v=next(x for x in m if x['group']=='silesia' and pathlib.Path(x['path']).name==name)
  b=(root/v['path']).read_bytes();assert sha(b)==v['sha256'];off=(len(b)-N)//3
  yield 'silesia',name,b[off:off+N],dict(path=v['path'],source_sha256=v['sha256'],offset=off)
 for name,path in [('sqlite','/usr/lib/x86_64-linux-gnu/libsqlite3.so.0'),('crypto','/usr/lib/x86_64-linux-gnu/libcrypto.so.3'),('glib-news','/usr/share/doc/libglib2.0-0t64/NEWS.gz'),('ffmpeg-man','/usr/share/man/man1/ffmpeg-all.1.gz')]:
  b=pathlib.Path(path).read_bytes();data=gzip.decompress(b) if path.endswith('.gz') else b
  yield 'local',name,data[:N],dict(path=path,source_sha256=sha(b),canonical_sha256=sha(data),offset=0)
def vector(x):return [x[k] for k in ('bytes','enc_ns','dec_ns','enc_rss','dec_rss')]
def front(rr):
 return [r['codec'] for r in rr if not any(all(x<=y for x,y in zip(vector(q),vector(r))) and any(x<y for x,y in zip(vector(q),vector(r))) for q in rr)]
def budget(r,k):
 e,d,m,n=r['enc_mibs'],r['dec_mibs'],r['enc_rss'],r['dec_rss']
 return (e>=20 and d>=50 and max(m,n)<=65536) if k=='A' else (e>=5 and d>=20 and max(m,n)<=262144) if k=='B' else (d>=10 and n<=16384 and m<=524288)
def aggregate(rr,expected):
 res=[]
 for k in profiles:
  ss=[r for r in rr if r['codec']==k and r['status']=='PASS']
  if len(ss)!=expected*3:continue
  groups={}
  for s in ss:groups.setdefault(s['name'],[]).append(s)
  if len(groups)!=expected or any(len(v)!=3 or len({(s['bytes'],s['archive_sha256']) for s in v})!=1 for v in groups.values()):continue
  med=statistics.median
  n=sum(v[0]['input_bytes'] for v in groups.values());size=sum(v[0]['bytes'] for v in groups.values())
  e=sum(med(s['enc']['wall_ns'] for s in v) for v in groups.values());d=sum(med(s['dec']['wall_ns'] for s in v) for v in groups.values())
  res.append(dict(codec=k,input_bytes=n,bytes=size,enc_ns=e,dec_ns=d,enc_mibs=n/1048576/(e/1e9),dec_mibs=n/1048576/(d/1e9),enc_rss=max(med(s['enc']['peak_rss_kib'] for s in v) for v in groups.values()),dec_rss=max(med(s['dec']['peak_rss_kib'] for s in v) for v in groups.values())))
 best=min(res,key=lambda x:x['bytes']) if res else None
 budgets={}
 for k in 'ABC':
  v=[r for r in res if budget(r,k)]
  budgets[k]=min(v,key=lambda x:x['bytes']) if v else None
 return dict(profiles=res,front=front(res),min=best,budgets=budgets)
a.out.parent.mkdir(parents=True,exist_ok=True);rows=[];samples=[]
with a.out.open('x') as f:
 def log(r):f.write(json.dumps(r,separators=(',',':'))+'\n');f.flush()
 log(dict(type='meta',protocol='H13',script_sha256=sha(pathlib.Path(__file__).read_bytes()),profiles=profiles,affinity=sorted(os.sched_getaffinity(0)),binaries={k:dict(path=shutil.which(v[0][0]),sha256=sha(pathlib.Path(shutil.which(v[0][0])).read_bytes())) for k,v in profiles.items()}))
 for g,name,b,source in sources():
  h=sha(b);samples.append((g,name));log(dict(type='source',group=g,name=name,input_bytes=len(b),sha256=h,**source))
  for rep in range(3):
   order=list(profiles);random.Random(h+str(rep)).shuffle(order)
   for k in order:
    row=dict(type='measurement',group=g,name=name,codec=k,rep=rep,input_bytes=len(b),status='FAIL')
    with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h13-') as td:
     w=pathlib.Path(td);(w/'input.bin').write_bytes(b);enc,dec,es,ds=profiles[k];archive='packed.7z' if k in ('7z5','ppmd5') else 'packed'
     try:
      row['enc']=run(enc,w,archive if es else None,'encode');packed=(w/archive).read_bytes()
      row['bytes']=len(packed);row['archive_sha256']=sha(packed)
      row['dec']=run(dec,w,'restored' if ds else None,'decode')
      if (w/'restored').read_bytes()!=b:raise RuntimeError('roundtrip mismatch')
      row['status']='PASS'
     except (OSError,RuntimeError,ValueError) as ex:row['error']=str(ex)
    rows.append(row);log(row)
   print('DONE',g,name,rep,sum(r['status']=='PASS' for r in rows),len(rows),flush=True)
 for g,name in samples:
  s=aggregate([r for r in rows if r['name']==name],1);log(dict(type='sample-summary',group=g,name=name,**s))
 for g,n in [('silesia',6),('local',4),('all',10)]:
  rr=[r for r in rows if g=='all' or r['group']==g]
  s=aggregate(rr,n);q=dict(type='summary',group=g,checks=sum(r['status']=='PASS' for r in rr),total=len(rr),**s);log(q)
  print(json.dumps(q),flush=True)
