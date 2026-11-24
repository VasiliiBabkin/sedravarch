#!/usr/bin/env python3
"""Linux benchmark. Requires release binaries, native wait4 launcher and codec CLIs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile

REPO = Path(__file__).resolve().parents[3]


def command(args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def hash_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()



def files_equal(first, second):
    with first.open("rb") as a, second.open("rb") as b:
        while True:
            left = a.read(1024 * 1024)
            if left != b.read(1024 * 1024):
                return False
            if not left:
                return True

def run(args):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canterbury", type=Path)
    parser.add_argument("--silesia", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--ablation-repetitions", type=int, default=2)
    parser.add_argument("--only-family", action="store_true")
    parser.add_argument("--sadm-only", action="store_true")
    parser.add_argument("--legacy-policy", action="store_true",
                        help="the pilot executable enabled multiscale by default")
    parser.add_argument("--family-directory", type=Path)
    parser.add_argument("--seven", default="7zz")
    parser.add_argument("--sadm", type=Path, default=REPO / "research/sadm/target/release/sadm")
    opts = parser.parse_args(args)
    if min(opts.repetitions, opts.ablation_repetitions) < 1:
        parser.error("repetition counts must be positive")
    if not opts.only_family and (opts.canterbury is None or opts.silesia is None):
        parser.error("provide both corpus directories or --only-family")
    sadm = opts.sadm.resolve()
    boundary_ablation = ("sadm-no-multiscale", "--no-multiscale") if opts.legacy_policy else (
        "sadm-multiscale", "--multiscale")
    ablations = [boundary_ablation, *((f"sadm-no-{name}", f"--no-{name}")
                   for name in ["references", "delta", "rans", "predict"])]
    stable = REPO / "target/release/sedravarch"
    with tempfile.TemporaryDirectory(prefix="sadm-bench-") as temp:
        root = Path(temp)
        launcher = root / "measure"
        subprocess.run(["cc", "-O2", REPO / "scripts/measure.c", "-o", launcher], check=True)
        profile = root / "usage"
        rows = []
        manifest = {}

        def measured(argv, stdout=None, cwd=None):
            env = dict(os.environ, LC_ALL="C")
            if stdout is None:
                subprocess.run([launcher, profile, *argv], check=True,
                               stdout=subprocess.DEVNULL, cwd=cwd, env=env)
            else:
                with stdout.open("wb") as stream:
                    subprocess.run([launcher, profile, *argv], check=True,
                                   stdout=stream, cwd=cwd, env=env)
            wall, user, sys, rss = profile.read_text().split()
            return {"wall_s": float(wall), "user_s": float(user), "system_s": float(sys),
                    "peak_rss_kib": int(rss)}

        def bench(dataset, input_file, tool, rep, encode, decode, archive, restored,
                  encode_stdout=False, decode_stdout=False, cwd=None):
            archive.unlink(missing_ok=True)
            restored.unlink(missing_ok=True)
            packed = measured(encode, archive if encode_stdout else None, cwd)
            unpacked = measured(decode, restored if decode_stdout else None, cwd)
            assert files_equal(input_file, restored), (dataset, tool)
            rows.append({"dataset": dataset, "tool": tool, "rep": rep,
                         "archive_bytes": archive.stat().st_size, "archive_sha256": hash_file(archive),
                         "encode": packed, "decode": unpacked})
            archive.unlink()
            restored.unlink()

        archive = root / "archive.7z"
        restored = root / "restored"
        if not opts.only_family:
            cases = {}
            for suite, path in [("canterbury", opts.canterbury), ("silesia", opts.silesia)]:
                for item in sorted(path.resolve().iterdir()):
                    if item.is_file() and item.name != "SHA1SUM":
                        cases[f"{suite}/{item.name}"] = item
            generated = root / "generated"
            generated.mkdir()
            random_file = generated / "random.bin"
            random_file.write_bytes(random.Random(20261124).randbytes(1024 * 1024))
            numeric = generated / "numeric.bin"
            numeric.write_bytes(b"".join((i * 7).to_bytes(4, "little") for i in range(65536)))
            database = generated / "records.sqlite"
            with sqlite3.connect(database) as db:
                db.execute("create table records(id integer primary key, band integer, label text)")
                db.executemany("insert into records values (?, ?, ?)",
                               ((i, i % 31, f"record-{i % 172}") for i in range(20000)))
            if Path("/usr/bin/git").is_file():
                elf = Path("/usr/bin/git")
                cases["local/git-elf"] = elf
                packed_elf = generated / "git.xz"
                with packed_elf.open("wb") as stream:
                    subprocess.run(["xz", "-6", "-T1", "-c", elf], stdout=stream, check=True)
                cases["local/git-xz"] = packed_elf
            source = generated / "source.tar"
            with source.open("wb") as stream:
                subprocess.run(["git", "-C", REPO, "archive", "05a1c26662a15b10ce60cc56d568fb410051cfe0"],
                               stdout=stream, check=True)
            cases.update({f"generated/{p.name}": p for p in [random_file, numeric, database, source]})

            for dataset, path in cases.items():
                manifest[dataset] = {"bytes": path.stat().st_size, "sha256": hash_file(path)}
                print(dataset, flush=True)
                for rep in range(opts.repetitions):
                    tools = [
                        ("sadm", [sadm, "encode", archive, path], [sadm, "decode", archive, restored], False, False),
                        ("sedravarch", [stable, "pack-profile", "balanced", "1", path, archive],
                         [stable, "unpack", archive, restored], False, False),
                        ("zstd", ["zstd", "-3", "-T1", "-c", path], ["zstd", "-dc", archive], True, True),
                        ("brotli", ["brotli", "-q", "6", "-c", path], ["brotli", "-dc", archive], True, True),
                        ("gzip", ["gzip", "-6", "-nc", path], ["gzip", "-dc", archive], True, True),
                        ("lz4", ["lz4", "-1", "-c", path], ["lz4", "-dc", archive], True, True),
                        ("7zip", [opts.seven, "a", "-t7z", "-m0=LZMA2", "-mx=5", "-mmt=1", archive, path.name],
                         [opts.seven, "x", "-so", "-mmt=1", archive], False, True),
                    ]
                    for tool, enc, dec, es, ds in tools:
                        if opts.sadm_only and tool != "sadm":
                            continue
                        bench(dataset, path, tool, rep, enc, dec, archive, restored, es, ds, path.parent)
                if not opts.sadm_only and dataset in {"canterbury/alice29.txt", "generated/numeric.bin", "generated/random.bin",
                               "generated/records.sqlite", "local/git-elf"}:
                    for rep in range(opts.ablation_repetitions):
                        for name, flag in ablations:
                            bench(dataset, path, name, rep,
                                  [sadm, "encode", flag, archive, path],
                                  [sadm, "decode", archive, restored], archive, restored)

        family = root / "family"
        family.mkdir()
        if opts.family_directory:
            inputs = sorted(item for item in opts.family_directory.iterdir() if item.is_file())
            if len(inputs) != 3:
                parser.error("the family directory must contain three files")
            files = [family / item.name for item in inputs]
            for item, destination in zip(inputs, files):
                shutil.copyfile(item, destination)
        else:
            first = random.Random(917).randbytes(256 * 1024)
            moved = first[32768:65536] + first[:32768] + first[65536:]
            versions = [first, first, moved[:93881] + b"new" * 17 + moved[93909:]]
            files = []
            for index, data in enumerate(versions):
                file = family / f"v{index}"
                file.write_bytes(data)
                files.append(file)
        for file in files:
            os.utime(file, (946684800, 946684800))
            manifest[f"family/{file.name}"] = {"bytes": file.stat().st_size, "sha256": hash_file(file)}
        solid_input = root / "family.tar"
        with tarfile.open(solid_input, "w") as tar:
            for file in files:
                info = tar.gettarinfo(str(file), arcname=file.name)
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ""
                with file.open("rb") as stream:
                    tar.addfile(info, stream)
        manifest["family/tar"] = {"bytes": solid_input.stat().st_size, "sha256": hash_file(solid_input)}
        multi = []
        for rep in range(opts.repetitions):
            configurations = [
                ("sadm", [sadm, "encode", archive, *files], lambda i, _: [sadm, "extract", archive, str(i), restored], False),
                ("sedravarch-non-solid", [stable, "create-profile", "balanced", "1", archive, *files],
                 lambda _, f: [stable, "extract-file", archive, f.name, restored], False),
            ]
            for name, flag in ablations:
                if opts.sadm_only and name == "sadm-multiscale":
                    continue
                configurations.append((name, [sadm, "encode", flag, archive, *files],
                                       lambda i, _: [sadm, "extract", archive, str(i), restored], False))
            for solid in ["on", "off"]:
                configurations.append((f"7zip-solid-{solid}",
                    [opts.seven, "a", "-t7z", "-m0=LZMA2", "-mx=5", "-mmt=1", f"-ms={solid}", archive, *(p.name for p in files)],
                    lambda _, f: [opts.seven, "x", "-so", "-mmt=1", archive, f.name], True))
            for tool, enc, dec, stdout in configurations:
                if opts.sadm_only and not tool.startswith("sadm"):
                    continue
                pack = measured(enc, cwd=family)
                extract = []
                for i, file in enumerate(files):
                    extract.append(measured(dec(i, file), restored if stdout else None, family))
                    assert files_equal(file, restored)
                    restored.unlink()
                tags = json.loads(command([sadm, "stats", archive]))["tags"] if tool.startswith("sadm") else None
                multi.append({"tool": tool, "rep": rep, "archive_bytes": archive.stat().st_size,
                              "archive_sha256": hash_file(archive), "encode": pack, "extract": extract, "tags": tags})
                archive.unlink()

        versions = {tool: command(argv) for tool, argv in {
            "rustc": ["rustc", "-Vv"], "cc": ["cc", "--version"], "zstd": ["zstd", "--version"],
            "lz4": ["lz4", "--version"], "brotli": ["brotli", "--version"],
            "gzip": ["gzip", "--version"], "7zip": [opts.seven, "i"], "xz": ["xz", "--version"],
        }.items()}
        versions["7zip"] = versions["7zip"].splitlines()[0]
        cpu = next(line.split(":")[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                   if line.startswith("model name"))
        counts = {name: Path(f"/sys/fs/cgroup/{name}").read_text().strip()
                  for name in ["cpu.max", "memory.max"] if Path(f"/sys/fs/cgroup/{name}").exists()}
        sources = {}
        if not opts.only_family:
            sources = {"canterbury": command(["git", "-C", opts.canterbury, "rev-parse", "HEAD"]),
                       "silesia": command(["git", "-C", opts.silesia.parent / "silesia", "rev-parse", "HEAD"])}
        opts.out.write_text(json.dumps({"baseline": "05a1c26662a15b10ce60cc56d568fb410051cfe0",
            "environment": {"uname": platform.uname()._asdict(), "cpu_model": cpu,
                            "affinity_count": len(os.sched_getaffinity(0)), "cgroup": counts,
                            "python": platform.python_version(), "sqlite": sqlite3.sqlite_version},
            "versions": versions, "binaries_sha256": {"sadm": hash_file(sadm), "sedravarch": hash_file(stable)},
            "sources": sources,
            "inputs": manifest, "single_file": rows, "multifile": multi}, indent=2) + "\n")


if __name__ == "__main__":
    import sys
    run(sys.argv[1:])
