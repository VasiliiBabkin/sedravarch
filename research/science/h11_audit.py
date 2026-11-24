#!/usr/bin/env python3
import argparse,ast,collections,fcntl,hashlib,io,json,lzma,math,os,pathlib,re,shutil,struct,subprocess,tempfile,zipfile,zlib
p=argparse.ArgumentParser();p.add_argument('--lab',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();root=a.lab.resolve()
os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);assert shutil.disk_usage(root).free>=5*1024**3
def sha(b):return hashlib.sha256(b).hexdigest()
dep=root/'experiments/h07b2/h07b2_precompression.py';assert sha(dep.read_bytes())=='cb984396ad8b5a118260f5e13d50e34d1eb8dab099a8b9c254cb2fc3fcdc0fc6'
MAX=2*1024**2
for node in ast.parse(dep.read_text()).body:
 if isinstance(node,ast.FunctionDef) and node.name in ('inflate','wrap','spans'):exec(compile(ast.Module(body=[node],type_ignores=[]),str(dep),'exec'))
driver=root/'experiments/h11/h11-driver'
def call(cmd):return subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20).stdout
def u(v):
 b=bytearray()
 while v>=128:b.append((v&127)|128);v>>=7
 b.append(v);return b
def sparse(lanes):
 out=bytearray()
 for v in lanes:
  nz=[(i,x) for i,x in enumerate(v) if x];out.extend(u(len(v)));out.extend(u(len(nz)));prev=-1
  for i,x in nz:out.extend(u(i-prev-1));out.extend(u(x-1));prev=i
 return bytes(out)
def unsparse(b):
 i=0;out=[]
 def read():
  nonlocal i
  x=s=0
  while True:
   v=b[i];i+=1;x|=(v&127)<<s
   if not v&128:return x
   s+=7;assert s<=35
 for _ in range(17):
  n=read();k=read();assert k<=n<=1000000;v=[0]*n;pos=-1
  for _ in range(k):pos+=read()+1;assert pos<n;v[pos]=read()+1
  out.append(v)
 assert i==len(b);return out
def kt(features):
 d=[collections.defaultdict(lambda:[0,0]) for _ in range(4)];loss=[0.]*5
 for l,dist,y in features:
  lb=sum(l>=x for x in (4,5,8,16,32));db=sum(dist>=x for x in (5,33,257,2049))
  keys=(0,lb,db,(lb,db));ps=[]
  for j,k in enumerate(keys):
   v=d[j][k];pr=(v[y]+.5)/(sum(v)+1);ps.append(pr);loss[j]-=math.log2(pr);v[y]+=1
  loss[4]-=math.log2((ps[0]+ps[3])/2)
 return loss
def measure(raw,plain,w,old):
 (w/'raw').write_bytes(raw)
 lines=call([str(driver),'trace',str(w/'raw'),str(w)]).decode().splitlines()
 baseline,cabac=map(int,lines[0].split());isolated=list(map(int,lines[1].split()));assert len(isolated)==17
 assert (w/'plain').read_bytes()==plain and baseline==old['corrections']
 params=(w/'params').read_bytes();lanes=[[] for _ in range(17)]
 for i,v in struct.iter_unpack('<BI',(w/'events').read_bytes()):lanes[i].append(v)
 counts=[[len(v),sum(x!=0 for x in v)] for v in lanes];assert counts==old['counts']
 f=list(struct.iter_unpack('<IIB',(w/'features').read_bytes()));assert [y for l,d,y in f]==lanes[16]
 b=sparse(lanes);sizes=[]
 for k,payload in enumerate((b,zlib.compress(b,9),lzma.compress(b,preset=5,check=lzma.CHECK_CRC64))):
  frame=struct.pack('<BI',k,len(params))+params+payload
  t,n=struct.unpack_from('<BI',frame);assert t==k;data=frame[5+n:];data=data if t==0 else zlib.decompress(data) if t==1 else lzma.decompress(data)
  restored=unsparse(data);assert restored==lanes
  dense=b''.join(struct.pack('<I',len(v))+b''.join(struct.pack('<I',x) for x in v) for v in restored)
  (w/'params2').write_bytes(frame[5:5+n]);(w/'dense').write_bytes(dense)
  call([str(driver),'decode',str(w/'plain'),str(w/'params2'),str(w/'dense'),str(w/'restored')]);assert (w/'restored').read_bytes()==raw
  sizes.append(len(frame))
 ent=[]
 for v in lanes:
  c=collections.Counter(v);ent.append(sum(-n*math.log2(n/len(v)) for n in c.values()))
 return dict(baseline=baseline,cabac=cabac,params=len(params),isolated=isolated,counts=counts,entropy_bits=ent,sizes=sizes,loss=kt(f),features=len(f),checks=4)
old=root/'results/h07b2-20261124.jsonl';assert sha(old.read_bytes())=='618421bf6b20e323e826b42eb78a4921463f9f215733532939aded677a2db963'
prev=root/'results/h10-20261124.jsonl';assert sha(prev.read_bytes())=='31da13486fc461e4d8a4beb7a304072a72fe0c856310f21f5589e2c64ade4dcd'
prior={r['name']:r for r in map(json.loads,prev.read_text().splitlines()) if r['type']=='sample'}
a.out.parent.mkdir(parents=True,exist_ok=True);rows=[]
with a.out.open('x') as out:
 def log(r):out.write(json.dumps(r)+'\n');out.flush()
 log(dict(type='meta',protocol='H11',driver_sha256=sha(driver.read_bytes()),script_sha256=sha(pathlib.Path(__file__).read_bytes())))
 for x in map(json.loads,old.read_text().splitlines()):
  if x['type']!='sample':continue
  with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h11-') as td:
   w=pathlib.Path(td)
   try:call(['curl','-fLsS','--proto','=https','--max-time','15','--max-filesize','750000','-o',str(w/'source'),x['url']]);b=(w/'source').read_bytes();assert sha(b)==x['sha256']
   except (OSError,AssertionError,subprocess.SubprocessError) as e:log(dict(type='skip',name=x['name'],error=repr(e)));continue
   rr=spans(b,x['group']);total=0;stats=[];pr={s['offset']:s for s in prior[x['name']]['streams']}
   for s,e,c,p,mode,lens in rr:
    if len(c)>131072 or len(p)>262144 or total+len(p)>1048576:continue
    total+=len(p);assert wrap(c,lens)==b[s:e];raw=c[2:-4] if mode==15 else c
    r=measure(raw,p,w,pr[s]);r.update(offset=s,compressed=len(c),plain=len(p));stats.append(r)
   assert len(stats)==len(pr)
   row=dict(type='sample',group=x['group'],name=x['name'],sha256_input=sha(b),streams=stats);log(row);rows.append(row)
   print(row['group'],row['name'],len(stats),sum(s['baseline'] for s in stats),sum(min(s['sizes']) for s in stats),flush=True)
 for g in ('pdf','docx','xlsx','zip','png','all'):
  rr=[r for r in rows if g=='all' or r['group']==g];ss=[s for r in rr for s in r['streams']]
  base=sum(s['baseline'] for s in ss);oracle=sum(min(s['sizes']) for s in ss)
  result=dict(type='summary',group=g,files=len(rr),streams=len(ss),baseline=base,cabac=sum(s['cabac'] for s in ss),params=sum(s['params'] for s in ss),isolated=[sum(s['isolated'][i] for s in ss) for i in range(17)],counts=[[sum(s['counts'][i][j] for s in ss) for j in range(2)] for i in range(17)],entropy_bits=[sum(s['entropy_bits'][i] for s in ss) for i in range(17)],sizes=[sum(s['sizes'][i] for s in ss) for i in range(3)],oracle=oracle,wins=sum(min(s['sizes'])<s['baseline'] for s in ss),loss=[sum(s['loss'][i] for s in ss) for i in range(5)],features=sum(s['features'] for s in ss),checks=sum(s['checks'] for s in ss))
  log(result);print(json.dumps(result),flush=True)
