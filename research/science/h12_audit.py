#!/usr/bin/env python3
"""H12: equal-frame conditional channel comparison, exact whole-file recovery."""
import argparse,ast,fcntl,hashlib,io,json,lzma,os,pathlib,re,shutil,struct,subprocess,tempfile,time,zipfile,zlib
p=argparse.ArgumentParser();p.add_argument('--lab',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();root=a.lab.resolve()
os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);assert shutil.disk_usage(root).free>=5*1024**3
def sha(b):return hashlib.sha256(b).hexdigest()
def xz(b):return lzma.compress(b,preset=5,check=lzma.CHECK_CRC64)
dep=root/'experiments/h07b2/h07b2_precompression.py';assert sha(dep.read_bytes())=='cb984396ad8b5a118260f5e13d50e34d1eb8dab099a8b9c254cb2fc3fcdc0fc6'
MAX=2*1024**2
for node in ast.parse(dep.read_text()).body:
 if isinstance(node,ast.FunctionDef) and node.name in ('inflate','wrap','spans'):exec(compile(ast.Module(body=[node],type_ignores=[]),str(dep),'exec'))
driver=root/'experiments/h12/h12-driver'
gnu=root/'bin/time';use_time=gnu.is_file()
def call(cmd,timeout=30):return subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout).stdout
def timed(args,w):
 t=time.perf_counter_ns()
 out=call(([str(gnu),'-f','%M','-o',str(w/'rss')]+args) if use_time else args)
 return out,time.perf_counter_ns()-t,int((w/'rss').read_text().strip()) if use_time else None
def rec(tag,b):return struct.pack('<BI',tag,len(b))+b
def decode_record(body,w):
 z,n,pl,cl=struct.unpack_from('<BIII',body);i=13;wrapper=body[i:i+6] if z else b'';i+=6 if z else 0
 lengths=list(struct.unpack_from('<'+'I'*n,body,i));i+=4*n;assert i+pl+cl==len(body)
 (w/'plain2').write_bytes(body[i:i+pl]);(w/'corr2').write_bytes(body[i+pl:])
 _,wall,rss=timed([str(driver),'decode',str(w/'plain2'),str(w/'corr2'),str(w/'rawout')],w)
 raw=(w/'rawout').read_bytes();return wrap(wrapper[:2]+raw+wrapper[2:] if z else raw,lengths),wall,rss
def gzip_span(b):
 assert len(b)<=524288 and b[:3]==b'\x1f\x8b\x08'
 flags=b[3];assert not flags&224;i=10
 if flags&4:
  n=struct.unpack_from('<H',b,i)[0];i+=2+n
 for bit in (8,16):
  if flags&bit:i=b.index(0,i)+1
 if flags&2:i+=2
 assert i<len(b)-8
 raw=b[i:-8];d=zlib.decompressobj(-15);p=d.decompress(raw,2097153)
 assert len(p)<=2097152 and d.eof and not d.unused_data and not d.unconsumed_tail
 assert zlib.crc32(p)==struct.unpack_from('<I',b,len(b)-8)[0] and len(p)==struct.unpack_from('<I',b,len(b)-4)[0]
 assert zlib.decompress(b,31)==p
 return [(i,len(b)-8,raw,p,-15,[])]
def measure(b,g,w,prior=None):
 rr=gzip_span(b) if g.startswith('new-') else spans(b,g);pos=total=0;rows=[];out=[bytearray() for _ in range(3)];selected=[0]*3;checks=0
 for s,e,c,p,mode,lens in rr:
  if not g.startswith('new-') and (len(c)>131072 or len(p)>262144 or total+len(p)>1048576):continue
  total+=len(p);assert wrap(c,lens)==b[s:e]
  original=rec(0,b[s:e])
  for k in range(3):
   if s>pos:out[k].extend(rec(0,b[pos:s]))
  pos=e
  raw=c[2:-4] if mode==15 else c;(w/'raw').write_bytes(raw)
  row=dict(offset=s,compressed=len(c),plain=len(p),sha256=sha(raw))
  try:
   log,wall,rss=timed([str(driver),'encode',str(w/'raw'),str(w)],w)
  except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
   if isinstance(exc,subprocess.CalledProcessError) and exc.returncode!=2:raise
   row.update(status='rejected',error=repr(exc),stderr=(getattr(exc,'stderr',None) or b'').decode(errors='replace')[-500:])
   for k in range(3):out[k].extend(original)
   rows.append(row);continue
  n,base_ns,l_ns,m_ns=map(int,log.decode().split());assert (w/'plain').read_bytes()==p
  corr=[(w/f'corr{k}').read_bytes() for k in range(3)]
  if prior is not None:
   assert len(corr[0])==prior[s]['corrections']+1 and n==prior[s]['counts'][16][0]
  rb=len(xz(original));local=[];chosen=[];decode_ns=[];decode_rss=[]
  for k,v in enumerate(corr):
   body=struct.pack('<BIII',int(mode==15),len(lens),len(p),len(v))+(c[:2]+c[-4:] if mode==15 else b'')+b''.join(struct.pack('<I',x) for x in lens)+p+v
   restored,dw,dr=decode_record(body,w);assert restored==b[s:e];checks+=1;decode_ns.append(dw);decode_rss.append(dr)
   r=rec(1,body);size=len(xz(r));use=size<rb;local.append(size);chosen.append(use);selected[k]+=use
   out[k].extend(r if use else original)
  row.update(status='pass',features=n,sizes=list(map(len,corr)),corr_sha256=list(map(sha,corr)),raw_record_xz=rb,local_xz=local,selected=chosen,encode_wall_ns=wall,encode_peak_rss_kib=rss,internal_phase_ns=[base_ns,l_ns,m_ns],decode_wall_ns=decode_ns,decode_peak_rss_kib=decode_rss);rows.append(row)
 results=[]
 for k in range(3):
  if pos<len(b):out[k].extend(rec(0,b[pos:]))
  frame=struct.pack('<4sII',b'H12A',len(b),zlib.crc32(b))+xz(out[k])
  magic,n,crc=struct.unpack_from('<4sII',frame);assert magic==b'H12A';data=lzma.decompress(frame[12:]);i=0;rest=bytearray();t=time.perf_counter_ns()
  while i<len(data):
   tag,nr=struct.unpack_from('<BI',data,i);i+=5;v=data[i:i+nr];i+=nr;assert len(v)==nr
   rest.extend(v if tag==0 else decode_record(v,w)[0])
  assert i==len(data) and len(rest)==n and zlib.crc32(rest)==crc and rest==b;checks+=1
  results.append(dict(bytes=len(frame),sha256=sha(frame),selected=selected[k],decode_records_wall_ns=time.perf_counter_ns()-t))
 assert prior is None or len(rows)==len(prior)
 return dict(streams=rows,detected=len(rr),frames=results,checks=checks)
old=root/'results/h07b2-20261124.jsonl';assert sha(old.read_bytes())=='618421bf6b20e323e826b42eb78a4921463f9f215733532939aded677a2db963'
prev=root/'results/h10-20261124.jsonl';assert sha(prev.read_bytes())=='31da13486fc461e4d8a4beb7a304072a72fe0c856310f21f5589e2c64ade4dcd'
prior={r['name']:{s['offset']:s for s in r['streams']} for r in map(json.loads,prev.read_text().splitlines()) if r['type']=='sample'}
new={'new-text':['/usr/share/doc/nginx/changelog.gz','/usr/share/doc/coreutils/NEWS.gz','/usr/share/man/man1/bash.1.gz','/usr/share/info/coreutils.info.gz'],'new-binary':['/usr/share/doc/fontconfig/fontconfig-user.pdf.gz']+['/usr/share/doc/icecast2/assets/font/FiraSans-'+x+'.eot.gz' for x in ('Regular','Italic','Bold')]}
a.out.parent.mkdir(parents=True,exist_ok=True);rows=[]
with a.out.open('x') as f:
 def log(r):f.write(json.dumps(r)+'\n');f.flush()
 log(dict(type='meta',protocol='H12',driver_sha256=sha(driver.read_bytes()),script_sha256=sha(pathlib.Path(__file__).read_bytes()),gnu_time=use_time,affinity=sorted(os.sched_getaffinity(0))))
 # New panels first, so any external-source timeout cannot prevent new measurements.
 for g,paths in new.items():
  for path in paths:
   with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h12-') as td:
    w=pathlib.Path(td)
    try:b=pathlib.Path(path).read_bytes();gzip_span(b)
    except (OSError,ValueError,AssertionError,zlib.error) as exc:log(dict(type='skip',group=g,path=path,error=repr(exc)));print('SKIP',path,repr(exc),flush=True);continue
    (w/'source').write_bytes(b);c=xz(b);assert lzma.decompress(c)==b
    z=call(['zstd','-q','-T1','-15','-c',str(w/'source')]);(w/'source.zst').write_bytes(z);assert call(['zstd','-q','-d','-c',str(w/'source.zst')])==b
    r=measure(b,g,w);r['checks']+=2;r.update(type='sample',group=g,name=pathlib.Path(path).name,path=path,sha256_input=sha(b),input_bytes=len(b),strong=min(len(c),len(z)),controls={'xz5':len(c),'zstd15':len(z)});rows.append(r);log(r)
    print(g,r['name'],[s.get('sizes',s.get('error')) for s in r['streams']],[x['bytes'] for x in r['frames']],flush=True)
 for x in map(json.loads,old.read_text().splitlines()):
  if x['type']!='sample':continue
  with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h12-') as td:
   w=pathlib.Path(td)
   try:call(['curl','-fLsS','--proto','=https','--max-time','15','--max-filesize','750000','-o',str(w/'source'),x['url']]);b=(w/'source').read_bytes();assert sha(b)==x['sha256']
   except (OSError,AssertionError,subprocess.SubprocessError) as e:log(dict(type='skip',group=x['group'],name=x['name'],error=repr(e)));continue
   r=measure(b,x['group'],w,prior[x['name']]);r.update(type='sample',group=x['group'],name=x['name'],url=x['url'],sha256_input=sha(b),input_bytes=len(b),strong=min(x['candidates'][k]['bytes'] for k in ('xz5','zstd15','7z','precomp-xz5')));rows.append(r);log(r)
   print(r['group'],r['name'],len(r['streams']),[x['bytes'] for x in r['frames']],flush=True)
 summaries={}
 for g in ('new-text','new-binary','pdf','docx','xlsx','zip','png','old-all'):
  rr=[r for r in rows if r['group']==g or (g=='old-all' and not r['group'].startswith('new-'))];ss=[s for r in rr for s in r['streams']];pp=[s for s in ss if s['status']=='pass']
  q=dict(type='summary',group=g,files=len(rr),streams=len(ss),passed=len(pp),corr=[sum(s['sizes'][k] for s in pp) for k in range(3)],frames=[sum(r['frames'][k]['bytes'] for r in rr) for k in range(3)],strong=sum(r['strong'] for r in rr),wins=[sum(s['sizes'][k]<s['sizes'][0] for s in pp) for k in (1,2)],features=sum(s['features'] for s in pp),checks=sum(r['checks'] for r in rr),input_bytes=sum(r['input_bytes'] for r in rr),plain=sum(s['plain'] for s in ss))
  summaries[g]=q;log(q);print(json.dumps(q),flush=True)
 nn=[summaries[g] for g in ('new-text','new-binary')];complete=all(x['files']==x['streams']==x['passed']==4 for x in nn)
 r=dict(type='gate',complete=complete,a=complete and sum(x['wins'][0] for x in nn)>=4 and all(x['corr'][1]<=.95*x['corr'][0] for x in nn),b=complete and all(x['frames'][1]<=.99*x['frames'][0] and x['frames'][1]<=.95*x['strong'] for x in nn),checks=sum(r['checks'] for r in rows))
 log(r);print(json.dumps(r),flush=True)
