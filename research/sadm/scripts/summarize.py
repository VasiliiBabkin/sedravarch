#!/usr/bin/env python3
"""Aggregate verified raw rows and compute a 3D Pareto frontier per suite."""
from collections import defaultdict
import json
import statistics
import sys


def median(rows, *fields):
    values = []
    for row in rows:
        value = row
        for field in fields:
            value = value[field]
        values.append(value)
    return statistics.median(values)


def frontier(table):
    values = {name: (row["archive_bytes"], row["encode_wall_s"], row["encode_peak_kib"])
              for name, row in table.items()}
    return sorted(name for name, current in values.items()
                  if not any(other != current and all(a <= b for a, b in zip(other, current))
                             for other in values.values()))


def main():
    raw = json.load(open(sys.argv[1], encoding="utf-8"))
    grouped = defaultdict(lambda: defaultdict(list))
    for row in raw["single_file"]:
        grouped[row["tool"]][row["dataset"]].append(row)
    suites = {}
    base = {name for name in grouped if not name.startswith("sadm-no-")}
    for prefix in ("canterbury", "silesia", "generated", "local"):
        table = {}
        paths = [path for path in raw["inputs"] if path.startswith(prefix + "/")]
        length = sum(raw["inputs"][path]["bytes"] for path in paths)
        for tool in sorted(base):
            cases = [grouped[tool][path] for path in paths]
            size = int(sum(median(rows, "archive_bytes") for rows in cases))
            row = {"input_bytes": length, "archive_bytes": size, "ratio": size / length}
            for operation in ("encode", "decode"):
                wall = sum(median(rows, operation, "wall_s") for rows in cases)
                cpu = sum(statistics.median(r[operation]["user_s"] + r[operation]["system_s"]
                                            for r in rows) for rows in cases)
                peak = max(r[operation]["peak_rss_kib"] for rows in cases for r in rows)
                row.update({f"{operation}_wall_s": wall, f"{operation}_cpu_s": cpu,
                            f"{operation}_peak_kib": peak, f"{operation}_mib_s": length / (wall * 2**20)})
            table[tool] = row
        suites[prefix] = {"tools": table, "encode_pareto": frontier(table)}

    multi = defaultdict(list)
    for row in raw["multifile"]:
        multi[row["tool"]].append(row)
    family = {}
    for tool, rows in sorted(multi.items()):
        family[tool] = {
            "archive_bytes": int(median(rows, "archive_bytes")),
            "encode_wall_s": median(rows, "encode", "wall_s"),
            "encode_peak_kib": max(r["encode"]["peak_rss_kib"] for r in rows),
            "extract_median_s": [median(rows, "extract", i, "wall_s") for i in range(3)],
            "extract_peak_kib": [max(r["extract"][i]["peak_rss_kib"] for r in rows) for i in range(3)],
        }
    ablation = {}
    for tool, datasets in sorted(grouped.items()):
        if tool.startswith("sadm-no-"):
            ablation[tool] = {
                path: {"bytes_delta": int(median(rows, "archive_bytes") - median(grouped["sadm"][path], "archive_bytes")),
                       "encode_speedup": median(grouped["sadm"][path], "encode", "wall_s") / median(rows, "encode", "wall_s")}
                for path, rows in datasets.items()
            }
    print(json.dumps({"suites": suites, "family": family, "family_pareto": frontier(family),
                      "single_file_ablation": ablation}, indent=2))


if __name__ == "__main__":
    main()
