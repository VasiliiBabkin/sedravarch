#!/usr/bin/env python3
"""H13.2 repeated native calls. Trusted bounded research inputs only."""
import argparse,ctypes as C,fcntl,hashlib,json,os,pathlib,random,resource,shutil,signal,statistics,struct,subprocess,sys,tempfile,time,zlib
MIB=1048576
PROFILES=[('lz4',1),('zstd',3),('zstd',6),('zstd',9),('zstd',12),('deflate',6)]
def require(v,msg='check failed'):
 if not v:raise RuntimeError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def equal_file(buf,n,path):
 v=memoryview(buf).cast('B')[:n]
 with open(path,'rb') as f:
  for i in range(0,n,65536):
   b=f.read(min(65536,n-i))
   if v[i:i+len(b)]!=b or len(b)!=min(65536,n-i):return False
  return not f.read(1)
def bindings():
 l=C.CDLL('liblz4.so.1');z=C.CDLL('libzstd.so.1');d=C.CDLL('libdeflate.so.0')
 I=C.c_int;S=C.c_size_t;P=C.c_void_p
 for lib,name,args,ret in [
  (l,'LZ4_compressBound',[I],I),(l,'LZ4_compress_fast',[P,P,I,I,I],I),(l,'LZ4_decompress_safe',[P,P,I,I],I),
  (z,'ZSTD_compressBound',[S],S),(z,'ZSTD_compress',[P,S,P,S,I],S),(z,'ZSTD_decompress',[P,S,P,S],S),(z,'ZSTD_isError',[S],C.c_uint),
  (d,'libdeflate_alloc_compressor',[I],P),(d,'libdeflate_free_compressor',[P],None),(d,'libdeflate_gzip_compress_bound',[P,S],S),(d,'libdeflate_gzip_compress',[P,P,S,P,S],S),
  (d,'libdeflate_alloc_decompressor',[],P),(d,'libdeflate_free_decompressor',[P],None),(d,'libdeflate_gzip_decompress',[P,P,S,P,S,C.POINTER(S)],I)]:
  f=getattr(lib,name);f.argtypes=args;f.restype=ret
 return l,z,d
def worker(phase,source,packed,codec,level,mode,warm,reps):
 l,z,d=bindings();enc=phase=='enc';pre=mode=='prealloc';data=(source if enc else packed).read_bytes()
 require(len(data)<=32*MIB+MIB)
 if enc:
  n=len(data);tag={'lz4':0,'zstd':1,'deflate':2}[codec];require(0<n<=32*MIB);payload=data
 else:
  magic,tag,n,crc=struct.unpack_from('<4sBII',data)
  require(magic==b'H131' and tag in (0,1,2) and 0<n<=32*MIB);payload=data[13:]
 def handle():
  h=(d.libdeflate_alloc_compressor(level) if enc else d.libdeflate_alloc_decompressor()) if tag==2 else None
  require(tag!=2 or h,'libdeflate allocation');return h
 def free(h):
  if h:(d.libdeflate_free_compressor if enc else d.libdeflate_free_decompressor)(h)
 def allocate(h):
  cap=(l.LZ4_compressBound(n) if tag==0 else z.ZSTD_compressBound(n) if tag==1 else d.libdeflate_gzip_compress_bound(h,n)) if enc else n
  require(0<cap<=64*MIB);return C.create_string_buffer(cap+(13 if enc else 0)),cap
 h=handle() if pre else None;buf,cap=allocate(h) if pre else (None,0);results=[]
 try:
  for i in range(warm+reps):
   t=time.perf_counter_ns();c=time.process_time_ns()
   if not pre:h=handle();buf,cap=allocate(h)
   if enc:
    struct.pack_into('<4sBII',buf,0,b'H131',tag,n,zlib.crc32(data));dest=C.byref(buf,13)
    if tag==0:m=l.LZ4_compress_fast(payload,dest,n,cap,level)
    elif tag==1:m=z.ZSTD_compress(dest,cap,payload,n,level);require(not z.ZSTD_isError(m))
    else:m=d.libdeflate_gzip_compress(h,payload,n,dest,cap)
    require(0<m<=cap);written=13+m
   else:
    if tag==0:m=l.LZ4_decompress_safe(payload,buf,len(payload),n)
    elif tag==1:m=z.ZSTD_decompress(buf,n,payload,len(payload));require(not z.ZSTD_isError(m))
    else:
     actual=C.c_size_t();require(d.libdeflate_gzip_decompress(h,payload,len(payload),buf,n,C.byref(actual))==0);m=actual.value
    require(m==n and zlib.crc32(memoryview(buf).cast('B')[:n])==crc);written=n
   if not pre:free(h);h=None
   cpu=time.process_time_ns()-c;wall=time.perf_counter_ns()-t
   if enc and i==0:
    with packed.open('wb') as f:f.write(memoryview(buf).cast('B')[:written])
   else:require(equal_file(buf,written,packed if enc else source),'byte comparison')
   if i>=warm:results.append(dict(wall_ns=wall,cpu_ns=cpu))
   if not pre:buf=None
 finally:free(h)
 print(json.dumps(dict(calls=results,checks=reps if not enc else 0,packed_bytes=packed.stat().st_size)))
def limits():
 resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,)*2);resource.setrlimit(resource.RLIMIT_FSIZE,(128*MIB,)*2);resource.setrlimit(resource.RLIMIT_CPU,(91,92))
def procstat(cpu):
 lines=pathlib.Path('/proc/stat').read_text().splitlines()
 line=next(x for x in lines if x.startswith('cpu'+str(cpu)+' ')).split()
 freq=pathlib.Path(f'/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_cur_freq')
 return dict(cpu_ticks=list(map(int,line[1:])),load=pathlib.Path('/proc/loadavg').read_text().strip(),freq_khz=int(freq.read_text()) if freq.is_file() else None)
def run(cmd,w,timer,stdout=None):
 with (w/'error').open('wb') as err, (w/'stdout' if stdout is None else stdout).open('wb') as out:
  t=time.perf_counter_ns();p=subprocess.Popen([str(timer),'-f','%M','-o',str(w/'rss'),'--',*cmd],cwd=w,stdout=out,stderr=err,preexec_fn=limits,start_new_session=True)
  try:rc=p.wait(timeout=90)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait();raise RuntimeError('timeout')
  wall=time.perf_counter_ns()-t
 require(rc==0,(w/'error').read_text(errors='replace')[-1000:])
 return dict(rss_kib=int((w/'rss').read_text()),process_wall_ns=wall)
def sources(root,smoke):
 if smoke:
  b=random.Random(20261125).randbytes(524288)+b'ABCD0123456789\n'*40000
  yield 'smoke','synthetic',b,dict(generator='random seed 20261125 plus repeated text',full_sha256=sha(b));return
 m=json.loads((root/'corpora/manifest.json').read_text())
 for name in ['dickens','mozilla']:
  x=next(v for v in m if v['group']=='silesia' and pathlib.Path(v['path']).name==name)
  b=(root/x['path']).read_bytes();require(sha(b)==x['sha256'])
  yield 'silesia',name,b if name=='dickens' else b[:16*MIB],dict(path=x['path'],full_sha256=sha(b),full_size=len(b))
 for name,path in [('avfilter','/usr/lib/x86_64-linux-gnu/libavfilter.so.9.12.100'),('x265','/usr/lib/x86_64-linux-gnu/libx265.so.199')]:
  b=pathlib.Path(path).read_bytes();yield 'local',name,b if name=='avfilter' else b[:16*MIB],dict(path=path,full_sha256=sha(b),full_size=len(b))
def reference(w,source,b,timer,codec):
 archive=w/('ref.7z' if codec=='ppmd5' else 'ref.xz');restored=w/'ref-restored'
 if codec=='xz5':
  e=run(['xz','-T1','-5','--check=crc64','-c',str(source)],w,timer,archive)
  d=run(['xz','-T1','-d','-c',str(archive)],w,timer,restored)
 else:
  e=run(['7z','a','-t7z','-m0=PPMd','-mx=5','-mmt=1','-mtc=off','-mta=off','-mtm=off',str(archive),source.name],w,timer)
  d=run(['7z','x','-so','-mmt=1',str(archive)],w,timer,restored)
 require(restored.read_bytes()==b);return dict(codec=codec,bytes=archive.stat().st_size,sha256=sha(archive.read_bytes()),enc=e,dec=d,checks=1)
def summarize(rows,refs,g):
 rr=[r for r in rows if r['group']==g];ref=[r for r in refs if r['group']==g];profiles=[]
 nfiles=len({r['name'] for r in rr});refsize=min(sum(r['bytes'] for r in ref if r['codec']==k) for k in ('xz5','ppmd5')) if nfiles and len(ref)==2*nfiles else None
 for mode in ('prealloc','alloc'):
  for codec,level in PROFILES:
   ss=[r for r in rr if (r['mode'],r['codec'],r['level'])==(mode,codec,level)]
   if len(ss)!=nfiles or nfiles==0:continue
   n=sum(r['input_bytes'] for r in ss);q=dict(mode=mode,codec=codec,level=level,bytes=sum(r['packed_bytes'] for r in ss),input_bytes=n)
   for phase in ('enc','dec'):
    v=[[a['wall_ns'] for a in r[phase]['calls']] for r in ss];c=[[a['cpu_ns'] for a in r[phase]['calls']] for r in ss]
    med=statistics.median
    q[phase+'_mibs']=n/MIB/(sum(map(med,v))/1e9);q[phase+'_worst_mibs']=n/MIB/(sum(map(max,v))/1e9)
    q[phase+'_rss_kib']=max(r[phase]['rss_kib'] for r in ss)
    q[phase+'_wall_ranges']=[(max(x)-min(x))/med(x) for x in v]
    q[phase+'_cpu_ranges']=[(max(x)-min(x))/med(x) for x in c]
    q[phase+'_iqr_ratios']=[(statistics.quantiles(x,n=4,method='inclusive')[2]-statistics.quantiles(x,n=4,method='inclusive')[0])/med(x) for x in v]
   profiles.append(q)
 budgets={}
 for mode in ('prealloc','alloc'):
  for key,e,d,rss in [('A',20,50,65536),('B',5,20,262144)]:
   eligible=[q for q in profiles if q['mode']==mode and q['enc_mibs']>=e and q['dec_mibs']>=d and max(q['enc_rss_kib'],q['dec_rss_kib'])<=rss]
   winner=min(eligible,key=lambda x:x['bytes']) if eligible else None
   budgets[mode+'-'+key]=dict(winner=winner,excess=winner['bytes']/refsize-1 if winner and refsize else None,worst_pass=bool(winner and winner['enc_worst_mibs']>=e and winner['dec_worst_mibs']>=d))
 var={mode:statistics.median([x for q in profiles if q['mode']==mode for phase in ('enc','dec') for x in q[phase+'_wall_ranges']]) for mode in ('prealloc','alloc')} if profiles else {}
 return dict(type='summary',group=g,files=nfiles,reference=refsize,profiles=profiles,budgets=budgets,wall_range_median=var)
def bench(root,out,smoke):
 root=root.resolve();root.joinpath('tmp').mkdir(parents=True,exist_ok=True)
 lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 require(shutil.disk_usage(root).free>=5*1024**3,'disk safety floor')
 require(int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))>=1024**2,'memory safety floor')
 cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu});os.nice(10)
 timer=root/'bin/time' if not smoke else pathlib.Path('/usr/bin/time');require(timer.is_file())
 reps=2 if smoke else 7;warm=1 if smoke else 2
 script=pathlib.Path(__file__).resolve();rows=[];refs=[]
 out.parent.mkdir(parents=True,exist_ok=True)
 with out.open('x') as f:
  def log(r):f.write(json.dumps(r,separators=(',',':'))+'\n');f.flush()
  libpaths=['/lib/x86_64-linux-gnu/'+x for x in ('liblz4.so.1','libzstd.so.1','libdeflate.so.0','libz.so.1')]
  log(dict(type='meta',protocol='H132',smoke=smoke,script_sha256=sha(script.read_bytes()),cpu=cpu,warmups=warm,reps=reps,libs={x:sha(pathlib.Path(x).read_bytes()) for x in libpaths},python=sys.version,packages=subprocess.run(['dpkg-query','-W','liblz4-1','libzstd1','libdeflate0','zlib1g'],capture_output=True,text=True).stdout))
  for g,name,b,src in sources(root,smoke):
   h=sha(b);log(dict(type='source',group=g,name=name,input_bytes=len(b),sha256=h,**src));order=[(c,l,m) for c,l in PROFILES for m in ('prealloc','alloc')];random.Random(h).shuffle(order);hashes={}
   with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h132-') as td:
    w=pathlib.Path(td);source=w/'input.bin';source.write_bytes(b);packed=w/'packed'; 
    for codec,level,mode in order:
     before=procstat(cpu);metrics={}
     for phase in ('enc','dec'):
      cmd=[sys.executable,str(script),'worker',phase,str(source),str(packed),codec,str(level),mode,str(warm),str(reps)]
      q=run(cmd,w,timer);v=json.loads((w/'stdout').read_text());q.update(v);metrics[phase]=q
     digest=sha(packed.read_bytes());require(hashes.setdefault((codec,level),digest)==digest,'cross-mode archive mismatch')
     r=dict(type='measurement',group=g,name=name,codec=codec,level=level,mode=mode,input_bytes=len(b),packed_bytes=packed.stat().st_size,archive_sha256=digest,checks=reps,before=before,after=procstat(cpu),**metrics);rows.append(r);log(r)
     print('PASS',name,codec,level,mode,reps,flush=True)
    if not smoke:
     for k in ('xz5','ppmd5'):
      r=reference(w,source,b,timer,k);r.update(type='reference',group=g,name=name);refs.append(r);log(r)
  if smoke:
   log(dict(type='smoke-result',checks=sum(r['checks'] for r in rows),pairs=len(rows),primary_gate='NOT_RUN'));return
  summaries=[summarize(rows,refs,g) for g in ('silesia','local')]
  for q in summaries:log(q)
  complete=all(q['files']==2 and q['reference'] and len(q['profiles'])==12 for q in summaries) and len(rows)==48 and len(refs)==8
  gate={k:bool(complete and all(q['wall_range_median']['prealloc']<=.2 and q['budgets']['prealloc-'+k]['excess'] is not None and q['budgets']['prealloc-'+k]['excess']>=.2 and q['budgets']['prealloc-'+k]['worst_pass'] for q in summaries)) for k in 'AB'}
  log(dict(type='gate',complete=complete,nominate_A=gate['A'],nominate_B=not gate['A'] and gate['B'],checks=sum(r['checks'] for r in rows+refs)))
if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='worker':
  _,_,phase,src,packed,codec,level,mode,warm,reps=sys.argv;worker(phase,pathlib.Path(src),pathlib.Path(packed),codec,int(level),mode,int(warm),int(reps))
 else:
  p=argparse.ArgumentParser();p.add_argument('--lab',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--smoke',action='store_true');a=p.parse_args();bench(a.lab,a.out,a.smoke)
