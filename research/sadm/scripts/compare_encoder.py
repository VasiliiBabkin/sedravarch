#!/usr/bin/env python3
"""Measure two SADM encoders and require byte-identical wire output."""
import argparse
from pathlib import Path
import json
import os
import subprocess
import tempfile

from bench import REPO, files_equal, hash_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("files", type=Path, nargs="+")
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("repetitions must be positive")
    rows = []
    binaries = [args.before.resolve(), args.after.resolve()]
    with tempfile.TemporaryDirectory(prefix="sadm-compare-") as directory:
        root = Path(directory)
        launcher, metrics, restored = [root / name for name in ["measure", "metrics", "restored"]]
        archives = [root / "before.sadm", root / "after.sadm"]
        subprocess.run(["cc", "-O2", REPO / "scripts/measure.c", "-o", launcher], check=True)
        for path in args.files:
            for rep in range(args.repetitions):
                runs = [None, None]
                for revision in [rep % 2, 1 - rep % 2]:
                    binary = binaries[revision]
                    archive = archives[revision]
                    subprocess.run([launcher, metrics, binary, "encode", archive, path], check=True)
                    wall, user, system, rss = metrics.read_text().split()
                    runs[revision] = {"wall_s": float(wall), "cpu_s": float(user) + float(system),
                                      "peak_rss_kib": int(rss)}
                    subprocess.run([binary, "decode", archive, restored], check=True)
                    assert files_equal(path, restored), (path, revision)
                    restored.unlink()
                assert files_equal(*archives), path
                rows.append({"path": str(path), "input_bytes": path.stat().st_size,
                             "input_sha256": hash_file(path), "archive_bytes": archives[0].stat().st_size,
                             "archive_sha256": hash_file(archives[0]), "repetition": rep,
                             "before": runs[0], "after": runs[1]})
                for archive in archives:
                    archive.unlink()
    args.out.write_text(json.dumps({"binaries_sha256": list(map(hash_file, binaries)),
                                    "affinity_count": len(os.sched_getaffinity(0)), "rows": rows},
                                   indent=2) + "\n")


if __name__ == "__main__":
    main()
