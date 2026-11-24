#!/usr/bin/env python3
"""H04b.2: loss screening with byte-exact external controls."""
import argparse,fcntl,hashlib,json,lzma,math,os,pathlib,shutil,subprocess,tempfile,time
p=argparse.ArgumentParser();p.add_argument('--lab',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args();root=a.lab.resolve()
os.nice(10);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
lock=(root/'tmp/benchmark.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);assert shutil.disk_usage(root).free>=5*1024**3
kernel=root/'experiments/h04b2/predict'
def sha(b):return hashlib.sha256(b).hexdigest()
def call(args,cwd=None):return subprocess.run(args,cwd=cwd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45).stdout
def measure(group,name,b,source):
 with tempfile.TemporaryDirectory(dir=root/'tmp',prefix='h04b2-') as td:
  d=pathlib.Path(td);p=d/'input.bin';p.write_bytes(b);models={}
  for line in call([str(kernel),str(p)]).decode().splitlines():
   i,loss,coverage,correct,wall=line.split();loss=float(loss);assert math.isfinite(loss) and loss>=0
   models['ABCD'[int(i)]]=dict(loss_bits=loss,diagnostic_bytes=math.ceil(loss/8)+15,covered=int(coverage),correct=int(correct),wall_s=float(wall))
  assert len(models)==4
  z=lzma.compress(b,preset=5,check=lzma.CHECK_CRC64);assert lzma.decompress(z)==b
  c={'xz5':len(z)}
  call(['7z','a','-t7z','-m0=PPMd','-mx=5','-mmt=1','-mtc=off','-mta=off','-mtm=off','p.7z','input.bin'],d)
  assert call(['7z','x','-so','-mmt=1','p.7z','input.bin'],d)==b;c['ppmd5']=(d/'p.7z').stat().st_size
  z=call(['zstd','-q','-T1','-15','-c',str(p)]);(d/'p.zst').write_bytes(z);assert call(['zstd','-q','-d','-c',str(d/'p.zst')])==b;c['zstd15']=len(z)
  if shutil.which('zpaq'):
   call(['zpaq','add','p.zpaq','input.bin','-method','5','-threads','1'],d)
   p.unlink();call(['zpaq','extract','p.zpaq','-threads','1'],d);assert p.read_bytes()==b;c['zpaq5']=(d/'p.zpaq').stat().st_size
  return dict(type='sample',group=group,name=name,input_bytes=len(b),sha256=sha(b),source=source,models=models,controls=c,strong=min(c[k] for k in ('xz5','ppmd5','zstd15')),checks=len(c))
a.out.parent.mkdir(parents=True,exist_ok=True);rows=[]
with a.out.open('x') as f:
 def log(x):f.write(json.dumps(x)+'\n');f.flush()
 log(dict(type='meta',protocol='H04B2',script_sha256=sha(pathlib.Path(__file__).read_bytes()),kernel_sha256=sha(kernel.read_bytes()),affinity=sorted(os.sched_getaffinity(0)),zpaq=shutil.which('zpaq')))
 for item in json.loads((root/'corpora/manifest.json').read_text()):
  if item['group']!='silesia':continue
  p=(root/item['path']).resolve();assert p.is_relative_to(root/'corpora')
  b=p.read_bytes();assert sha(b)==item['sha256'];r=measure('silesia',p.name,b[:65536],dict(path=item['path'],sha256=sha(b)));rows.append(r);log(r);print(r['group'],r['name'],r['strong'],[v['diagnostic_bytes'] for v in r['models'].values()],flush=True)
 for g,paths in [('local-text',['/usr/lib/python3.12/argparse.py','/usr/lib/python3.12/ast.py','/usr/lib/python3.12/email/message.py','/usr/share/common-licenses/GPL-3']),('local-binary',['/usr/bin/grep','/usr/bin/sed','/usr/bin/tar','/usr/bin/find'])]:
  for path in paths:
   p=pathlib.Path(path);b=p.read_bytes();r=measure(g,p.name,b[:65536],dict(path=path,sha256=sha(b)));rows.append(r);log(r);print(r['group'],r['name'],r['strong'],[v['diagnostic_bytes'] for v in r['models'].values()],flush=True)
 for g,n in [('silesia',12),('local-text',4),('local-binary',4)]:
  rr=[r for r in rows if r['group']==g];assert len(rr)==n
  loss={k:sum(r['models'][k]['loss_bits'] for r in rr) for k in 'ABCD'}
  sizes={k:sum(r['models'][k]['diagnostic_bytes'] for r in rr) for k in 'ABCD'};strong=sum(r['strong'] for r in rr)
  x=dict(type='summary',group=g,samples=n,input_bytes=sum(r['input_bytes'] for r in rr),loss_bits=loss,diagnostic_bytes=sizes,strong=strong,controls={k:sum(r['controls'][k] for r in rr) for k in rr[0]['controls']},gain_D_A=100*(1-loss['D']/loss['A']),gain_B_A=100*(1-loss['B']/loss['A']),gain_C_B=100*(1-loss['C']/loss['B']),gain_D_C=100*(1-loss['D']/loss['C']),gain_D_control=100*(1-sizes['D']/strong),coverage_D=sum(r['models']['D']['covered'] for r in rr),correct_D=sum(r['models']['D']['correct'] for r in rr),checks=sum(r['checks'] for r in rr),wall_s={k:sum(r['models'][k]['wall_s'] for r in rr) for k in 'ABCD'},gate_a=loss['D']<=.90*loss['A'],gate_b=sizes['D']<=.95*strong)
  log(x);print(json.dumps(x),flush=True)
