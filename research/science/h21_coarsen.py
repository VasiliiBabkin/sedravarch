#!/usr/bin/env python3
import argparse,collections,fcntl,gzip,hashlib,importlib.util,json,lzma,os,pathlib,resource,shutil,struct,subprocess,sys,tarfile,tempfile,time,zipfile,zlib
BASE='https://zenodo.org/records/8196385/files/'
SOURCES=[('new','Mac','Mac.tar.gz'),('new','HealthApp','HealthApp.tar.gz'),('new','HPC','HPC.zip'),('new','Proxifier','Proxifier.tar.gz'),('old','Apache','Apache.tar.gz'),('old','OpenStack','OpenStack.tar.gz')]
MAX=2*1024**2; CAP=32*1024**2
def sha(b):return hashlib.sha256(b).hexdigest()
def load(root):
 p=root/'experiments/h18/h18_h20_logs.py';assert sha(p.read_bytes())=='1b71aaa8778c46ef4b82f16162f32304df58df8b42d99f49b111a80fab911298'
 spec=importlib.util.spec_from_file_location('h18',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def record(m,rows):
 assert rows and all(len(x)==len(rows[0]) for x in rows)
 out=bytearray(m.v(len(rows))+m.v(len(rows[0])))
 for col in zip(*rows):
  if all(x==col[0] for x in col):out.extend(b'\0'+m.pack(col[0]))
  else:
   raw=b''.join(m.pack(x) for x in col);d=m.delta(col)
   use=d is not None and len(d)<len(raw)
   out.extend(bytes([2 if use else 1])+m.pack(d if use else raw))
 return bytes(out)
def coarsen(m,b):
 rows=b.splitlines(keepends=True);assert b''.join(rows)==b
 shapes={}
 for i,line in enumerate(rows):
  fs=m.TOK.findall(line);assert b''.join(fs)==line
  ty=tuple(0 if 65<=x[0]<=90 or 97<=x[0]<=122 or x[0]==95 else 1 if 48<=x[0]<=57 else 2 for x in fs)
  anchor=tuple(x for x,t in zip(fs,ty) if t==0)[:2]
  shapes.setdefault(ty,{}).setdefault(anchor,[]).append((i,fs))
 def best(g):
  a=record(m,[x[1] for x in g]);r=record(m,[[rows[x[0]]] for x in g])
  return (r,True) if len(r)<len(a) else (a,False)
 groups=[];merged=0;anchors=0;raw_groups=0;split_cost=0;chosen_cost=0
 for shape in shapes.values():
  split=[(g,*best(g)) for g in shape.values()];anchors+=len(split)
  union=sorted([x for g in shape.values() for x in g],key=lambda x:x[0]);rec,raw=best(union)
  cost=sum(len(x[1]) for x in split);split_cost+=cost
  if len(split)>1 and len(rec)<cost:
   chosen=[(union,rec,raw)];merged+=len(split)-1
  else:chosen=split
  chosen_cost+=sum(len(x[1]) for x in chosen);groups.extend(chosen)
 # order group IDs by earliest row
 groups.sort(key=lambda x:x[0][0][0]);order=[None]*len(rows)
 for k,(g,r,raw) in enumerate(groups):
  raw_groups+=raw
  for i,_ in g:assert order[i] is None;order[i]=k
 seq=b''.join(m.v(i) for i in order);head=m.v(len(rows))+m.v(len(groups))
 body=head+b''.join(x[1] for x in groups)+seq
 assert m.decode(body)==b
 return body,dict(groups=len(groups),anchors=anchors,merged=merged,raw_groups=raw_groups,record_bytes=chosen_cost,split_record_bytes=split_cost,order_bytes=len(seq),inner_bytes=len(body))
def candidate(root,w):
 m=load(root);b=(w/'input.bin').read_bytes();sizes={};hashes={};stats={}
 for mode,k in enumerate('ABCD'):
  body,st=(b,dict(inner_bytes=len(b))) if mode==0 else m.encode(b,mode)
  c=m.frame(b,mode,body);assert m.unframe(c)==b
  (w/k).write_bytes(c);sizes[k]=len(c);hashes[k]=sha(c);stats[k]=st
 body,st=coarsen(m,b);c=m.frame(b,3,body);assert m.unframe(c)==b
 (w/'E').write_bytes(c);sizes['E']=len(c);hashes['E']=sha(c);stats['E']=st
 selected=min(sizes,key=sizes.get);shutil.copyfile(w/selected,w/'F')
 sizes['F']=sizes[selected];hashes['F']=hashes[selected]
 print(json.dumps(dict(sizes=sizes,hashes=hashes,stats=stats,selected=selected,checks=5)))
def specialized(root,w):
 sys.path.insert(0,str(root/'experiments/h21/logfold/src'))
 from logfold.codec import compress,decompress,serialize,deserialize
 from logfold.logio import split_text,join_lines,had_trailing_newline
 b=(w/'input.bin').read_bytes();t=b.decode('utf-8')
 raw=serialize(compress(split_text(t),trailing_newline=had_trailing_newline(t)))
 result={}
 for k,c in [('logfold',gzip.compress(raw,compresslevel=9,mtime=0)),('logfold-xz',lzma.compress(raw,preset=5,check=lzma.CHECK_CRC64))]:
  restored=gzip.decompress(c) if k=='logfold' else lzma.decompress(c)
  a=deserialize(restored);x=join_lines(decompress(a),trailing_newline=a.trailing_newline).encode('utf-8')
  result[k]=dict(exact=x==b,bytes=len(c),sha256=sha(c))
 print(json.dumps(result))
def call(cmd,w,timeout=45):
 return subprocess.run(cmd,cwd=w,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout).stdout
def timed(root,cmd,w,timeout):
 t=time.perf_counter_ns()
 q=call([str(root/'bin/time'),'-f','%U %S %M','-o','metrics','--',*cmd],w,timeout)
 u,s,r=(w/'metrics').read_text().split()
 return json.loads(q),dict(wall_ns=time.perf_counter_ns()-t,cpu_s=float(u)+float(s),rss_kib=int(r))
def getdata(w,name):
 url=BASE+name+'?download=1';p=w/'source'
 call(['curl','-fLsS','--proto','=https','--max-time','40','--retry','1','--max-filesize',str(CAP),'-o',str(p),url],w,90)
 assert 0<p.stat().st_size<=CAP
 if name.endswith('.zip'):
  with zipfile.ZipFile(p) as f:
   entries=[x for x in f.infolist() if not x.is_dir() and x.filename.lower().endswith('.log')]
   x=sorted(entries,key=lambda x:(-x.file_size,x.filename))[0];assert x.file_size<=128*1024**2
   member=x.filename;raw=f.read(x)
 else:
  with tarfile.open(p,'r:gz') as f:
   entries=[x for x in f.getmembers() if x.isfile() and x.name.lower().endswith('.log')]
   x=sorted(entries,key=lambda x:(-x.size,x.name))[0];assert x.size<=128*1024**2
   member=x.name;raw=f.extractfile(x).read()
 offset=0
 for _ in range(2000):
  i=raw.find(b'\n',offset);assert i>=0;offset=i+1
 b=raw[offset:offset+MAX];end=b.rfind(b'\n');assert end>=0;b=b[:end+1];assert b
 return b,dict(url=url,archive_sha256=sha(p.read_bytes()),archive_bytes=p.stat().st_size,member=member,member_sha256=sha(raw),member_bytes=len(raw),offset=offset)
def main(root,out):
 root=root.resolve();lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 assert shutil.disk_usage(root).free>=5*1024**3 and int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))>=1024**2
 resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,)*2);resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024**2,)*2)
 m=load(root);script=str(pathlib.Path(__file__).resolve());rows=[]
 assert call(['git','-C',str(root/'experiments/h21/logfold'),'rev-parse','HEAD'],root).decode().strip()=='0330396bbe2bc7c44ea07e24d0c57b8725f7bbc2'
 with out.open('x') as f:
  def log(r):f.write(json.dumps(r,separators=(',',':'))+'\n');f.flush()
  log(dict(type='meta',protocol='H21',script_sha256=sha(pathlib.Path(script).read_bytes()),logfold_commit='0330396bbe2bc7c44ea07e24d0c57b8725f7bbc2',affinity=sorted(os.sched_getaffinity(0))))
  for g,n,name in SOURCES:
   with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h21-') as td:
    w=pathlib.Path(td)
    try:b,src=getdata(w,name)
    except (OSError,ValueError,IndexError,AssertionError,subprocess.SubprocessError,tarfile.TarError,zipfile.BadZipFile) as e:
     log(dict(type='skip',group=g,name=n,error=repr(e)));print('SKIP',n,repr(e),flush=True);continue
    (w/'input.bin').write_bytes(b);print('SOURCE',n,len(b),flush=True)
    cand,tm=timed(root,[sys.executable,script,'candidate',str(root),str(w)],w,90);sizes=cand['sizes'];hashes=cand['hashes'];checks=cand['checks']
    _,dec_tm=timed(root,[sys.executable,script,'decode',str(root),str(w)],w,45);assert (w/'restored').read_bytes()==b;checks+=1
    c=m.xz(b);assert lzma.decompress(c)==b;sizes['xz5']=len(c);hashes['xz5']=sha(c);checks+=1
    c=call(['zstd','-q','-T1','-19','-c','input.bin'],w,90);(w/'control.zst').write_bytes(c);assert call(['zstd','-q','-d','-c','control.zst'],w)==b;sizes['zstd19']=len(c);hashes['zstd19']=sha(c);checks+=1
    for k,method in [('ppmd5','PPMd'),('7z5','LZMA2')]:
     call(['7z','a','-t7z','-m0='+method,'-mx=5','-mmt=1','-mtc=off','-mta=off','-mtm=off',k+'.7z','input.bin'],w,90)
     c=(w/(k+'.7z')).read_bytes();assert call(['7z','x','-so','-mmt=1',k+'.7z'],w)==b;sizes[k]=len(c);hashes[k]=sha(c);checks+=1
    try:
     sp,sp_tm=timed(root,[sys.executable,script,'specialized',str(root),str(w)],w,90)
     for k,x in sp.items():
      if x['exact']:sizes[k]=x['bytes'];hashes[k]=x['sha256'];checks+=1
    except (OSError,ValueError,subprocess.SubprocessError) as e:sp=dict(error=repr(e));sp_tm=None
    r=dict(type='sample',group=g,name=n,input_bytes=len(b),sha256_input=sha(b),lines=b.count(b'\n'),sizes=sizes,hashes=hashes,stats=cand['stats'],selected=cand['selected'],checks=checks,candidate_metrics=tm,decode_F_metrics=dec_tm,specialized=sp,specialized_metrics=sp_tm,**src)
    rows.append(r);log(r);print(n,sizes,'selected',cand['selected'],'checks',checks,flush=True)
  summaries=[]
  for g in ('new','old'):
   rr=[r for r in rows if r['group']==g];controls=('xz5','zstd19','ppmd5','7z5','logfold','logfold-xz')
   strong=[min(r['sizes'][k] for k in controls if k in r['sizes']) for r in rr]
   sizes={k:sum(r['sizes'][k] for r in rr) for k in 'ABCDEF'}
   q=dict(type='summary',group=g,files=len(rr),input_bytes=sum(r['input_bytes'] for r in rr),sizes=sizes,strong=sum(strong),best_AD=sum(min(r['sizes'][k] for k in 'ABCD') for r in rr),wins={k:sum(r['sizes'][k]<s for r,s in zip(rr,strong)) for k in 'EF'},specialized_complete=all(all(k in r['sizes'] for k in controls) for r in rr),checks=sum(r['checks'] for r in rr));summaries.append(q);log(q);print(json.dumps(q),flush=True)
  q=summaries[0];complete=q['files']==4 and q['specialized_complete'];gate=dict(type='gate',complete=complete,F=bool(complete and q['sizes']['F']<=.95*q['strong'] and q['wins']['F']>=3),E=bool(complete and q['sizes']['E']<=.97*q['sizes']['D'] and q['sizes']['E']<=.95*q['strong'] and q['wins']['E']>=3),incremental=bool(complete and q['sizes']['F']<=.99*q['best_AD']),checks=sum(r['checks'] for r in rows));log(gate);print(json.dumps(gate),flush=True)
if __name__=='__main__':
 if sys.argv[1] in ('candidate','specialized','decode'):
  mode=sys.argv[1];root,w=map(pathlib.Path,sys.argv[2:])
  if mode=='candidate':candidate(root,w)
  elif mode=='specialized':specialized(root,w)
  else:
   (w/'restored').write_bytes(load(root).unframe((w/'F').read_bytes()));print('{}')
 else:
  p=argparse.ArgumentParser();p.add_argument('--lab',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();main(a.lab,a.out)
