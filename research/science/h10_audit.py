#!/usr/bin/env python3
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
driver=root/'experiments/h10/h10-driver'
def call(args,cwd=None):return subprocess.run(args,cwd=cwd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20).stdout
def rec(tag,b):return struct.pack('<BI',tag,len(b))+b
def reconstruct(body,w):
 z,n,pl,cl=struct.unpack_from('<BIII',body);i=13
 wrapper=body[i:i+6] if z else b'';i+=6 if z else 0
 lengths=list(struct.unpack_from('<'+'I'*n,body,i));i+=4*n
 assert len(body)==i+pl+cl
 (w/'plain').write_bytes(body[i:i+pl]);(w/'corr').write_bytes(body[i+pl:])
 call([str(driver),'decode',str(w/'plain'),str(w/'corr'),str(w/'rawout')])
 raw=(w/'rawout').read_bytes();c=wrapper[:2]+raw+wrapper[2:] if z else raw
 return wrap(c,lengths)
def measure(b,g,w):
 rr=spans(b,g);stats=[];pos=total=0;out=bytearray();selected=0
 for s,e,c,p,mode,lens in rr:
  if len(c)>131072 or len(p)>262144 or total+len(p)>1048576:continue
  assert wrap(c,lens)==b[s:e];total+=len(p)
  if s>pos:out.extend(rec(0,b[pos:s]))
  original=rec(0,b[s:e]);raw=c[2:-4] if mode==15 else c;(w/'raw').write_bytes(raw)
  row=dict(offset=s,compressed=len(c),plain=len(p))
  try:log=call([str(driver),'encode',str(w/'raw'),str(w/'plain'),str(w/'corr')]).decode()
  except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
   row.update(status='rejected',error=repr(exc),stderr=(getattr(exc,'stderr',None) or b'').decode(errors='replace')[-500:]);out.extend(original);stats.append(row);pos=e;continue
  pp=(w/'plain').read_bytes();corr=(w/'corr').read_bytes();assert pp==p
  counts=[]
  for line in log.splitlines():
   i,n,z=map(int,line.split());assert i==len(counts) and 0<=z<=n;counts.append([n,z])
  assert len(counts)==17
  body=struct.pack('<BIII',int(mode==15),len(lens),len(p),len(corr))+(c[:2]+c[-4:] if mode==15 else b'')+b''.join(struct.pack('<I',v) for v in lens)+p+corr
  assert reconstruct(body,w)==b[s:e]
  rr0=len(xz(original));rr1=len(xz(rec(1,body)));use=rr1<rr0
  selected+=use;out.extend(rec(1,body) if use else original);pos=e
  row.update(status='pass',counts=counts,corrections=len(corr),corrections_xz=len(xz(corr)),plaintext_xz=len(xz(p)),raw_record_xz=rr0,struct_record_xz=rr1,selected=use);stats.append(row)
 if pos<len(b):out.extend(rec(0,b[pos:]))
 frame=struct.pack('<4sII',b'H10A',len(b),zlib.crc32(b))+xz(out)
 magic,n,crc=struct.unpack_from('<4sII',frame);assert magic==b'H10A';data=lzma.decompress(frame[12:]);i=0;restore=bytearray()
 while i<len(data):
  tag,k=struct.unpack_from('<BI',data,i);i+=5;v=data[i:i+k];i+=k;assert len(v)==k
  restore.extend(v if tag==0 else reconstruct(v,w))
 assert i==len(data) and len(restore)==n and zlib.crc32(restore)==crc and restore==b
 return dict(bytes=len(frame),selected=selected,sha256=sha(frame),detected=len(rr),streams=stats,checks=1+sum(x['status']=='pass' for x in stats))
a.out.parent.mkdir(parents=True,exist_ok=True);old=root/'results/h07b2-20261124.jsonl';assert sha(old.read_bytes())=='618421bf6b20e323e826b42eb78a4921463f9f215733532939aded677a2db963';rows=[]
with a.out.open('x') as f:
 def log(r):f.write(json.dumps(r)+'\n');f.flush()
 log(dict(type='meta',protocol='H10',driver_sha256=sha(driver.read_bytes()),script_sha256=sha(pathlib.Path(__file__).read_bytes()),source='preflate-rs 0.7.6 instrumented',old_sha256=sha(old.read_bytes())))
 for x in map(json.loads,old.read_text().splitlines()):
  if x['type']!='sample':continue
  with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h10-') as td:
   w=pathlib.Path(td)
   try:
    call(['curl','-fLsS','--proto','=https','--max-time','15','--max-filesize','750000','-o',str(w/'source'),x['url']]);b=(w/'source').read_bytes();assert sha(b)==x['sha256']
   except (OSError,AssertionError,subprocess.SubprocessError) as e:log(dict(type='skip',name=x['name'],error=repr(e)));continue
   t=time.perf_counter();r=measure(b,x['group'],w);r.update(type='sample',group=x['group'],name=x['name'],sha256_input=sha(b),strong=min(x['candidates'][k]['bytes'] for k in ('xz5','zstd15','7z','precomp-xz5')),ordinary=min(x['candidates'][k]['bytes'] for k in ('xz5','zstd15','7z')),wall_s=time.perf_counter()-t);log(r);rows.append(r)
   print(r['group'],r['name'],r['strong'],r['bytes'],r['selected'],len(r['streams']),sum(y['status']=='pass' for y in r['streams']),flush=True)
 for g in ('pdf','docx','xlsx','zip','png','all'):
  rr=[r for r in rows if g=='all' or r['group']==g];ss=[s for r in rr for s in r['streams']];pp=[s for s in ss if s['status']=='pass']
  result=dict(type='summary',group=g,samples=len(rr),strong=sum(r['strong'] for r in rr),ordinary=sum(r['ordinary'] for r in rr),bytes=sum(r['bytes'] for r in rr),detected=sum(r['detected'] for r in rr),analyzed=len(ss),passed=len(pp),selected=sum(r['selected'] for r in rr),checks=sum(r['checks'] for r in rr),counts=[[sum(s['counts'][i][j] for s in pp) for j in (0,1)] for i in range(17)],components={k:sum(s[k] for s in pp) for k in ('compressed','plain','corrections','corrections_xz','plaintext_xz','raw_record_xz','struct_record_xz')})
  log(result);print(json.dumps(result),flush=True)
