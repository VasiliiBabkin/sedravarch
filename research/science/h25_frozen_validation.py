#!/usr/bin/env python3
"""H25 frozen D falsification; public trusted text only."""
import argparse,collections,fcntl,gzip,hashlib,importlib.util,json,lzma,os,pathlib,resource,shutil,statistics,subprocess,sys,tempfile,time,zipfile
MAX=2*1024**2;CAP=32*1024**2;RAW_CAP=256*1024**2
REV='f349db7f7783333f668e79618da62f8714fd7f2c'
BASE='https://raw.githubusercontent.com/wrench-project/task_clustering_batch_datasets/'+REV+'/workloads/'
SOURCES=[('scheduler','KTH',BASE+'kth_sp2.swf','raw'),('scheduler','SDSC',BASE+'sdsc_sp2.swf','raw'),('http','NASA','https://ita.ee.lbl.gov/traces/NASA_access_log_Jul95.gz','gzip'),('telemetry','UCI-power','https://archive.ics.uci.edu/static/public/235/individual+household+electric+power+consumption.zip','zip')]
CONTROLS=('xz5','xz9','zstd19','zstd22','ppmd5','ppmd7','7z5','logfold','logfold-xz','clp3','clp19','clp19-xz')
def sha(b):return hashlib.sha256(b).hexdigest()
def module(path,expected):
 assert sha(path.read_bytes())==expected
 spec=importlib.util.spec_from_file_location(path.stem,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def h18(root):return module(root/'experiments/h18/h18_h20_logs.py','1b71aaa8778c46ef4b82f16162f32304df58df8b42d99f49b111a80fab911298')
def call(cmd,w,t=120):
 return subprocess.run(cmd,cwd=w,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=t).stdout
def timed(root,cmd,w,stdout=None,t=120):
 start=time.perf_counter_ns()
 with (w/'timed-out' if stdout is None else stdout).open('wb') as f:
  p=subprocess.run([str(root/'bin/time'),'-f','%U %S %M','-o',str(w/'metrics'),'--',*cmd],cwd=w,stdout=f,stderr=subprocess.PIPE,timeout=t,check=True)
 wall=time.perf_counter_ns()-start;u,s,r=(w/'metrics').read_text().split()
 return dict(wall_ns=wall,cpu_s=float(u)+float(s),rss_kib=int(r))
def source(w,url,kind):
 p=w/'source';call(['curl','-fLsS','--proto','=https','--max-time','45','--retry','1','--max-filesize',str(CAP),'-o',str(p),url],w,100);assert 0<p.stat().st_size<=CAP
 if kind=='raw':raw=p.read_bytes();member=None
 elif kind=='gzip':
  with gzip.open(p,'rb') as f:raw=f.read(RAW_CAP+1)
  member=None
 else:
  with zipfile.ZipFile(p) as f:
   entry=f.getinfo('household_power_consumption.txt');assert entry.file_size<=RAW_CAP;raw=f.read(entry);member=entry.filename
 assert 0<len(raw)<=RAW_CAP
 off=max(0,(len(raw)-MAX)//3)
 if off:
  off=raw.find(b'\n',off)+1;assert off>0
 b=raw[off:off+MAX];end=b.rfind(b'\n');assert end>=0;b=b[:end+1]
 return b,dict(url=url,download_bytes=p.stat().st_size,download_sha256=sha(p.read_bytes()),member=member,member_bytes=len(raw),member_sha256=sha(raw),offset=off)
def eligibility(m,b):
 groups,order=m.group_rows(b,2);nb=nv=nc=0
 for rows in groups:
  for col in zip(*rows):
   if all(x==col[0] for x in col):continue
   if all(m.CAN.fullmatch(x) for x in col) and max(map(int,col))<=2**63-1:
    nc+=1;nv+=len(col);nb+=sum(map(len,col))
 return dict(groups=len(groups),rows=len(order),numeric_columns=nc,numeric_values=nv,numeric_value_bytes=nb,eligible=nb>=.10*len(b) and len(groups)<=.10*len(order))
def worker(root,w,mode):
 m=h18(root)
 if mode=='enc':
  b=(w/'input.bin').read_bytes();body,st=m.encode(b,3);(w/'D').write_bytes(m.frame(b,3,body))
 else:(w/'restored').write_bytes(m.unframe((w/'D').read_bytes()))
def measure(root,m,h22,w,b,has_brotli):
 (w/'input.bin').write_bytes(b);e=eligibility(m,b);sizes={};hashes={};fail={};runs=[];script=str(pathlib.Path(__file__).resolve())
 for rep in range(3):
  enc=timed(root,[sys.executable,script,'enc',str(root),str(w)],w)
  c=(w/'D').read_bytes();digest=sha(c);assert hashes.setdefault('D',digest)==digest and sizes.setdefault('D',len(c))==len(c)
  dec=timed(root,[sys.executable,script,'dec',str(root),str(w)],w);assert (w/'restored').read_bytes()==b
  runs.append(dict(enc=enc,dec=dec))
  print('D verified',rep+1,len(c),flush=True)
 xzmetrics={}
 for lev in (5,9):
  k='xz'+str(lev)
  try:
   enc=timed(root,['xz','-T1','-'+str(lev),'--check=crc64','-c','input.bin'],w,w/'control.xz')
   dec=timed(root,['xz','-T1','-d','-c','control.xz'],w,w/'restored')
   assert (w/'restored').read_bytes()==b;c=(w/'control.xz').read_bytes()
   sizes[k]=len(c);hashes[k]=sha(c);xzmetrics[k]=dict(enc=enc,dec=dec)
  except (OSError,AssertionError,subprocess.SubprocessError) as ex:fail[k]=repr(ex)
 for lev in (19,22):
  k='zstd'+str(lev)
  try:
   c=call(['zstd','-q','-T1',*(['--ultra'] if lev==22 else []),'-'+str(lev),'-c','input.bin'],w);(w/'control.zst').write_bytes(c);assert call(['zstd','-q','-d','-c','control.zst'],w)==b;sizes[k]=len(c);hashes[k]=sha(c)
  except (OSError,AssertionError,subprocess.SubprocessError) as ex:fail[k]=repr(ex)
 for k,method,lev in [('ppmd5','PPMd',5),('ppmd7','PPMd',7),('7z5','LZMA2',5)]:
  try:
   call(['7z','a','-t7z','-m0='+method,'-mx='+str(lev),'-mmt=1','-mtc=off','-mta=off','-mtm=off',k+'.7z','input.bin'],w)
   c=(w/(k+'.7z')).read_bytes();assert call(['7z','x','-so','-mmt=1',k+'.7z'],w)==b;sizes[k]=len(c);hashes[k]=sha(c)
  except (OSError,AssertionError,subprocess.SubprocessError) as ex:fail[k]=repr(ex)
 try:b.decode('utf-8');utf8=True
 except UnicodeDecodeError:utf8=False
 if utf8:
  try:
   sp=json.loads(call([sys.executable,str(root/'experiments/h21/h21_coarsen.py'),'specialized',str(root),str(w)],w))
   for k,q in sp.items():
    if q['exact']:sizes[k]=q['bytes'];hashes[k]=q['sha256']
    else:fail[k]='roundtrip mismatch'
  except (OSError,ValueError,subprocess.SubprocessError) as ex:fail['logfold']=repr(ex)
 else:fail['logfold']='not applicable: non-UTF8';fail['logfold-xz']='not applicable: non-UTF8'
 h22.clp_control(root,m,w,b,sizes,hashes,fail)
 if has_brotli:
  try:
   c=call(['brotli','-q','11','-c','input.bin'],w);(w/'control.br').write_bytes(c);assert call(['brotli','-d','-c','control.br'],w)==b;sizes['brotli11']=len(c);hashes['brotli11']=sha(c)
  except (OSError,AssertionError,subprocess.SubprocessError) as ex:fail['brotli11']=repr(ex)
 required=[k for k in CONTROLS if utf8 or not k.startswith('logfold')]
 # Optional brotli is included if exact; if available but failure, preserve diagnostic.
 strong=min((k for k in sizes if k!='D'),key=lambda k:sizes[k])
 return dict(sizes=sizes,hashes=hashes,fail=fail,utf8=utf8,required_complete=all(k in sizes for k in required),strong=sizes[strong],strong_codec=strong,eligibility=e,runs=runs,xzmetrics=xzmetrics,checks=3+len(sizes)-1)
def main():
 p=argparse.ArgumentParser();p.add_argument('--lab',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();root=a.lab.resolve()
 lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 assert shutil.disk_usage(root).free>=5*1024**3 and int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))>=1024**2
 resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,)*2);resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024**2,)*2)
 m=h18(root);h22=module(root/'experiments/h22/h22_h24_numeric.py','da3ba8d1e7ad86507281655f83bff8af2c9fd9519c847e58bd87fd1e7965b816')
 assert sha((root/'experiments/h21/h21_coarsen.py').read_bytes())=='07d1ff28850023a68a2839a4072924472a03a9503c45e434dd17ed38a55f0778'
 assert sha((root/'experiments/h22/clp/usr/bin/clp').read_bytes())=='fe3e1cf508c996c94de0a39d96a2113d5a475590e5048511ddfa7cb68d695718'
 assert call(['git','-C',str(root/'experiments/h21/logfold'),'rev-parse','HEAD'],root).decode().strip()=='0330396bbe2bc7c44ea07e24d0c57b8725f7bbc2'
 has_brotli=shutil.which('brotli') is not None;rows=[]
 with a.out.open('x') as f:
  def log(r):f.write(json.dumps(r,separators=(',',':'))+'\n');f.flush()
  log(dict(type='meta',protocol='H25',script_sha256=sha(pathlib.Path(__file__).read_bytes()),affinity=sorted(os.sched_getaffinity(0)),brotli_available=has_brotli,versions={k:call(cmd,root).decode(errors='replace').splitlines()[:4] for k,cmd in [('xz',['xz','--version']),('zstd',['zstd','--version']),('7z',['7z','i'])]+([('brotli',['brotli','--version'])] if has_brotli else [])}))
  for domain,name,url,kind in SOURCES:
   with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h25-') as td:
    w=pathlib.Path(td)
    try:b,src=source(w,url,kind)
    except (OSError,AssertionError,KeyError,ValueError,subprocess.SubprocessError,zipfile.BadZipFile) as ex:log(dict(type='skip',domain=domain,name=name,url=url,error=repr(ex)));print('SKIP',name,repr(ex),flush=True);continue
    print('SOURCE',name,len(b),flush=True)
    r=measure(root,m,h22,w,b,has_brotli)
    r.update(type='sample',domain=domain,name=name,input_bytes=len(b),sha256_input=sha(b),**src);rows.append(r);log(r);print(name,r['sizes'],r['eligibility'],r['fail'],flush=True)
  n=sum(r['input_bytes'] for r in rows);d=sum(r['sizes']['D'] for r in rows);s=sum(r['strong'] for r in rows);eligible=[r for r in rows if r['eligibility']['eligible']]
  coverage=sum(r['input_bytes'] for r in eligible)/n if n else 0;domains=len({r['domain'] for r in eligible})
  tests=dict(complete=len(rows)==4 and all(r['required_complete'] for r in rows),size=bool(s and d<=.9*s),wins=sum(r['sizes']['D']<r['strong'] for r in rows)>=3,worst_file=bool(rows and all(r['sizes']['D']<=1.05*r['strong'] for r in rows)),coverage=coverage>=.75 and domains>=2,resource=bool(rows and all(t['enc']['cpu_s']<=60 and t['dec']['cpu_s']<=5 and max(t['enc']['rss_kib'],t['dec']['rss_kib'])<=262144 for r in rows for t in r['runs'])))
  q=dict(type='gate',tests=tests,go=all(tests.values()),files=len(rows),input_bytes=n,D=d,strong=s,eligible_bytes=sum(r['input_bytes'] for r in eligible),coverage=coverage,eligible_domains=domains,wins=sum(r['sizes']['D']<r['strong'] for r in rows),checks=sum(r['checks'] for r in rows));log(q);print(json.dumps(q),flush=True)
if __name__=='__main__':
 if sys.argv[1] in ('enc','dec'):worker(pathlib.Path(sys.argv[2]),pathlib.Path(sys.argv[3]),sys.argv[1])
 else:main()
