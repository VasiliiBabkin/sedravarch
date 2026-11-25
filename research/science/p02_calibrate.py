#!/usr/bin/env python3
"""P02: bounded single-vCPU timing calibration, not a codec ranking."""
import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import platform
import random
import statistics as st
import time
import zlib

def summary(samples):
    m=st.median(samples)
    q=st.quantiles(samples,n=4,method="inclusive")
    return {"median_ns":m,"range_ratio":(max(samples)-min(samples))/m,
            "iqr_ratio":(q[2]-q[0])/m}

def ticks(cpu):
    line=next(s for s in pathlib.Path("/proc/stat").read_text().splitlines()
              if s.startswith(f"cpu{cpu} "))
    return list(map(int,line.split()[1:]))

def sample(fn, loops, expected):
    w=time.perf_counter_ns()
    c=time.process_time_ns()
    for _ in range(loops):
        out=fn()
    cpu=time.process_time_ns()-c
    wall=time.perf_counter_ns()-w
    if out!=expected:
        raise RuntimeError("output mismatch")
    return {"cpu_ns":cpu,"wall_ns":wall}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lock",type=pathlib.Path,required=True,
                   help="same lock as other lab benchmarks")
    p.add_argument("--cpu",type=int)
    p.add_argument("--out",type=pathlib.Path,required=True)
    a=p.parse_args()
    allowed=sorted(os.sched_getaffinity(0))
    cpu=allowed[-1] if a.cpu is None else a.cpu
    if cpu not in allowed:
        raise SystemExit("CPU outside affinity")
    with a.lock.open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        os.sched_setaffinity(0,{cpu})
        os.nice(10)
        rng=random.Random(20261125)
        data=rng.randbytes(1024*1024)+b"SedravArch test 0123456789\n"*40000
        packed=zlib.compress(data,6)
        jobs={"encode":(lambda:zlib.compress(data,6),packed),
              "decode":(lambda:zlib.decompress(packed),data)}
        report={"schema":"p02-calibration-v1","host":platform.machine(),
                "kernel":platform.release(),"python":platform.python_version(),
                "zlib":zlib.ZLIB_RUNTIME_VERSION,"cpu":cpu,"allowed":allowed,
                "affinity":sorted(os.sched_getaffinity(0)),"nice":os.nice(0),
                "input_bytes":len(data),"input_sha256":hashlib.sha256(data).hexdigest(),
                "packed_sha256":hashlib.sha256(packed).hexdigest(),
                "batches":3,"repetitions":7,"target_cpu_ns":100_000_000,
                "limits":{"range_ratio":0.20,"iqr_ratio":0.10,"median_shift":0.10,
                          "median_wall_cpu_ratio":1.10,"steal_ratio":0.02},
                "workloads":{},"physical_isolation_verified":False}
        before=ticks(cpu)
        order=list(jobs)
        for name,(fn,expected) in jobs.items():
            loops=1
            while True:
                s=sample(fn,loops,expected)
                if s["cpu_ns"]>=100_000_000 or loops>=512:
                    break
                loops=min(512,max(loops+1,int(loops*100_000_000/max(1,s["cpu_ns"]))))
            if s["cpu_ns"]<50_000_000:
                raise RuntimeError("sample too short")
            report["workloads"][name]={"loops":loops,"batches":[]}
        for b in range(3):
            random.Random(20261125+b).shuffle(order)
            for name in order:
                fn,expected=jobs[name]
                job=report["workloads"][name]
                sample(fn,job["loops"],expected)
                rows=[sample(fn,job["loops"],expected) for _ in range(7)]
                job["batches"].append({"samples":rows,
                    "cpu":summary([r["cpu_ns"] for r in rows]),
                    "wall":summary([r["wall_ns"] for r in rows]),
                    "wall_cpu_median":st.median([r["wall_ns"]/r["cpu_ns"] for r in rows])})
            if b<2: time.sleep(1)
        after=ticks(cpu)
        # Linux user/nice already include guest time; avoid double counting.
        delta=[y-x for x,y in zip(before[:8],after[:8])]
        total=sum(delta)
        steal=delta[7]/total if total>0 and len(delta)==8 else None
        report["cpu_ticks_delta"]=delta
        report["steal_ratio"]=steal
        cpu_ok=True
        wall_ok=True
        for job in report["workloads"].values():
            for key in ("cpu","wall"):
                vals=[b[key]["median_ns"] for b in job["batches"]]
                shift=(max(vals)-min(vals))/st.median(vals)
                job[key+"_median_shift"]=shift
                ok=shift<=.10 and all(b[key]["range_ratio"]<=.20 and b[key]["iqr_ratio"]<=.10 for b in job["batches"])
                job[key+"_pass"]=ok
                if key=="cpu": cpu_ok &= ok
                else: wall_ok &= ok
            wall_ok &= all(b["wall_cpu_median"]<=1.10 for b in job["batches"])
        report["cpu_pass"]=bool(cpu_ok)
        report["wall_pass"]=bool(wall_ok and steal is not None and 0<=steal<=.02)
        report["status"]="CALIBRATION_PASS" if report["cpu_pass"] and report["wall_pass"] else "CALIBRATION_FAIL"
        report["scope"]="single session synthetic zlib calibration; no H13 or product performance claim"
        with a.out.open("x") as f:
            json.dump(report,f,indent=2)
            f.write("\n")
        print(json.dumps({"status":report["status"],"cpu_pass":report["cpu_pass"],
                          "wall_pass":report["wall_pass"],"cpu":cpu,"steal_ratio":steal,
                          "workloads":{k:{"cpu_median_shift":v["cpu_median_shift"],
                              "wall_median_shift":v["wall_median_shift"],
                              "cpu_range_max":max(b["cpu"]["range_ratio"] for b in v["batches"]),
                              "wall_range_max":max(b["wall"]["range_ratio"] for b in v["batches"]),
                              "wall_cpu_max":max(b["wall_cpu_median"] for b in v["batches"])}
                              for k,v in report["workloads"].items()}},indent=2))
        return 0 if report["status"]=="CALIBRATION_PASS" else 2

if __name__=="__main__":
    raise SystemExit(main())
