#!/usr/bin/env python3
"""Render the measured three-metric frontier on two 2D projections with RSS color."""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize


def main():
    with open(sys.argv[1], encoding="utf-8") as source:
        suites = json.load(source)["suites"]
    names = ["canterbury", "silesia"]
    memory = [row["encode_peak_kib"] / 1024 for name in names for row in suites[name]["tools"].values()]
    norm = Normalize(min(memory), max(memory))
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
    for ax, name in zip(axes, names):
        suite = suites[name]
        for tool, row in suite["tools"].items():
            selected = tool in suite["encode_pareto"]
            x, y = row["encode_mib_s"], 100 * row["ratio"]
            dots = ax.scatter([x], [y], c=[row["encode_peak_kib"] / 1024],
                              cmap="viridis", norm=norm, s=70, marker="D" if selected else "o",
                              edgecolors="#17293d", linewidths=0.6)
            ax.annotate(tool, (x, y), xytext=(5, 5), textcoords="offset points", fontsize=8)
        ax.set(xscale="log", title=name.title(), xlabel="Encode throughput (MiB/s)",
               ylabel="Archive size (% of input)")
        ax.margins(x=0.18, y=0.14)
        ax.grid(alpha=0.25)
    fig.colorbar(dots, ax=axes, label="Peak encode RSS (MiB)")
    fig.suptitle("Measured codec settings · diamonds mark the three-metric Pareto frontier")
    fig.savefig(sys.argv[2], dpi=150)


if __name__ == "__main__":
    main()
