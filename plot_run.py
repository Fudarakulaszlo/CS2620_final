#!/usr/bin/env python3
"""
plot_run.py – visualise consensus trajectories for one run directory

Usage
-----
basic interactive window
    python plot_run.py /path/to/run_20250429-154210

save figure to PNG (still shows window unless --no-show)
    python plot_run.py run_dir -o traj.png

suppress on-screen window (for CI or headless servers)
    python plot_run.py run_dir -o traj.png --no-show
"""
from __future__ import annotations

import argparse
import glob
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt


def load_csv(path: Path) -> Tuple[List[int], List[float]]:
    rounds: List[int] = []
    values: List[float] = []
    with path.open("rt", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            k_str, v_str = line.strip().split(",")
            rounds.append(int(k_str))
            values.append(float(v_str))
    return rounds, values


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser("Plot consensus trajectories")
    p.add_argument("run_dir", help="Runner output directory (contains agent_*.csv)")
    p.add_argument("-o", "--out", help="Optional PNG path to save the figure")
    p.add_argument("--no-show", action="store_true", help="Do not pop up a GUI window")
    return p.parse_args()


def main() -> None:
    opts = parse_args()
    run_dir = Path(opts.run_dir)

    csv_paths = sorted(run_dir.glob("agent_*.csv"))
    if not csv_paths:
        raise SystemExit(f"No agent_*.csv files found in {run_dir}")

    fig, ax = plt.subplots()
    ax.set_xlabel("Round")
    ax.set_ylabel("Value")
    ax.set_title(f"Consensus trajectories – {run_dir.name}")

    for csv in csv_paths:
        aid = csv.stem.split("_", 1)[1]  # agent_<ID>.csv → <ID>
        k, v = load_csv(csv)
        ax.plot(k, v, label=aid)

    ax.legend(title="Agent")
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)

    fig.tight_layout()

    if opts.out:
        plt.savefig(opts.out, dpi=150, bbox_inches="tight")
        print(f"[plot_run] saved → {opts.out}")

    if not opts.no_show:
        plt.show()
    else:
        plt.close(fig)


if __name__ == "__main__":
    main()
