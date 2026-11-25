#!/usr/bin/env python3
"""H14: bounded LZ command serialization, trusted lab inputs only."""
import argparse,collections,ctypes as C,fcntl,hashlib,json,lzma,os,pathlib,resource,shutil,struct,zlib
B=262144
def sha(b):return hashlib.sha256(b).hexdigest()
lib=C.CDLL('libzstd.so.1');P=C.c_void_p;S=C.c_size_t
for name,args,ret in [('ZSTD_compressBound',[S],S),('ZSTD_compress',[P,S,P,S,C.c_int],S),('ZSTD_decompress',[P,S,P,S],S),('ZSTD_isError',[S],C.c_uint),('ZSTD_versionNumber',[],C.c_uint)]:
 f=getattr(lib,name);f.argtypes=args;f.restype=ret
def zc(b,level):
 cap=lib.ZSTD_compressBound(len(b));out=C.create_string_buffer(cap);n=lib.ZSTD_compress(out,cap,b,len(b),level);assert not lib.ZSTD_isError(n);return out.raw[:n]
def zd(b,n):
 out=C.create_string_buffer(n);k=lib.ZSTD_decompress(out,n,b,len(b));assert not lib.ZSTD_isError(k) and k==n;return out.raw
def v(n):
 b=bytearray()
 while n>=128:b.append((n&127)|128);n>>=7
 b.append(n);return b
def readv(b,i):
 x=0;s=0
 while True:
  k=b[i];i+=1;x|=(k&127)<<s
  if k<128:return x,i
  s+=7;assert s<=21
def parse(b):
 n=len(b);p=start=0;table={};seq=[]
 def insert(j):
  if j+4<=n:
   key=b[j:j+4];a=table.get(key)
   if a is None:table[key]=[j]
   else:
    a.append(j)
    if len(a)>4:del a[0]
 while p+4<=n:
  best=dist=0;cap=min(258,n-p)
  for q in reversed(table.get(b[p:p+4],())):
   d=p-q
   if d>65535:break
   lo=4;hi=cap
   while lo<hi:
    m=(lo+hi+1)//2
    if b[q:q+m]==b[p:p+m]:lo=m
    else:hi=m-1
   if lo>best:best=lo;dist=d
   if best==cap:break
  if best>=4:
   seq.append((b[start:p],best,dist))
   for j in range(p,p+best):insert(j)
   p+=best;start=p
  else:insert(p);p+=1
 return seq,b[start:]
def mtf(cache,d):
 if d in cache:cache.remove(d)
 cache.insert(0,d)
 if len(cache)>4:cache.pop()
def serialize(seq,tail,mode):
 out=bytearray(struct.pack('<I',len(seq)));runs=bytearray();lens=bytearray();dist=bytearray();lits=bytearray();esc=bytearray();cache=[]
 for lit,l,d in seq:
  if mode==0:out.extend(v(len(lit)));out.extend(lit);out.extend(struct.pack('<BH',l-4,d))
  else:
   runs.extend(v(len(lit)));lens.append(l-4);lits.extend(lit)
   if mode==1:dist.extend(struct.pack('<H',d))
   else:
    k=cache.index(d) if d in cache else 4;dist.append(k)
    if k==4:esc.extend(struct.pack('<H',d))
    mtf(cache,d)
 if mode==0:out.extend(v(len(tail)));out.extend(tail);return bytes(out),[]
 runs.extend(v(len(tail)));lits.extend(tail)
 lanes=[runs,lens,dist,lits] if mode==1 else [runs,lens,dist,esc,lits]
 sizes=list(map(len,lanes));out.extend(struct.pack('<'+'I'*len(lanes),*sizes))
 for a in lanes:out.extend(a)
 return bytes(out),sizes
def decode_inner(b,n,mode):
 m=struct.unpack_from('<I',b)[0];assert m<=n//4
 out=bytearray();pos=4;rp=lp=ep=dp=0;cache=[];copies=matchbytes=maxdist=0
 if mode:
  k=4 if mode==1 else 5;sizes=struct.unpack_from('<'+'I'*k,b,pos);pos+=4*k;lanes=[]
  for s in sizes:lanes.append(b[pos:pos+s]);pos+=s
  assert pos==len(b) and list(map(len,lanes))==list(sizes)
  runs,lens,ds=lanes[:3];lits=lanes[-1];esc=lanes[3] if mode==2 else b''
  assert len(lens)==m and len(ds)==m*(2 if mode==1 else 1)
 for j in range(m+1):
  if mode:
   r,rp=readv(runs,rp);assert lp+r<=len(lits);lit=lits[lp:lp+r];lp+=r
  else:r,pos=readv(b,pos);assert pos+r<=len(b);lit=b[pos:pos+r];pos+=r
  assert len(out)+r<=n;out.extend(lit)
  if j==m:break
  if mode==0:
   l,d=struct.unpack_from('<BH',b,pos);pos+=3;l+=4
  else:
   l=lens[j]+4
   if mode==1:d=struct.unpack_from('<H',ds,2*j)[0]
   else:
    k=ds[j]
    if k==4:d=struct.unpack_from('<H',esc,ep)[0];ep+=2
    else:assert k<len(cache);d=cache[k]
    mtf(cache,d)
  assert 4<=l<=258 and 0<d<=min(len(out),65535) and len(out)+l<=n
  base=len(out)-d;left=l;available=d
  while left:
   k=min(left,available);out.extend(out[base:base+k]);left-=k;available+=k;copies+=1
  matchbytes+=l;maxdist=max(maxdist,d)
 assert len(out)==n
 if mode:assert rp==len(runs) and lp==len(lits) and (mode!=2 or ep==len(esc))
 else:assert pos==len(b)
 return bytes(out),dict(matches=m,matchbytes=matchbytes,literalbytes=n-matchbytes,copies=copies,maxdist=maxdist,runs=m+1)
def frame_decode(b):
 magic,mode,n,crc=struct.unpack_from('<4sBII',b);assert magic==b'H14A' and mode<=3;pos=13;out=bytearray();stats=[]
 while len(out)<n:
  k,s=struct.unpack_from('<II',b,pos);pos+=8;assert pos+k<=len(b)
  m=min(B,n-len(out));assert s<=2*m+64
  raw=zd(b[pos:pos+k],s);pos+=k
  if mode==3:assert len(raw)==m;out.extend(raw)
  else:x,st=decode_inner(raw,m,mode);out.extend(x);stats.append(st)
 assert pos==len(b) and len(out)==n and zlib.crc32(out)==crc
 return bytes(out),stats
def measure(b):
 frames=[bytearray(struct.pack('<4sBII',b'H14A',i,len(b),zlib.crc32(b))) for i in range(4)];rawsizes=[0]*4;max_inner=[0]*4;lanes=[[],[],[],[]];expected=[]
 for i in range(0,len(b),B):
  block=b[i:i+B];seq,tail=parse(block)
  st=dict(matches=len(seq),matchbytes=sum(x[1] for x in seq),literalbytes=len(tail)+sum(len(x[0]) for x in seq),copies=0,maxdist=max((x[2] for x in seq),default=0),runs=len(seq)+1)
  for _,l,d in seq:
   while l:k=min(l,d);l-=k;d+=k;st['copies']+=1
  expected.append(st)
  for mode in range(4):
   raw,ls=serialize(seq,tail,mode) if mode<3 else (block,[])
   assert len(raw)<=2*len(block)+64
   c=zc(raw,3);frames[mode].extend(struct.pack('<II',len(c),len(raw)));frames[mode].extend(c);rawsizes[mode]+=len(raw);max_inner[mode]=max(max_inner[mode],len(raw))
   if ls:
    if not lanes[mode]:lanes[mode]=[0]*len(ls)
    lanes[mode]=[x+y for x,y in zip(lanes[mode],ls)]
 sizes={};hashes={}
 for i,frame in enumerate(frames):
  r,stats=frame_decode(frame);assert r==b and (i==3 or stats==expected)
  k='ABCD'[i];sizes[k]=len(frame);hashes[k]=sha(frame)
 for lev in (6,9):
  c=zc(b,lev);assert zd(c,len(b))==b;sizes['zstd'+str(lev)]=len(c);hashes['zstd'+str(lev)]=sha(c)
 c=lzma.compress(b,preset=5,check=lzma.CHECK_CRC64);assert lzma.decompress(c)==b;sizes['xz5']=len(c);hashes['xz5']=sha(c)
 stats={k:sum(s[k] for s in expected) for k in ('matches','matchbytes','literalbytes','copies','runs')};stats['maxdist']=max((s['maxdist'] for s in expected),default=0)
 assert stats['matchbytes']+stats['literalbytes']==len(b)
 return dict(sizes=sizes,archive_sha256=hashes,inner_sizes=rawsizes,max_inner=max_inner,lanes=lanes,work=stats,blocks=len(expected),checks=7)
def sources(root):
 m=json.loads((root/'corpora/manifest.json').read_text())
 for name in ('dickens','mr','ooffice','samba','x-ray','xml'):
  x=next(v for v in m if v['group']=='silesia' and pathlib.Path(v['path']).name==name);b=(root/x['path']).read_bytes();assert sha(b)==x['sha256'];off=(len(b)-524288)*2//5
  yield 'silesia',name,b[off:off+524288],dict(path=x['path'],full_sha256=x['sha256'],offset=off)
 for path in ('/usr/bin/ffmpeg','/usr/bin/curl','/usr/lib/x86_64-linux-gnu/libxml2.so.2','/usr/lib/x86_64-linux-gnu/libpcre2-8.so.0','/usr/lib/python3.12/pydoc.py','/usr/lib/python3.12/inspect.py'):
  b=pathlib.Path(path).read_bytes();yield 'local',pathlib.Path(path).name,b[:524288],dict(path=path,full_sha256=sha(b),offset=0)
 for x in m:
  if x['group']=='synthetic':
   b=(root/x['path']).read_bytes();assert sha(b)==x['sha256'];yield 'synthetic',pathlib.Path(x['path']).name,b,dict(path=x['path'],full_sha256=x['sha256'],offset=0)
def main():
 p=argparse.ArgumentParser();p.add_argument('--lab',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();root=a.lab.resolve()
 lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 assert shutil.disk_usage(root).free>=5*1024**3 and int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))>=1024**2
 resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,)*2);resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,)*2)
 rows=[];summaries=[]
 with a.out.open('x') as f:
  def log(r):f.write(json.dumps(r,separators=(',',':'))+'\n');f.flush()
  log(dict(type='meta',protocol='H14',script_sha256=sha(pathlib.Path(__file__).read_bytes()),zstd_version=lib.ZSTD_versionNumber(),zstd_library_sha256=sha(pathlib.Path('/lib/x86_64-linux-gnu/libzstd.so.1').read_bytes()),affinity=sorted(os.sched_getaffinity(0))))
  for g,n,b,src in sources(root):
   r=measure(b);r.update(type='sample',group=g,name=n,input_bytes=len(b),sha256_input=sha(b),**src);rows.append(r);log(r);print(g,n,r['sizes'],r['work'],flush=True)
  for g in ('silesia','local','synthetic','real'):
   rr=[r for r in rows if r['group']==g or g=='real' and r['group']!='synthetic'];n=sum(r['input_bytes'] for r in rr);sizes={k:sum(r['sizes'][k] for r in rr) for k in rr[0]['sizes']}
   direct=sum(min(r['sizes']['zstd6'],r['sizes']['zstd9']) for r in rr);wins=sum(r['sizes']['C']<min(r['sizes']['zstd6'],r['sizes']['zstd9']) for r in rr)
   work={k:sum(r['work'][k] for r in rr) for k in ('matches','matchbytes','literalbytes','copies','runs')};work['maxdist']=max(r['work']['maxdist'] for r in rr)
   q=dict(type='summary',group=g,files=len(rr),input_bytes=n,sizes=sizes,direct_oracle=direct,wins=wins,work=work,max_inner=[max(r['max_inner'][i] for r in rr) for i in range(4)],inner_sizes=[sum(r['inner_sizes'][i] for r in rr) for i in range(4)],checks=sum(r['checks'] for r in rr));summaries.append(q);log(q);print(json.dumps(q),flush=True)
  gate=all(q['files']==6 and q['sizes']['C']<=.95*q['sizes']['A'] and q['sizes']['C']<=.95*q['direct_oracle'] and q['work']['copies']<=q['input_bytes']/4 for q in summaries[:2]) and summaries[-1]['wins']>=6
  log(dict(type='gate',pass_gate=gate,checks=sum(r['checks'] for r in rows),files=len(rows)))
if __name__=='__main__':main()
