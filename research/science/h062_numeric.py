#!/usr/bin/env python3
"""H06.2 bounded predictive bitpacking and exact decimal exceptions."""
import argparse,ctypes as C,ctypes.util,fcntl,hashlib,io,json,lzma,os,pathlib,random,shutil,struct,subprocess,tempfile,time,wave,zlib
import numpy as np
P=argparse.ArgumentParser();P.add_argument('--lab',type=pathlib.Path,required=True);P.add_argument('--out',type=pathlib.Path,required=True);a=P.parse_args();root=a.lab.resolve()
os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);assert shutil.disk_usage(root).free>=5*1024**3
alp=root/'experiments/h062/alp-driver'
def sha(b):return hashlib.sha256(b).hexdigest()
assert sha(alp.read_bytes())=='a4067dba45033367d93f91fbed66d20f12680708bd5ddf016bfc0f91857800ee'
lib=C.CDLL(ctypes.util.find_library('zstd') or 'libzstd.so.1')
lib.ZSTD_compressBound.argtypes=[C.c_size_t];lib.ZSTD_compressBound.restype=C.c_size_t
lib.ZSTD_compress.argtypes=[C.c_void_p,C.c_size_t,C.c_char_p,C.c_size_t,C.c_int];lib.ZSTD_compress.restype=C.c_size_t
lib.ZSTD_decompress.argtypes=[C.c_void_p,C.c_size_t,C.c_char_p,C.c_size_t];lib.ZSTD_decompress.restype=C.c_size_t
lib.ZSTD_isError.argtypes=[C.c_size_t];lib.ZSTD_isError.restype=C.c_uint
lib.ZSTD_getFrameContentSize.argtypes=[C.c_char_p,C.c_size_t];lib.ZSTD_getFrameContentSize.restype=C.c_uint64
lib.ZSTD_versionString.restype=C.c_char_p
def enc(b,k):
 if k==0:return b
 if k==1:return lzma.compress(b,preset=5,check=lzma.CHECK_CRC64)
 cap=lib.ZSTD_compressBound(len(b));buf=C.create_string_buffer(cap);n=lib.ZSTD_compress(buf,cap,b,len(b),15)
 assert not lib.ZSTD_isError(n);return buf.raw[:n]
def dec(b,k):
 if k==0:return b
 if k==1:return lzma.decompress(b)
 n=lib.ZSTD_getFrameContentSize(b,len(b));assert n<=16*1024**2
 buf=C.create_string_buffer(n);m=lib.ZSTD_decompress(buf,n,b,len(b));assert m==n and not lib.ZSTD_isError(m);return buf.raw
def call(argv,cwd=None):
 return subprocess.run(argv,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=45).stdout
def fetch(url):
 with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h062-source-') as t:
  p=pathlib.Path(t)/'source';call(['curl','-fLsS','--proto','=https','--max-time','25','--max-filesize','3145728','-o',str(p),url])
  b=p.read_bytes();assert 0<len(b)<=3145728;return b
def residual(x,order):
 r=x.copy()
 for _ in range(order):r=np.diff(r,prepend=np.zeros(1,dtype=r.dtype))
 w=x.dtype.itemsize*8
 return (r<<1)^(np.zeros_like(r)-(r>>(w-1)))
def inv(r,order):
 x=(r>>1)^(np.zeros_like(r)-(r&1))
 for _ in range(order):x=np.cumsum(x,dtype=r.dtype)
 return x
def pack(v,width):
 acc=nb=0;out=bytearray();mask=(1<<width)-1
 for x in v.tolist():
  acc|=(x&mask)<<nb;nb+=width
  while nb>=8:out.append(acc&255);acc>>=8;nb-=8
 if nb:out.append(acc&255)
 return bytes(out)
def unpack(b,n,width,dtype):
 acc=nb=i=0;out=[];mask=(1<<width)-1
 for _ in range(n):
  while nb<width:acc|=b[i]<<nb;i+=1;nb+=8
  out.append(acc&mask);acc>>=width;nb-=width
 return np.asarray(out,dtype=dtype)
def intrecords(x):
 out=bytearray();hist={};exc=0
 for i in range(0,len(x),256):
  v=x[i:i+256];best=None
  for order in range(4):
   r=residual(v,order)
   for width in range(17):
    ids=np.flatnonzero(r.astype(np.uint32)>=1<<width)
    cost=(len(v)*width+7)//8+3*len(ids)+4
    key=(cost,order,width)
    if best is None or key<best[0]:best=(key,r,ids)
  (_,order,width),r,ids=best
  out.extend(struct.pack('<BBH',order,width,len(ids)));out.extend(pack(r,width))
  for j in ids:out.extend(struct.pack('<BH',int(j),int(r[j])))
  hist[str(order)]=hist.get(str(order),0)+1;exc+=len(ids)
 return bytes(out),dict(orders=hist,exceptions=exc)
def floatrecords(x):
 out=bytearray();hist={};exc=rawblocks=0
 for i in range(0,len(x),256):
  v=x[i:i+256];bits=v.view('<u8');best=(1+8*len(v),255,0,0);payload=bytes([255])+v.tobytes();count=0
  for k in range(7):
   with np.errstate(all='ignore'):
    scaled=np.rint(v*10**k);valid=np.isfinite(scaled)&(np.abs(scaled)<=2**53-1)
    y=np.where(valid,scaled,0).astype('<i8')
    back=(y.astype('<f8')/(10**k)).view('<u8');valid=valid&(back==bits);y[~valid]=0
   ids=np.flatnonzero(~valid)
   for order in range(3):
    r=residual(y.view('<u8'),order);width=int(r.max()).bit_length() if len(r) else 0
    key=(5+(len(v)*width+7)//8+9*len(ids),k,order,width)
    if key<best:
     best=key;payload=struct.pack('<BBBH',k,order,width,len(ids))+pack(r,width)+b''.join(struct.pack('<BQ',int(j),int(bits[j])) for j in ids);count=len(ids)
  out.extend(payload);k=best[1];hist[str(k)]=hist.get(str(k),0)+1;exc+=count;rawblocks+=int(k==255)
 return bytes(out),dict(scales=hist,exceptions=exc,rawblocks=rawblocks)
def frame(b,magic,k,payload,w):
 return struct.pack('<4sIIB',magic,len(b)//w,zlib.crc32(b),k)+enc(payload,k)
def restore(b):
 magic,n,crc,k=struct.unpack_from('<4sIIB',b);assert n<=65536
 p=dec(b[13:],k);i=0;out=bytearray()
 if magic==b'H62D':
  r=np.frombuffer(p,dtype=np.uint8).reshape(2,n).T.copy().view('<u2').reshape(-1);out.extend(inv(r,2).tobytes());i=len(p)
 else:
  for start in range(0,n,256):
   m=min(256,n-start)
   if magic==b'H62I':
    order,width,count=struct.unpack_from('<BBH',p,i);i+=4;scale=None;dtype='<u2'
   else:
    assert magic==b'H62F';scale=p[i]
    if scale==255:out.extend(p[i+1:i+1+8*m]);i+=1+8*m;continue
    scale,order,width,count=struct.unpack_from('<BBBH',p,i);i+=5;dtype='<u8'
   size=(m*width+7)//8;r=unpack(p[i:i+size],m,width,dtype);i+=size
   if magic==b'H62I':
    for _ in range(count):
     j,v=struct.unpack_from('<BH',p,i);i+=3;r[j]=v
    out.extend(inv(r,order).tobytes())
   else:
    v=(inv(r,order).view('<i8').astype('<f8')/(10**scale)).view('<u8')
    for _ in range(count):
     j,x=struct.unpack_from('<BQ',p,i);i+=9;v[j]=x
    out.extend(v.tobytes())
 assert i==len(p) and len(out)==n*(8 if magic==b'H62F' else 2) and zlib.crc32(out)==crc
 return bytes(out)
def measure(group,name,b,w,rate,source,work):
 r={};custom=[]
 def trial(key,stream,decode,elapsed=None):
  t=time.perf_counter_ns();out=decode(stream);d=time.perf_counter_ns()-t;assert out==b
  r[key]=dict(bytes=len(stream),sha256=sha(stream),encode_wall_ns=elapsed,decode_wall_ns=d)
 def run(key,fn,decode):
  t=time.perf_counter_ns();s=fn();elapsed=time.perf_counter_ns()-t;trial(key,s,decode,elapsed);return s
 trial('raw',b,lambda x:x)
 for k,nm in ((1,'xz5'),(2,'zstd15')):run(nm,lambda k=k:enc(b,k),lambda s,k=k:dec(s,k))
 src=work/'input';src.write_bytes(b)
 if w==2:
  p=work/'out.flac';d=work/'restore.raw'
  def fc():
   call(['flac','-s','-8','--no-padding','--no-seektable','--force-raw-format','--endian=little','--sign=signed','--channels=1','--bps=16','--sample-rate='+str(rate),'-o',str(p),str(src)]);return p.read_bytes()
  def fd(s):
   p.write_bytes(s);call(['flac','-s','-d','--force-raw-format','--endian=little','--sign=signed','-o',str(d),str(p)]);return d.read_bytes()
  run('flac8',fc,fd)
  x=np.frombuffer(b,dtype='<u2');t=time.perf_counter_ns();payload,stats=intrecords(x);pre=time.perf_counter_ns()-t
  fixed=residual(x,2).view(np.uint8).reshape(-1,2).T.copy().tobytes()
  for k,nm in enumerate(('plain','xz5','zstd15')):
   key='block-'+nm;run(key,lambda k=k:frame(b,b'H62I',k,payload,2),restore);r[key]['encode_wall_ns']+=pre;custom.append(key)
  for k,nm in ((1,'xz5'),(2,'zstd15')):
   key='delta2-shuffle-'+nm;run(key,lambda k=k:frame(b,b'H62D',k,fixed,2),restore);custom.append(key)
  controls=('raw','xz5','zstd15','flac8')
 else:
  p=work/'out.alp';d=work/'restore'
  def ac():call([str(alp),'encode',str(src),str(p)]);return p.read_bytes()
  def ad(s):p.write_bytes(s);call([str(alp),'decode',str(p),str(d)]);return d.read_bytes()
  al=run('alp',ac,ad)
  for k,nm in ((1,'xz5'),(2,'zstd15')):run('alp-'+nm,lambda k=k:enc(al,k),lambda s,k=k:ad(dec(s,k)))
  x=np.frombuffer(b,dtype='<f8');t=time.perf_counter_ns();payload,stats=floatrecords(x);pre=time.perf_counter_ns()-t
  for k,nm in enumerate(('plain','xz5','zstd15')):
   key='block-'+nm;run(key,lambda k=k:frame(b,b'H62F',k,payload,8),restore);r[key]['encode_wall_ns']+=pre;custom.append(key)
  controls=('raw','xz5','zstd15','alp','alp-xz5','alp-zstd15')
 best=min(controls,key=lambda k:r[k]['bytes']);ours=min(custom,key=lambda k:r[k]['bytes'])
 return dict(type='sample',group=group,name=name,source=source,input_bytes=len(b),sha256=sha(b),best_control=best,control_bytes=r[best]['bytes'],best_candidate=ours,candidate_bytes=r[ours]['bytes'],stats=stats,checks=len(r),candidates=r)
def inputs():
 for rid in ('100','101','103'):
  base='https://physionet.org/files/mitdb/1.0.0/'+rid
  try:
   h=fetch(base+'.hea');b=fetch(base+'.dat');lines=h.decode().splitlines();assert lines[0].split()[1:3]==['2','360'] and all(x.split()[1]=='212' for x in lines[1:3])
   assert len(b)>=65536*3
   x=np.frombuffer(b[:65536*3],dtype=np.uint8).reshape(-1,3).astype(np.int32)
   for j,y in enumerate((x[:,0]+((x[:,1]&15)<<8),x[:,2]+((x[:,1]&240)<<4))):
    y=np.where(y>=2048,y-4096,y).astype('<i2');yield ('ecg',rid+'-ch'+str(j),y.tobytes(),2,360,dict(url=base+'.dat',sha256=sha(b),header_sha256=sha(h)))
  except (OSError,ValueError,AssertionError,subprocess.SubprocessError) as e:yield dict(type='skip',group='ecg',name=rid,error=repr(e))
 for name in ('0_jackson_0','1_nicolas_0','2_theo_0','3_george_0','4_lucas_0','5_yweweler_0'):
  url='https://raw.githubusercontent.com/Jakobovski/free-spoken-digit-dataset/26eb9aaf76e81b692f806f9140c2d2777410d7a1/recordings/'+name+'.wav'
  try:
   b=fetch(url)
   with wave.open(io.BytesIO(b)) as f:
    assert f.getnchannels()==1 and f.getsampwidth()==2 and f.getnframes()<=65536;rate=f.getframerate();v=f.readframes(f.getnframes())
   yield ('speech',name,v,2,rate,dict(url=url,sha256=sha(b)))
  except (OSError,ValueError,AssertionError,subprocess.SubprocessError,wave.Error) as e:yield dict(type='skip',group='speech',name=name,error=repr(e))
 for group,names in [('neon',('neon_air_pressure','neon_bio_temp_c')),('stocks',('stocks_de','stocks_usa_c')),('poi',('poi_lat','poi_lon'))]:
  for name in names:
   url='https://raw.githubusercontent.com/cwida/ALP/31ca0ed11c93c99d3f5b5c30e01a3e1c3832d3ce/data/samples/'+name+'.csv'
   try:
    b=fetch(url);lines=b.decode().splitlines();assert len(lines)>=1024
    v=np.asarray([float(s.strip()) for s in lines[:1024]],dtype='<f8')
    yield (group,name,v.tobytes(),8,None,dict(url=url,sha256=sha(b)))
   except (OSError,ValueError,AssertionError,subprocess.SubprocessError) as e:yield dict(type='skip',group=group,name=name,error=repr(e))
 rng=np.random.default_rng(20261124)
 yield ('synthetic-int','random',rng.integers(-32768,32768,16384,dtype=np.int16).astype('<i2').tobytes(),2,8000,dict(seed=20261124))
 yield ('synthetic-int','linear',(np.arange(16384,dtype=np.int32)*2).astype('<i2').tobytes(),2,8000,dict(seed=20261124))
 bits=np.asarray([0,0x8000000000000000,0x7ff8000000000012,0x7ff0000000000000,0xfff0000000000000,1,0x3ff0000000000000]*150,dtype='<u8')
 yield ('synthetic-float','special-bits',bits.tobytes(),8,None,dict(generator='special bit patterns'))
 yield ('synthetic-float','decimal',((np.arange(16384)%1000)/100).astype('<f8').tobytes(),8,None,dict(generator='decimal grid'))
a.out.parent.mkdir(parents=True,exist_ok=True);rows=[]
with a.out.open('x') as f:
 def log(r):f.write(json.dumps(r)+'\n');f.flush()
 log(dict(type='meta',protocol='H062',script_sha256=sha(pathlib.Path(__file__).read_bytes()),alp_sha256=sha(alp.read_bytes()),flac=call(['flac','--version']).decode().strip(),numpy=np.__version__,zstd=lib.ZSTD_versionString().decode(),affinity=sorted(os.sched_getaffinity(0))))
 for item in inputs():
  if isinstance(item,dict):log(item);print(item,flush=True);continue
  with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h062-') as td:
   r=measure(item[0],item[1],item[2],item[3],item[4],item[5],pathlib.Path(td))
   rows.append(r);log(r);print(r['group'],r['name'],r['input_bytes'],r['best_control'],r['control_bytes'],r['best_candidate'],r['candidate_bytes'],r['stats'],flush=True)
 for g,expected in [('ecg',6),('speech',6),('neon',2),('stocks',2),('poi',2),('synthetic-int',2),('synthetic-float',2)]:
  rs=[r for r in rows if r['group']==g];b=sum(r['control_bytes'] for r in rs);c=sum(r['candidate_bytes'] for r in rs)
  result=dict(type='summary',group=g,samples=len(rs),expected=expected,input_bytes=sum(r['input_bytes'] for r in rs),control=b,candidate=c,saving_percent=100*(1-c/b) if b else None,checks=sum(r['checks'] for r in rs),gate=len(rs)==expected and c<=.95*b)
  log(result);print(json.dumps(result),flush=True)
