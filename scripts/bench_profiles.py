#!/usr/bin/env python3
"""Profile size, wall time, CPU time and maximum RSS with a minimal wait4 launcher on Linux."""
from pathlib import Path
import argparse, subprocess, tempfile, statistics, csv, sys

def measure(cmd, report, helper):
    subprocess.run([helper,report,*map(str,cmd)],check=True)
    return [float(x) for x in report.read_text().split()]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("binary",type=Path);p.add_argument("files",nargs="+",type=Path)
    p.add_argument("--runs",type=int,default=3);p.add_argument("--threads",type=int,default=2)
    args=p.parse_args()
    if args.runs<1 or not 1<=args.threads<=8:p.error("invalid runs or threads")
    binary=args.binary.resolve()
    w=csv.writer(sys.stdout)
    w.writerow(["file","bytes","profile","threads","archive_bytes","pack_wall_s","pack_cpu_s","pack_rss_KiB","unpack_wall_s","unpack_cpu_s","unpack_rss_KiB"])
    with tempfile.TemporaryDirectory() as tmp:
        a,b,t,helper=[Path(tmp)/n for n in ["archive","restored","time","measure"]]
        subprocess.run(["cc","-O2","-Wall","-Wextra",str(Path(__file__).with_name("measure.c")),"-o",helper],check=True)
        for file in args.files:
            file=file.resolve();data=file.read_bytes()
            for mode in ["fast","balanced","deep","extreme"]:
                expected=None
                for threads in sorted({1,args.threads}):
                    pack=[];unpack=[]
                    for _ in range(args.runs):
                        a.unlink(missing_ok=True);b.unlink(missing_ok=True)
                        pack.append(measure([binary,"pack-profile",mode,threads,file,a],t,helper))
                        unpack.append(measure([binary,"unpack",a,b,len(data)],t,helper))
                        if b.read_bytes()!=data:raise RuntimeError("roundtrip mismatch")
                        if expected is None:expected=a.read_bytes()
                        elif a.read_bytes()!=expected:raise RuntimeError("nondeterministic output")
                    def med(rows):
                        return [statistics.median(r[0] for r in rows),statistics.median(r[1]+r[2] for r in rows),max(r[3] for r in rows)]
                    w.writerow([file.name,len(data),mode,threads,a.stat().st_size,*med(pack),*med(unpack)])
                    sys.stdout.flush()
if __name__=="__main__":main()
