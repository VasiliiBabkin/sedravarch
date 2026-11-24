#!/usr/bin/env python3
import argparse,fcntl,hashlib,json,os,pathlib,random,resource,shutil,signal,statistics,subprocess,tempfile,time
p=argparse.ArgumentParser();p.add_argument('--lab',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();root=a.lab.resolve()
lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
assert shutil.disk_usage(root).free>=5*1024**3
assert int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))>=1024**2
def sha(b):return hashlib.sha256(b).hexdigest()
driver=str(root/'experiments/h131/native');profiles={}
for codec,levels in [('lz4',[1,4]),('lz4hc',[3,9]),('zstd',[-3,-1,1,3,6,9,12]),('deflate',[1,3,6])]:
 for lev in levels:profiles[f'{codec}:{lev}']=('native',[driver,'enc','input.bin','packed',codec,str(lev)],[driver,'dec','packed','restored'],False,False)
for lev in [1,3,9]:profiles[f'cli-zstd:{lev}']=('cli',['zstd','-q','-T1','-'+str(lev),'-c','input.bin'],['zstd','-q','-d','-c','packed'],True,True)
profiles['cli-lz4:1']=('cli',['lz4','-q','-1','-c','input.bin'],['lz4','-q','-d','-c','packed'],True,True)
profiles['ref-xz5']=('ref',['xz','-T1','-5','--check=crc64','-c','input.bin'],['xz','-T1','-d','-c','packed'],True,True)
profiles['ref-ppmd5']=('ref',['7z','a','-t7z','-m0=PPMd','-mx=5','-mmt=1','-mtc=off','-mta=off','-mtm=off','packed.7z','input.bin'],['7z','x','-so','-mmt=1','packed.7z'],False,True)
assert len(profiles)==20
def limits():
 resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,)*2);resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024**2,)*2);resource.setrlimit(resource.RLIMIT_CPU,(46,47))
def run(cmd,w,out,kind):
 with (w/out).open('wb') if out else (w/'log').open('wb') as dest,(w/'err').open('wb') as err:
  t=time.perf_counter_ns();child=subprocess.Popen([str(root/'bin/time'),'-f','%U %S %M','-o','metrics','--',*cmd],cwd=w,stdout=dest,stderr=err,preexec_fn=limits,start_new_session=True)
  try:rc=child.wait(timeout=45)
  except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait();raise RuntimeError('timeout')
  wall=time.perf_counter_ns()-t
 if rc:raise RuntimeError('exit '+str(rc)+': '+(w/'err').read_text(errors='replace')[-500:])
 u,s,r=(w/'metrics').read_text().split();v=dict(wall_ns=wall,cpu_s=float(u)+float(s),rss=int(r))
 if kind=='native':v['core_wall_ns'],v['core_cpu_ns']=map(int,(w/'log').read_text().split())
 return v
def sources():
 manifest=json.loads((root/'corpora/manifest.json').read_text())
 for name in ['dickens','mr','x-ray','mozilla']:
  x=next(v for v in manifest if v['group']=='silesia' and pathlib.Path(v['path']).name==name);b=(root/x['path']).read_bytes();assert sha(b)==x['sha256']
  yield 'silesia',name,b[:16777216] if name=='mozilla' else b,dict(path=x['path'],full_sha256=x['sha256'],full_size=len(b))
 for name,path in [('avcodec','/usr/lib/x86_64-linux-gnu/libavcodec.so.60.31.102'),('icudata','/usr/lib/x86_64-linux-gnu/libicudata.so.74.2')]:
  b=pathlib.Path(path).read_bytes();yield 'local',name,b[:16777216] if name=='icudata' else b,dict(path=path,full_sha256=sha(b),full_size=len(b))
def measure(g,n,b,k,rep,w):
 kind,e,d,es,ds=profiles[k];archive='packed.7z' if k=='ref-ppmd5' else 'packed'
 for f in ('packed','packed.7z','restored'):
  (w/f).unlink(missing_ok=True)
 row=dict(type='measurement',group=g,name=n,codec=k,kind=kind,rep=rep,input_bytes=len(b),status='FAIL')
 try:
  row['enc']=run(e,w,archive if es else None,kind);packed=(w/archive).read_bytes();row.update(bytes=len(packed),archive_sha256=sha(packed));row['dec']=run(d,w,'restored' if ds else None,kind)
  if (w/'restored').read_bytes()!=b:raise RuntimeError('roundtrip mismatch')
  row['status']='PASS'
 except (RuntimeError,OSError,ValueError) as ex:row['error']=str(ex)
 return row
def range_ratio(v):return (max(v)-min(v))/statistics.median(v) if statistics.median(v)>0 else None
def aggregate(rows,n):
 pp=[];var={'native_wall':[],'native_cpu':[],'cli_wall':[]}
 for k,(kind,*_) in profiles.items():
  rr=[r for r in rows if r['codec']==k and r['status']=='PASS'];reps=1 if kind=='ref' else 3
  if len(rr)!=n*reps:continue
  groups={}
  for r in rr:groups.setdefault(r['name'],[]).append(r)
  if len(groups)!=n or any(len(v)!=reps or len({(x['bytes'],x['archive_sha256']) for x in v})!=1 for v in groups.values()):continue
  size=sum(v[0]['bytes'] for v in groups.values());nb=sum(v[0]['input_bytes'] for v in groups.values());res=dict(codec=k,kind=kind,bytes=size,input_bytes=nb)
  for phase in ('enc','dec'):
   med=statistics.median
   for key in (['wall_ns','core_wall_ns','core_cpu_ns'] if kind=='native' else ['wall_ns']):
    duration=sum(med(r[phase][key] for r in v) for v in groups.values());res[phase+'_'+key]=duration;res[phase+'_'+key+'_mibs']=nb/1048576/(duration/1e9)
    if reps==3:
     label='cli_wall' if kind=='cli' else 'native_wall' if key=='core_wall_ns' else 'native_cpu' if key=='core_cpu_ns' else None
     if label:var[label].extend(range_ratio([r[phase][key] for r in v]) for v in groups.values())
   res[phase+'_rss']=max(med(r[phase]['rss'] for r in v) for v in groups.values())
  pp.append(res)
 ref=[r for r in pp if r['kind']=='ref'];ref_min=min(ref,key=lambda r:r['bytes']) if ref else None
 ref_oracle=0
 for name in set(r['name'] for r in rows):
  v=[r['bytes'] for r in rows if r['name']==name and r['kind']=='ref' and r['status']=='PASS'];ref_oracle+=min(v) if len(v)==2 else 0
 budgets={}
 for mode,kind,t in [('native-core','native','core_wall_ns'),('native-cpu','native','core_cpu_ns'),('native-e2e','native','wall_ns'),('cli','cli','wall_ns')]:
  budgets[mode]={}
  for key,es,ds,rss in [('A',20,50,65536),('B',5,20,262144)]:
   v=[r for r in pp if r['kind']==kind and r['enc_'+t+'_mibs']>=es and r['dec_'+t+'_mibs']>=ds and max(r['enc_rss'],r['dec_rss'])<=rss]
   budgets[mode][key]=min(v,key=lambda r:r['bytes']) if v else None
 return dict(profiles=pp,ref_min=ref_min,ref_oracle=ref_oracle if len(ref)==2 else None,budgets=budgets,variability={k:dict(median=statistics.median(v),p90=sorted(v)[int(.9*len(v))],count=len(v)) for k,v in var.items() if v})
a.out.parent.mkdir(parents=True,exist_ok=True);rows=[];names=[]
with a.out.open('x') as f:
 def log(r):f.write(json.dumps(r,separators=(',',':'))+'\n');f.flush()
 libs=['/lib/x86_64-linux-gnu/libzstd.so.1','/lib/x86_64-linux-gnu/liblz4.so.1','/lib/x86_64-linux-gnu/libdeflate.so.0','/lib/x86_64-linux-gnu/libz.so.1','/lib/x86_64-linux-gnu/liblzma.so.5']
 log(dict(type='meta',protocol='H131',script_sha256=sha(pathlib.Path(__file__).read_bytes()),driver_sha256=sha(pathlib.Path(driver).read_bytes()),profiles=profiles,affinity=sorted(os.sched_getaffinity(0)),libs={x:sha(pathlib.Path(x).read_bytes()) for x in libs},packages=subprocess.check_output(['dpkg-query','-W','libzstd1','liblz4-1','libdeflate0','zlib1g','liblzma5']).decode(),cli={x:sha(pathlib.Path(shutil.which(x)).read_bytes()) for x in ('zstd','lz4','xz','7z')}))
 for g,n,b,src in sources():
  h=sha(b);names.append((g,n));log(dict(type='source',group=g,name=n,sha256=h,input_bytes=len(b),**src))
  with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h131-') as td:
   w=pathlib.Path(td);(w/'input.bin').write_bytes(b)
   for rep in range(3):
    order=[k for k,v in profiles.items() if v[0]!='ref'];random.Random(h+str(rep)).shuffle(order)
    for k in order:
     r=measure(g,n,b,k,rep,w);rows.append(r);log(r)
    print('DONE',g,n,rep,sum(r['status']=='PASS' for r in rows),len(rows),flush=True)
   for k in ('ref-xz5','ref-ppmd5'):
    r=measure(g,n,b,k,0,w);rows.append(r);log(r);print('REF',g,n,k,r.get('bytes',r.get('error')),flush=True)
 for g,n in names:log(dict(type='sample-summary',group=g,name=n,**aggregate([r for r in rows if r['name']==n],1)))
 for g,n in [('silesia',4),('local',2),('all',6)]:
  rr=[r for r in rows if r['group']==g or g=='all'];q=dict(type='summary',group=g,checks=sum(r['status']=='PASS' for r in rr),total=len(rr),**aggregate(rr,n));log(q)
  print(json.dumps(dict(group=g,checks=q['checks'],total=q['total'],ref=q['ref_min'],budgets=q['budgets'],variability=q['variability'])),flush=True)
