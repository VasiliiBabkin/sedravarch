#!/usr/bin/env python3
"""Resume H131 after bounded job timeout. Preserve original partial JSONL."""
import pathlib,sys,json,hashlib
src,partial,resumed=map(pathlib.Path,sys.argv[1:4])
s=src.read_text()
raw=partial.read_bytes()
assert raw.endswith(b'\n'),"incomplete last line"
rr=[json.loads(line) for line in raw.splitlines()]
assert rr[0]['type']=='meta' and rr[0]['script_sha256']==hashlib.sha256(src.read_bytes()).hexdigest()
assert all(r['type'] in ('meta','source','measurement') for r in rr)
assert all(r['status']=='PASS' for r in rr if r['type']=='measurement')
keys=[(r['group'],r['name'],r['codec'],r['rep']) for r in rr if r['type']=='measurement']
assert len(keys)==len(set(keys))
def replace(a,b):
 global s
 assert s.count(a)==1,a
 s=s.replace(a,b)
replace("a.out.parent.mkdir(parents=True,exist_ok=True);rows=[];names=[]",f"""a.out.parent.mkdir(parents=True,exist_ok=True)
previous=pathlib.Path({str(partial)!r}).read_bytes()
assert sha(previous)=={hashlib.sha256(raw).hexdigest()!r}
old=[json.loads(line) for line in previous.splitlines()]
rows=[r for r in old if r['type']=='measurement'];names=[]
done={{(r['group'],r['name'],r['codec'],r['rep']) for r in rows}}
prior_sources={{(r['group'],r['name']):r for r in old if r['type']=='source'}}
# lock already held; remove only stale temporary directories from this interrupted H131 run
for stale in (root/'tmp').glob('h131-*'):
 if stale.is_dir() and not stale.is_symlink():shutil.rmtree(stale)
""")
replace("with a.out.open('x') as f:", "with a.out.open('x') as f:\n f.write(previous.decode());f.flush()")
start=s.index(" log(dict(type='meta',protocol='H131'")
end=s.index("\n for g,n,b,src in sources():",start)
s=s[:start]+""" log(dict(type='resume',partial_sha256=sha(previous),resume_script_sha256=sha(pathlib.Path(__file__).read_bytes()),prior_measurements=len(rows),reason='first 300s job timed out'))"""+s[end:]
replace("h=sha(b);names.append((g,n));log(dict(type='source',group=g,name=n,sha256=h,input_bytes=len(b),**src))","""h=sha(b);names.append((g,n));source=dict(type='source',group=g,name=n,sha256=h,input_bytes=len(b),**src)
  if (g,n) in prior_sources:assert prior_sources[(g,n)]==source
  else:log(source)""")
replace("r=measure(g,n,b,k,rep,w);rows.append(r);log(r)","""if (g,n,k,rep) in done:continue
     r=measure(g,n,b,k,rep,w);rows.append(r);log(r)""")
replace("r=measure(g,n,b,k,0,w);rows.append(r);log(r);print('REF'","""if (g,n,k,0) in done:continue
    r=measure(g,n,b,k,0,w);rows.append(r);log(r);print('REF'""")
resumed.write_text(s)
print("PRESERVED",len(keys),"measurements",hashlib.sha256(raw).hexdigest())
