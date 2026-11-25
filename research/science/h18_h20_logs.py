#!/usr/bin/env python3
"""H18-H20: byte-exact structural log models; trusted bounded corpus."""
import argparse,collections,ctypes as C,fcntl,hashlib,json,lzma,math,os,pathlib,re,resource,shutil,struct,subprocess,tempfile,zlib
REV='dd61d0952749ee7963bde24220d1be5ede023033'
PANELS={'dev':('HDFS','BGL','Linux','Apache','Spark','OpenSSH'),'confirmation':('Hadoop','OpenStack','Thunderbird','Windows','Android','Zookeeper')}
MAX=2*1024*1024
def sha(b):return hashlib.sha256(b).hexdigest()
def v(n):
 assert n>=0
 out=bytearray()
 while n>=128:out.append((n&127)|128);n>>=7
 out.append(n);return bytes(out)
def pack(b):return v(len(b))+b
class Reader:
 def __init__(self,b):self.b=b;self.i=0
 def take(self,n):
  assert 0<=n<=len(self.b)-self.i
  p=self.i;self.i+=n;return self.b[p:self.i]
 def var(self):
  x=0
  for k in range(10):
   b=self.take(1)[0];x|=(b&127)<<(7*k)
   if b<128:return x
  raise ValueError('varint overflow')
 def blob(self):return self.take(self.var())
 def end(self):assert self.i==len(self.b)
def h0(items):
 c=collections.Counter(items);n=sum(c.values());return sum(k*math.log2(n/k) for k in c.values()) if n else 0.
TOK=re.compile(rb'[A-Za-z_]+|[0-9]+|[^A-Za-z_0-9]+')
DIG=re.compile(rb'[0-9]+')
CAN=re.compile(rb'(?:0|[1-9][0-9]{0,18})\Z')
def group_rows(data,mode):
 rows=data.splitlines(keepends=True);assert b''.join(rows)==data
 groups=[];keys={};order=[]
 for line in rows:
  if mode==1:
   fields=re.split(rb'([0-9]+)',line);key=tuple(fields[::2])
  else:
   fields=TOK.findall(line);assert b''.join(fields)==line
   types=tuple(0 if (65<=x[0]<=90 or 97<=x[0]<=122 or x[0]==95) else 1 if 48<=x[0]<=57 else 2 for x in fields)
   anchors=tuple(x for x,t in zip(fields,types) if t==0)[:2];key=(types,anchors)
  k=keys.get(key)
  if k is None:k=len(groups);keys[key]=k;groups.append([])
  groups[k].append(fields);order.append(k)
 return groups,order
def delta(values):
 if not all(CAN.fullmatch(x) for x in values):return None
 nums=list(map(int,values))
 if any(x>2**63-1 for x in nums):return None
 out=bytearray(v(nums[0]));prev=nums[0]
 for n in nums[1:]:
  d=n-prev;out.extend(v(2*d if d>=0 else -2*d-1));prev=n
 return bytes(out)
def encode(data,mode):
 groups,order=group_rows(data,mode);out=bytearray(v(len(order))+v(len(groups)))
 meta=len(out);constant_bytes=raw_bytes=lanes_bytes=constant_fields=variable_fields=delta_fields=0;field_entropy=0.
 for rows in groups:
  cols=list(zip(*rows));assert all(len(x)==len(cols) for x in rows)
  p=v(len(rows))+v(len(cols));out.extend(p);meta+=len(p)
  for j,col in enumerate(cols):
   fixed=(j%2==0) if mode==1 else all(x==col[0] for x in col)
   if fixed:
    assert all(x==col[0] for x in col);p=bytes([0])+pack(col[0]);out.extend(p);meta+=len(p);constant_bytes+=len(col[0]);constant_fields+=1
   else:
    variable_fields+=1;field_entropy+=h0(col);raw=b''.join(pack(x) for x in col);raw_bytes+=len(raw)
    d=delta(col) if mode==3 else None
    use=d is not None and len(d)<len(raw);lane=d if use else raw
    if use:delta_fields+=1
    p=bytes([2 if use else 1])+v(len(lane));out.extend(p);out.extend(lane);meta+=len(p);lanes_bytes+=len(lane)
 seq=b''.join(map(v,order));out.extend(seq)
 assert meta+lanes_bytes+len(seq)==len(out)
 return bytes(out),dict(rows=len(order),groups=len(groups),model_bytes=meta,constant_bytes=constant_bytes,raw_variable_bytes=raw_bytes,lane_bytes=lanes_bytes,order_bytes=len(seq),constant_fields=constant_fields,variable_fields=variable_fields,delta_fields=delta_fields,group_h0_bits=h0(order),variable_token_h0_bits=field_entropy,inner_bytes=len(out))
def decode(body):
 r=Reader(body);nr=r.var();ng=r.var();assert ng<=nr<=MAX;groups=[]
 for _ in range(ng):
  n=r.var();nf=r.var();assert 0<n<=nr and nf<=MAX;cols=[]
  for _ in range(nf):
   tag=r.take(1)[0];b=r.blob()
   if tag==0:col=[b]*n
   else:
    q=Reader(b)
    if tag==1:col=[q.blob() for _ in range(n)]
    elif tag==2:
     val=q.var();assert val<=2**63-1;col=[str(val).encode()]
     for i in range(n-1):
      z=q.var();val+=z//2 if z%2==0 else -(z//2)-1;assert 0<=val<=2**63-1;col.append(str(val).encode())
    else:raise ValueError('lane tag')
    q.end()
   cols.append(col)
  groups.append(collections.deque(b''.join(row) for row in zip(*cols)) if nf else collections.deque([b'']*n))
 out=bytearray()
 for _ in range(nr):
  k=r.var();assert k<ng;out.extend(groups[k].popleft());assert len(out)<=MAX
 assert not any(groups);r.end();return bytes(out)
def xz(b):return lzma.compress(b,preset=5,check=lzma.CHECK_CRC64)
def frame(data,mode,body):return struct.pack('<4sBII',b'H18A',mode,len(data),zlib.crc32(data))+xz(body)
def unframe(b):
 m,mode,n,crc=struct.unpack_from('<4sBII',b);assert m==b'H18A' and mode<4
 body=lzma.decompress(b[13:]);x=body if mode==0 else decode(body)
 assert len(x)==n and zlib.crc32(x)==crc;return x
def call(cmd,w):
 return subprocess.run(cmd,cwd=w,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45).stdout
def measure(b,w):
 (w/'input.bin').write_bytes(b);sizes={};hashes={};stats={}
 for mode,k in enumerate('ABCD'):
  body,st=(b,dict(inner_bytes=len(b))) if mode==0 else encode(b,mode)
  c=frame(b,mode,body);assert unframe(c)==b
  sizes[k]=len(c);hashes[k]=sha(c);stats[k]=st
 # C and D must have same structure and rows; only selected numeric lanes differ.
 for k in ('rows','groups','constant_bytes','raw_variable_bytes','order_bytes','constant_fields','variable_fields','group_h0_bits','variable_token_h0_bits'):assert stats['C'][k]==stats['D'][k]
 assert stats['D']['lane_bytes']<=stats['C']['lane_bytes']
 c=xz(b);assert lzma.decompress(c)==b;sizes['xz5']=len(c);hashes['xz5']=sha(c)
 c=call(['zstd','-q','-T1','-19','-c','input.bin'],w);(w/'control.zst').write_bytes(c);assert call(['zstd','-q','-d','-c','control.zst'],w)==b;sizes['zstd19']=len(c);hashes['zstd19']=sha(c)
 for k,method in [('ppmd5','PPMd'),('7z5','LZMA2')]:
  call(['7z','a','-t7z','-m0='+method,'-mx=5','-mmt=1','-mtc=off','-mta=off','-mtm=off',k+'.7z','input.bin'],w)
  c=(w/(k+'.7z')).read_bytes();assert call(['7z','x','-so','-mmt=1',k+'.7z'],w)==b;sizes[k]=len(c);hashes[k]=sha(c)
 assert sizes['A']==sizes['xz5']+13
 return dict(sizes=sizes,archive_sha256=hashes,stats=stats,checks=8)
def main():
 p=argparse.ArgumentParser();p.add_argument('--lab',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();root=a.lab.resolve()
 lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 assert shutil.disk_usage(root).free>=5*1024**3 and int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))>=1024**2
 resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,)*2);resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,)*2)
 rows=[];summaries=[];controls=('xz5','zstd19','ppmd5','7z5')
 with a.out.open('x') as f:
  def log(r):f.write(json.dumps(r,separators=(',',':'))+'\n');f.flush()
  log(dict(type='meta',protocol='H18-H20',revision=REV,script_sha256=sha(pathlib.Path(__file__).read_bytes()),affinity=sorted(os.sched_getaffinity(0)),zstd_version=call(['zstd','--version'],root).decode(),xz_version=call(['xz','--version'],root).decode(),sevenzip_version=call(['7z','i'],root).decode().splitlines()[:4]))
  for g,names in PANELS.items():
   for name in names:
    url=f'https://raw.githubusercontent.com/logpai/loghub/{REV}/{name}/{name}_2k.log'
    with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h18-') as td:
     w=pathlib.Path(td)
     try:call(['curl','-fLsS','--proto','=https','--max-time','20','--max-filesize',str(MAX),'-o','source',url],w);b=(w/'source').read_bytes();assert 0<len(b)<=MAX
     except (OSError,subprocess.SubprocessError,AssertionError) as e:log(dict(type='skip',group=g,name=name,url=url,error=repr(e)));print('SKIP',name,repr(e),flush=True);continue
     r=measure(b,w)
    r.update(type='sample',group=g,name=name,url=url,sha256_input=sha(b),input_bytes=len(b),lines=len(b.splitlines(keepends=True)));rows.append(r);log(r);print(g,name,r['sizes'],flush=True)
  for g in PANELS:
   rr=[r for r in rows if r['group']==g];keys='ABCD'
   sizes={k:sum(r['sizes'][k] for r in rr) for k in (*keys,*controls)}
   direct=sum(min(r['sizes'][k] for k in controls) for r in rr);wins={k:sum(r['sizes'][k]<min(r['sizes'][j] for j in controls) for r in rr) for k in keys}
   oracle=sum(min(r['sizes'][k] for k in keys) for r in rr)
   st={k:{j:sum(r['stats'][k][j] for r in rr) for j in ('rows','groups','model_bytes','constant_bytes','raw_variable_bytes','lane_bytes','order_bytes','constant_fields','variable_fields','delta_fields','group_h0_bits','variable_token_h0_bits','inner_bytes')} for k in 'BCD'}
   q=dict(type='summary',group=g,files=len(rr),input_bytes=sum(r['input_bytes'] for r in rr),sizes=sizes,direct_oracle=direct,framed_oracle=oracle,wins=wins,stats=st,checks=sum(r['checks'] for r in rr));summaries.append(q);log(q);print(json.dumps(q),flush=True)
  d,h=summaries
  def cgate(q):return q['files']==6 and q['sizes']['C']<=.95*q['direct_oracle'] and q['sizes']['C']<=.95*q['sizes']['B'] and q['wins']['C']>=4
  def dgate(q):return q['files']==6 and q['sizes']['D']<=.95*q['direct_oracle'] and q['sizes']['D']<=.97*q['sizes']['C'] and q['wins']['D']>=4
  gate=dict(type='gate',complete=len(rows)==12,h18=cgate(d),h19=dgate(d),h20_D=dgate(d) and dgate(h),h20_C=cgate(d) and cgate(h),confirmation_C=cgate(h),confirmation_D=dgate(h),checks=sum(r['checks'] for r in rows));log(gate);print(json.dumps(gate),flush=True)
if __name__=='__main__':main()
