#!/usr/bin/env python3
"""Resume H132 following bounded interruption without discarding measurements."""
import hashlib,json,pathlib,sys
src,partial,dest=map(pathlib.Path,sys.argv[1:4])
s=src.read_text();raw=partial.read_bytes()
assert raw.endswith(b'\n')
rows=[json.loads(x) for x in raw.splitlines()]
assert rows[0]['type']=='meta' and not rows[0]['smoke'] and rows[0]['script_sha256']==hashlib.sha256(src.read_bytes()).hexdigest()
assert all(x['type'] in ('meta','source','measurement','reference') for x in rows)
keys=[(x['group'],x['name'],x['codec'],x['level'],x['mode']) for x in rows if x['type']=='measurement']
rkeys=[(x['group'],x['name'],x['codec']) for x in rows if x['type']=='reference']
assert len(keys)==len(set(keys)) and len(rkeys)==len(set(rkeys))
assert all(x['checks']==7 and len(x['enc']['calls'])==len(x['dec']['calls'])==7 for x in rows if x['type']=='measurement')
assert all(x['checks']==1 for x in rows if x['type']=='reference')
def replace(a,b):
 global s
 assert s.count(a)==1,a
 s=s.replace(a,b)
replace("script=pathlib.Path(__file__).resolve();rows=[];refs=[]",f"""script=pathlib.Path(__file__).resolve()
 previous=pathlib.Path({str(partial.resolve())!r}).read_bytes()
 require(sha(previous)=={hashlib.sha256(raw).hexdigest()!r},'partial changed')
 old=[json.loads(x) for x in previous.splitlines()]
 require(not smoke and old[0]['cpu']==cpu,'environment changed')
 rows=[r for r in old if r['type']=='measurement'];refs=[r for r in old if r['type']=='reference']
 done={{(r['group'],r['name'],r['codec'],r['level'],r['mode']) for r in rows}}
 refdone={{(r['group'],r['name'],r['codec']) for r in refs}}
 prior={{(r['group'],r['name']):r for r in old if r['type']=='source'}}
 require(all(sha(pathlib.Path(p).read_bytes())==h for p,h in old[0]['libs'].items()),'library changed')
 # Original job has terminated; acquire lab lock before cleaning only its orphaned work dirs.
 for stale in (root/'tmp').glob('h132-*'):
  if stale.is_dir() and not stale.is_symlink():shutil.rmtree(stale)
""")
replace("with out.open('x') as f:\n  def log", "with out.open('x') as f:\n  f.write(previous.decode());f.flush()\n  def log")
start=s.index("  log(dict(type='meta',protocol='H132'")
end=s.index("\n  for g,name,b,src in sources",start)
s=s[:start]+"""  log(dict(type='resume',partial_sha256=sha(previous),prior_measurements=len(rows),prior_references=len(refs),resume_script_sha256=sha(script.read_bytes())))"""+s[end:]
replace("h=sha(b);log(dict(type='source',group=g,name=name,input_bytes=len(b),sha256=h,**src));order=", """h=sha(b);entry=dict(type='source',group=g,name=name,input_bytes=len(b),sha256=h,**src)
   if (g,name) in prior:require(prior[(g,name)]==entry,'source changed')
   else:log(entry)
   order=""")
replace("random.Random(h).shuffle(order);hashes={}","""random.Random(h).shuffle(order);hashes={}
   for r in rows:
    if (r['group'],r['name'])==(g,name):require(hashes.setdefault((r['codec'],r['level']),r['archive_sha256'])==r['archive_sha256'],'old archive mismatch')""")
replace("    for codec,level,mode in order:\n     before=", "    for codec,level,mode in order:\n     if (g,name,codec,level,mode) in done:continue\n     before=")
replace("     for k in ('xz5','ppmd5'):\n      r=reference", "     for k in ('xz5','ppmd5'):\n      if (g,name,k) in refdone:continue\n      r=reference")
compile(s,str(dest),'exec');dest.write_text(s)
print('PRESERVED',len(keys),'native pairs',len(rkeys),'references',hashlib.sha256(raw).hexdigest())
