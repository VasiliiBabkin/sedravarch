#!/usr/bin/env python3
import argparse,ctypes,fcntl,hashlib,importlib.util,json,lzma,os,pathlib,resource,shutil,struct,subprocess,tempfile,zlib
B=262144;MODES=('G','F','E','W8','W32');ALL=MODES+('D','zstd6','zstd9','xz5')
def sha(b):return hashlib.sha256(b).hexdigest()
def load(root):
 p=root/'experiments/h14/h14_bounded_lz.py';assert sha(p.read_bytes())=='6e17c43d344a63aafecbb63f063cebf1109fedde5a18590953b75179727ab404'
 spec=importlib.util.spec_from_file_location('h14',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def sources(root):
 m=json.loads((root/'corpora/manifest.json').read_text())
 for name in ('dickens','mr','ooffice','samba','x-ray','xml'):
  x=next(v for v in m if v['group']=='silesia' and pathlib.Path(v['path']).name==name);b=(root/x['path']).read_bytes();assert sha(b)==x['sha256'];off=(len(b)-B)*3//5
  yield 'silesia',name,b[off:off+B],dict(path=x['path'],full_sha256=x['sha256'],offset=off)
 for path in ('/usr/bin/readelf','/usr/bin/objdump','/usr/bin/openssl','/usr/lib/python3.12/ast.py','/usr/lib/python3.12/dis.py','/usr/lib/python3.12/tokenize.py'):
  b=pathlib.Path(path).read_bytes();yield 'local',pathlib.Path(path).name,b[:B],dict(path=path,full_sha256=sha(b),offset=0)
 for x in m:
  if x['group']=='synthetic':
   b=(root/x['path']).read_bytes();assert sha(b)==x['sha256'];yield 'synthetic',pathlib.Path(x['path']).name,b,dict(path=x['path'],full_sha256=x['sha256'],offset=0)
def parses(block,w,exe,h14):
 (w/'block').write_bytes(block);subprocess.run([str(exe),str(w/'block'),str(w/'commands')],check=True,timeout=45)
 b=(w/'commands').read_bytes();pos=0;out={}
 for mode in MODES:
  n=struct.unpack_from('<I',b,pos)[0];pos+=4;assert n<=len(block)//4
  seq=[];i=0
  for _ in range(n):
   p,l,d=struct.unpack_from('<IHH',b,pos);pos+=8;assert i<=p and p+l<=len(block) and 4<=l<=258 and 0<d<=min(p,65535) and block[p:p+l]==block[p-d:p-d+l]
   seq.append((block[i:p],l,d));i=p+l
  sc=struct.unpack_from('<QQQQ',b,pos);pos+=32
  out[mode]=(seq,block[i:],sc)
 assert pos==len(b);assert out['G'][:2]==h14.parse(block)
 assert out['F'][2][0]<=out['G'][2][0] and out['E'][2][1]<=min(out['G'][2][1],out['F'][2][1])
 assert out['W8'][2][2]<=out['E'][2][2] and out['W32'][2][3]<=out['E'][2][3]
 return out
def measure(b,w,exe,h14):
 frames={k:bytearray(struct.pack('<4sBII',b'H14A',3 if k=='D' else 1,len(b),zlib.crc32(b))) for k in MODES+('D',)}
 st={k:dict(inner=0,matches=0,matchbytes=0,literalbytes=0,copies=0,score=[0]*4) for k in MODES}
 for i in range(0,len(b),B):
  block=b[i:i+B];pp=parses(block,w,exe,h14)
  for k in MODES:
   seq,tail,sc=pp[k];raw,_=h14.serialize(seq,tail,1);assert len(raw)<=2*len(block)+64
   decoded,stat=h14.decode_inner(raw,len(block),1);assert decoded==block
   st[k]['inner']+=len(raw)
   for key in ('matches','matchbytes','literalbytes','copies'):st[k][key]+=stat[key]
   st[k]['score']=[a+b for a,b in zip(st[k]['score'],sc)]
   comp=h14.zc(raw,3);frames[k].extend(struct.pack('<II',len(comp),len(raw)));frames[k].extend(comp)
  comp=h14.zc(block,3);frames['D'].extend(struct.pack('<II',len(comp),len(block)));frames['D'].extend(comp)
 sizes={};hashes={}
 for k,f in frames.items():
  r,stats=h14.frame_decode(f);assert r==b
  if k!='D':
   for key in ('matches','matchbytes','literalbytes','copies'):assert sum(x[key] for x in stats)==st[k][key]
  sizes[k]=len(f);hashes[k]=sha(f)
 for lev in (6,9):
  c=h14.zc(b,lev);assert h14.zd(c,len(b))==b;sizes['zstd'+str(lev)]=len(c);hashes['zstd'+str(lev)]=sha(c)
 c=lzma.compress(b,preset=5,check=lzma.CHECK_CRC64);assert lzma.decompress(c)==b;sizes['xz5']=len(c);hashes['xz5']=sha(c)
 return dict(sizes=sizes,archive_sha256=hashes,stats=st,checks=9)
def main():
 p=argparse.ArgumentParser();p.add_argument('--lab',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();root=a.lab.resolve()
 lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 assert shutil.disk_usage(root).free>=5*1024**3 and int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))>=1024**2
 resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,)*2);resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,)*2);h14=load(root);exe=root/'experiments/h15/parse';rows=[];summaries=[]
 with a.out.open('x') as f:
  def log(r):f.write(json.dumps(r,separators=(',',':'))+'\n');f.flush()
  log(dict(type='meta',protocol='H15-H17',script_sha256=sha(pathlib.Path(__file__).read_bytes()),exe_sha256=sha(exe.read_bytes()),zstd_version=h14.lib.ZSTD_versionNumber(),zstd_library_sha256=sha(pathlib.Path('/lib/x86_64-linux-gnu/libzstd.so.1').read_bytes()),affinity=sorted(os.sched_getaffinity(0))))
  for g,n,b,src in sources(root):
   with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h15-') as td:r=measure(b,pathlib.Path(td),exe,h14)
   r.update(type='sample',group=g,name=n,input_bytes=len(b),sha256_input=sha(b),**src);rows.append(r);log(r);print(g,n,r['sizes'],flush=True)
  for g in ('silesia','local','synthetic','real'):
   rr=[r for r in rows if r['group']==g or g=='real' and r['group']!='synthetic'];sizes={k:sum(r['sizes'][k] for r in rr) for k in ALL}
   direct=sum(min(r['sizes']['zstd6'],r['sizes']['zstd9']) for r in rr);wins={k:sum(r['sizes'][k]<min(r['sizes']['zstd6'],r['sizes']['zstd9']) for r in rr) for k in MODES}
   st={k:{key:sum(r['stats'][k][key] for r in rr) for key in ('inner','matches','matchbytes','literalbytes','copies')} for k in MODES}
   for k in MODES:st[k]['score']=[sum(r['stats'][k]['score'][i] for r in rr) for i in range(4)]
   q=dict(type='summary',group=g,files=len(rr),input_bytes=sum(r['input_bytes'] for r in rr),sizes=sizes,direct_oracle=direct,wins=wins,stats=st,checks=sum(r['checks'] for r in rr));summaries.append(q);log(q);print(json.dumps(q),flush=True)
  p=summaries[:2];r=summaries[-1];assert [q['files'] for q in p]==[6,6] and len(rows)==19
  h15=all(q['sizes']['F']<=.95*q['sizes']['G'] and q['sizes']['F']<=.95*q['direct_oracle'] for q in p) and r['wins']['F']>=6
  h16=all(q['sizes']['E']<=.97*q['sizes']['F'] and q['sizes']['E']<=.95*q['direct_oracle'] for q in p) and r['wins']['E']>=6
  proxy=all(q['sizes']['W8']<=1.01*q['sizes']['E'] and q['stats']['W8']['copies']<=.75*q['stats']['E']['copies'] and q['stats']['W8']['literalbytes']<=1.10*q['stats']['E']['literalbytes'] for q in p)
  h17=proxy and all(q['sizes']['W8']<=.95*q['direct_oracle'] for q in p)
  log(dict(type='gate',h15=h15,h16=h16,h17_proxy=proxy,h17=h17,checks=sum(r['checks'] for r in rows)))
if __name__=='__main__':main()
