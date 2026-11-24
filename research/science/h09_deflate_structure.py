#!/usr/bin/env python3
"""H09: exact structural DEFLATE representation, trusted bounded inputs."""
import argparse,ast,fcntl,hashlib,io,json,lzma,os,pathlib,re,shutil,struct,subprocess,tempfile,time,zipfile,zlib
p=argparse.ArgumentParser();p.add_argument('--lab',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();root=a.lab.resolve()
os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);assert shutil.disk_usage(root).free>=5*1024**3
def sha(b):return hashlib.sha256(b).hexdigest()
def xz(b):return lzma.compress(b,preset=5,check=lzma.CHECK_CRC64)
# Reuse the exact previously measured detector, without executing its benchmark.
dep=root/'experiments/h07b2/h07b2_precompression.py';assert sha(dep.read_bytes())=='cb984396ad8b5a118260f5e13d50e34d1eb8dab099a8b9c254cb2fc3fcdc0fc6'
tree=ast.parse(dep.read_text());MAX=2*1024**2
for node in tree.body:
 if isinstance(node,ast.FunctionDef) and node.name in ('inflate','wrap','spans'):
  exec(compile(ast.Module(body=[node],type_ignores=[]),str(dep),'exec'))
class R:
 def __init__(self,b):self.b=b;self.p=0
 def get(self,n):
  assert self.p+n<=8*len(self.b)
  i=self.p//8;s=self.p%8;k=(s+n+7)//8;self.p+=n
  return (int.from_bytes(self.b[i:i+k],'little')>>s)&((1<<n)-1)
class W:
 def __init__(self):self.b=bytearray();self.acc=0;self.n=0;self.p=0
 def put(self,x,n):
  assert 0<=x<1<<n
  self.acc|=x<<self.n;self.n+=n;self.p+=n
  while self.n>=8:self.b.append(self.acc&255);self.acc>>=8;self.n-=8
 def finish(self):
  assert self.n==0;return bytes(self.b)
def slice_bits(b,start,n):
 r=R(b);r.p=start;w=W()
 while n:
  k=min(n,8);w.put(r.get(k),k);n-=k
 if w.n:w.put(0,8-w.n)
 return w.finish()
def copy_bits(w,b,n):
 r=R(b)
 while n:
  k=min(n,8);w.put(r.get(k),k);n-=k
class Huff:
 def __init__(self,lens):
  self.d={};self.e={};counts=[0]*16
  for k in lens:
   assert 0<=k<=15
   if k:counts[k]+=1
  code=0;nexts=[0]*16
  for k in range(1,16):code=(code+counts[k-1])<<1;nexts[k]=code;assert code+counts[k]<=1<<k
  for s,k in enumerate(lens):
   if k:
    v=nexts[k];nexts[k]+=1;self.d[k,v]=s
    rev=int(f'{v:0{k}b}'[::-1],2);self.e[s]=(rev,k)
 def read(self,r):
  x=0
  for k in range(1,16):
   x=2*x+r.get(1)
   if (k,x) in self.d:return self.d[k,x]
  raise ValueError('invalid huffman')
 def write(self,w,s):v,k=self.e[s];w.put(v,k)
LB=[3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258]
LE=[0]*8+[1]*4+[2]*4+[3]*4+[4]*4+[5]*4+[0]
DB=[1,2,3,4];DE=[0]*4
for i in range(4,30):
 k=i//2-1;DE.append(k);DB.append(((2+(i%2))<<k)+1)
FIX=(Huff([8]*144+[9]*112+[7]*24+[8]*8),Huff([5]*32))
def header(r,offset=0):
 final=r.get(1);kind=r.get(2)
 if kind==0:
  r.get((-(r.p+offset))%8);n=r.get(16);assert r.get(16)==(n^65535);return final,kind,n,None,None
 if kind==1:return final,kind,None,*FIX
 assert kind==2
 nl=r.get(5)+257;nd=r.get(5)+1;nc=r.get(4)+4
 order=[16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15];lens=[0]*19
 for i in range(nc):lens[order[i]]=r.get(3)
 h=Huff(lens);out=[]
 while len(out)<nl+nd:
  k=h.read(r)
  if k<16:out.append(k)
  elif k==16:assert out;out.extend([out[-1]]*(r.get(2)+3))
  elif k==17:out.extend([0]*(r.get(3)+3))
  else:out.extend([0]*(r.get(7)+11))
 assert len(out)==nl+nd
 return final,kind,None,Huff(out[:nl]),Huff(out[nl:])
def match_values(ls,le,ds,de):
 assert ls<29 and ds<30 and le<1<<LE[ls] and de<1<<DE[ds]
 return LB[ls]+le,DB[ds]+de
def append_match(out,l,d):
 assert 0<d<=len(out) and len(out)+l<=262144
 base=out[-d:];out.extend((base*((l+d-1)//d))[:l])
def parse(raw,plain):
 r=R(raw);out=bytearray();heads=bytearray();matches=bytearray();lits=bytearray();blocks=0;hist=[0,0,0];count=0
 while True:
  start=r.p;final,kind,n,h,d=header(r);bits=r.p-start;hb=slice_bits(raw,start,bits);startout=len(out);num=0;run=0;hist[kind]+=1
  if kind==0:
   assert r.p%8==0;v=raw[r.p//8:r.p//8+n];assert len(v)==n;r.p+=n*8;out.extend(v);lits.extend(v)
  else:
   while True:
    s=h.read(r)
    if s<256:out.append(s);lits.append(s);run+=1
    elif s==256:break
    else:
     ls=s-257;assert ls<29;le=r.get(LE[ls]);ds=d.read(r);assert ds<30;de=r.get(DE[ds]);l,dist=match_values(ls,le,ds,de)
     append_match(out,l,dist);matches.extend(struct.pack('<IBBBH',run,ls,le,ds,de));run=0;num+=1
    assert len(out)<=262144
  heads.extend(struct.pack('<III',bits,len(out)-startout,num));heads.extend(hb);blocks+=1;count+=num
  assert blocks<=65536 and len(out)<=262144
  if final:break
 pad=(-r.p)%8;tail=r.get(pad);assert r.p==8*len(raw) and bytes(out)==plain
 heads.extend(struct.pack('<BB',pad,tail))
 return bytes(heads),bytes(matches),bytes(lits),dict(blocks=blocks,kinds=hist,matches=count)
def serialize(h,m,d,mode):
 return struct.pack('<BIII',mode,len(h),len(m),len(d))+h+m+d
def reconstruct(b):
 mode,nh,nm,nd=struct.unpack_from('<BIII',b);assert mode in (0,1) and len(b)==13+nh+nm+nd
 heads=b[13:13+nh];matches=b[13+nh:13+nh+nm];data=b[13+nh+nm:]
 hp=mp=dp=0;w=W();out=bytearray()
 def literal(n,h=None):
  nonlocal dp
  v=data[dp:dp+n];assert len(v)==n;dp+=n
  for x in v:
   if h is None:w.put(x,8)
   else:h.write(w,x)
  out.extend(v)
 while True:
  bits,n,nm=struct.unpack_from('<III',heads,hp);hp+=12;k=(bits+7)//8;hb=heads[hp:hp+k];hp+=k
  r=R(hb);final,kind,stored,h,d=header(r,w.p%8);assert r.p==bits;copy_bits(w,hb,bits);start=len(out)
  if kind==0:assert nm==0 and stored==n;literal(n)
  else:
   for _ in range(nm):
    run,ls,le,ds,de=struct.unpack_from('<IBBBH',matches,mp);mp+=9
    literal(run,h);l,dist=match_values(ls,le,ds,de);h.write(w,ls+257);w.put(le,LE[ls]);d.write(w,ds);w.put(de,DE[ds]);append_match(out,l,dist)
    if mode:assert data[dp:dp+l]==out[-l:];dp+=l
   assert len(out)-start<=n;literal(n-(len(out)-start),h);h.write(w,256)
  assert len(out)-start==n
  if final:break
 pad,tail=struct.unpack_from('<BB',heads,hp);hp+=2;assert pad==(-w.p)%8;w.put(tail,pad)
 assert hp==len(heads) and mp==len(matches) and dp==len(data)
 return w.finish(),bytes(out)
def raw_record(b):return struct.pack('<BI',0,len(b))+b
def structural(c,plain,mode,lengths):
 raw=c[2:-4] if mode==15 else c
 h,m,l,stats=parse(raw,plain)
 assert zlib.decompress(raw,-15)==plain
 outs=[];components={}
 for k,d in enumerate((l,plain)):
  s=serialize(h,m,d,k);r,p=reconstruct(s);assert r==raw and p==plain
  wrapper=c[:2]+c[-4:] if mode==15 else b''
  body=struct.pack('<BI',int(mode==15),len(lengths))+wrapper+b''.join(struct.pack('<I',v) for v in lengths)+s
  rec=struct.pack('<BI',1,len(body))+body
  assert unwrap(body)==wrap(c,lengths)
  outs.append(rec)
  components['LP'[k]]=dict(header_xz=len(xz(h)),matches_xz=len(xz(m)),data_xz=len(xz(d)),local_xz=len(xz(rec)),raw_record_xz=len(xz(raw_record(wrap(c,lengths)))))
 return outs,stats,components
def unwrap(b):
 z,n=struct.unpack_from('<BI',b);i=5;wrapper=b[i:i+6] if z else b'';i+=6 if z else 0
 lengths=list(struct.unpack_from('<'+'I'*n,b,i));i+=4*n
 raw,_=reconstruct(b[i:]);c=wrapper[:2]+raw+wrapper[2:] if z else raw
 return wrap(c,lengths)
def decode(frame):
 magic,n,crc=struct.unpack_from('<4sII',frame);assert magic==b'H09A';b=lzma.decompress(frame[12:]);out=bytearray();i=0
 while i<len(b):
  tag,k=struct.unpack_from('<BI',b,i);i+=5;v=b[i:i+k];i+=k;assert len(v)==k
  out.extend(v if tag==0 else unwrap(v));assert len(out)<=n
 assert i==len(b) and len(out)==n and zlib.crc32(out)==crc
 return bytes(out)
def measure(b,g):
 streams=spans(b,g);total=0;chosen=[0,0];out=[bytearray(),bytearray()];pos=0;stats=[]
 for s,e,c,p,mode,lens in streams:
  if len(c)>131072 or len(p)>262144 or total+len(p)>1048576:continue
  assert wrap(c,lens)==b[s:e];total+=len(p)
  rec,st,comp=structural(c,p,mode,lens);raw=raw_record(b[s:e]);rb=len(xz(raw))
  for k in range(2):
   if s>pos:out[k].extend(raw_record(b[pos:s]))
   use=len(xz(rec[k]))<rb;chosen[k]+=use;out[k].extend(rec[k] if use else raw)
  stats.append(dict(offset=s,compressed=len(c),plain=len(p),**st,components=comp));pos=e
 result={}
 for k in range(2):
  if pos<len(b):out[k].extend(raw_record(b[pos:]))
  f=struct.pack('<4sII',b'H09A',len(b),zlib.crc32(b))+xz(out[k]);assert decode(f)==b
  result['LP'[k]]=dict(bytes=len(f),selected=chosen[k],sha256=sha(f))
 return result,stats,len(streams)
def fetch(url):
 with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h09-') as td:
  p=pathlib.Path(td)/'source';subprocess.run(['curl','-fLsS','--proto','=https','--max-time','20','--max-filesize','750000','-o',str(p),url],check=True,timeout=25,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  return p.read_bytes()
a.out.parent.mkdir(parents=True,exist_ok=True);rows=[]
with a.out.open('x') as f:
 def log(r):f.write(json.dumps(r)+'\n');f.flush()
 old=root/'results/h07b2-20261124.jsonl';assert sha(old.read_bytes())=='618421bf6b20e323e826b42eb78a4921463f9f215733532939aded677a2db963'
 log(dict(type='meta',protocol='H09',script_sha256=sha(pathlib.Path(__file__).read_bytes()),old_sha256=sha(old.read_bytes()),zlib=zlib.ZLIB_RUNTIME_VERSION))
 manifest=json.loads((root/'corpora/manifest.json').read_text());synth=[]
 for item in manifest:
  if pathlib.Path(item['path']).name in ('alice29.txt','random.bin','repeat.bin'):
   b=(root/item['path']).read_bytes();assert sha(b)==item['sha256'];synth.append((pathlib.Path(item['path']).name,b[:32768]))
 synth.append(('generated-text',b'abc defgh repeated lines\n'*1200))
 for name,b in synth:
  for label,lev,strat,flush in [('stored',0,0,False),('default',6,0,False),('fixed',6,4,False),('sync',6,0,True)]:
   z=zlib.compressobj(lev,zlib.DEFLATED,-15,8,strat)
   c=z.compress(b[:len(b)//2])+(z.flush(zlib.Z_SYNC_FLUSH) if flush else b'')+z.compress(b[len(b)//2:])+z.flush()
   rec,st,comp=structural(c,b,-15,[]);log(dict(type='synthetic',name=name,variant=label,compressed=len(c),plain=len(b),**st,components=comp,checks=2))
 print('SYNTHETIC',len(synth)*4,flush=True)
 for x in map(json.loads,old.read_text().splitlines()):
  if x['type']!='sample':continue
  try:b=fetch(x['url']);assert sha(b)==x['sha256']
  except (OSError,AssertionError,subprocess.SubprocessError) as e:log(dict(type='skip',name=x['name'],error=repr(e)));continue
  t=time.perf_counter();result,stats,found=measure(b,x['group']);base=min(x['candidates'][k]['bytes'] for k in ('xz5','zstd15','7z','precomp-xz5'));ordinary=min(x['candidates'][k]['bytes'] for k in ('xz5','zstd15','7z'))
  r=dict(type='sample',name=x['name'],group=x['group'],url=x['url'],sha256=sha(b),input_bytes=len(b),ordinary=ordinary,strong=base,candidates=result,detected=found,streams=stats,checks=2+2*len(stats),wall_s=time.perf_counter()-t)
  rows.append(r);log(r);print(r['group'],r['name'],base,result['L']['bytes'],result['P']['bytes'],len(stats),found,flush=True)
 for g in ('pdf','docx','xlsx','zip','png','all'):
  rr=[r for r in rows if g=='all' or r['group']==g];strong=sum(r['strong'] for r in rr);ordinary=sum(r['ordinary'] for r in rr);tot={k:sum(r['candidates'][k]['bytes'] for r in rr) for k in 'LP'}
  r=dict(type='summary',group=g,samples=len(rr),strong=strong,ordinary=ordinary,sizes=tot,oracle=sum(min(r['ordinary'],r['candidates']['L']['bytes'],r['candidates']['P']['bytes']) for r in rr),wins=sum(r['candidates']['P']['bytes']<r['strong'] for r in rr),checks=sum(r['checks'] for r in rr),detected=sum(r['detected'] for r in rr),analyzed=sum(len(r['streams']) for r in rr),selected={k:sum(r['candidates'][k]['selected'] for r in rr) for k in 'LP'})
  if g=='all':r['gate']=len(rr)==15 and tot['P']<=.95*strong and r['wins']>=8
  log(r);print(json.dumps(r),flush=True)
