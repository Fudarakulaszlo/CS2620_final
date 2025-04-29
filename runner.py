"""
runner.py – orchestrator for the slot-synchronised consensus demo
-----------------------------------------------------------------

✔  generates or loads a topology  
✔  assigns free TCP ports  
✔  writes a *run-file* with the full runtime contract  
✔  spawns one **agent** process per node  
✔  tees every agent’s combined stdout/-err to <run_dir>/agent_<ID>.csv  
✔  exits cleanly (Ctrl-C OK) and prints log location

Run one machine / random graph example
--------------------------------------

    python runner.py --random 6 3 --algo wmsr --rounds 300 \
                     --slot 0.10 --holdoff 30 \
                     --init-min -1 --init-max 1 --seed 42
"""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
import subprocess as sp
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import yaml

import topo as topo_mod
from sync.timeslot import compute_t0

# ---------------------------------------------------------------------------#
# CLI                                                                         #
# ---------------------------------------------------------------------------#


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser("Distributed consensus runner")

    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--topo", help="Path to YAML topology")
    g.add_argument(
        "--random",
        nargs=2,
        metavar=("N", "AVG_DEG"),
        type=float,
        help="Generate random connected graph with N nodes, avg degree ≈ AVG_DEG",
    )

    p.add_argument("--algo", required=True, help="Algorithm registry key (e.g. wmsr)")
    p.add_argument("--rounds", type=int, default=50)
    p.add_argument("--slot", type=float, default=0.10, help="Slot width in seconds")
    p.add_argument(
        "--holdoff",
        type=int,
        default=30,
        help="Number of slots between now and t₀ (startup cushion)",
    )

    p.add_argument("--init-min", type=float, default=0.0)
    p.add_argument("--init-max", type=float, default=1.0)
    p.add_argument("--seed", type=int)

    p.add_argument("--eps", type=float, default=0.0)
    p.add_argument("--base-port", type=int, default=5500)
    p.add_argument(
        "--out",
        default=datetime.now().strftime("run_%Y%m%d-%H%M%S"),
        help="Output directory",
    )
    return p.parse_args(argv)


# ---------------------------------------------------------------------------#
# Helpers                                                                     #
# ---------------------------------------------------------------------------#


def pick_free_ports(start: int, n: int) -> List[int]:
    """Return *n* consecutive free TCP ports starting at ≥ *start*."""
    ports: List[int] = []
    cand = start
    while len(ports) < n:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("", cand))
                ports.append(cand)
            except OSError:
                pass  # busy
            cand += 1
    return ports


class Tee(threading.Thread):
    """
    Copy *src_fh* (bytes) to *dst_fh*.

    *dst_fh* may be an already-open file **or** a Path – in the latter case
    the file is opened in binary mode and closed automatically on exit.
    """

    def __init__(self, src_fh, dst_fh, mirror_console: bool = False):
        super().__init__(daemon=True)
        from pathlib import Path as _Path  # local import to avoid early cost

        self.src = src_fh
        if isinstance(dst_fh, _Path):
            self.dst = dst_fh.open("wb")
            self._close_dst = True
        else:
            self.dst = dst_fh
            self._close_dst = False

        self.echo = mirror_console
        self._halt_evt = threading.Event()

    def run(self) -> None:  # noqa: D401
        while not self._halt_evt.is_set():
            line = self.src.readline()
            if not line:
                break  # stream closed
            self.dst.write(line)
            self.dst.flush()
            if self.echo:
                sys.stdout.write(line.decode(errors="replace"))
        if self._close_dst:
            self.dst.close()

    def stop(self) -> None:  # noqa: D401
        self._halt_evt.set()
        self.join(timeout=2.0)


# ---------------------------------------------------------------------------#
# Main                                                                        #
# ---------------------------------------------------------------------------#


def main(opts: argparse.Namespace) -> None:  # noqa: D401
    out_dir = Path(opts.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=False)

    # 1 · Topology --------------------------------------------------------
    if opts.topo:
        topo = topo_mod.load_yaml(opts.topo)
    else:
        n = int(opts.random[0])
        avg_deg = float(opts.random[1])
        topo = topo_mod.random_connected(n, avg_deg, seed=opts.seed)
        (out_dir / "topo.yaml").write_text(
            yaml.safe_dump(
                {"agents": list(topo.agents), "edges": [list(e) for e in topo.edges]}
            ),
            encoding="utf-8",
        )

    # 2 · Per-agent initial values ---------------------------------------
    rng = random.Random(opts.seed)
    init_vals = {
        aid: rng.uniform(opts.init_min, opts.init_max) for aid in topo.agents
    }

    # 3 · Ports -----------------------------------------------------------
    ports = pick_free_ports(opts.base_port, len(topo.agents))
    aid2port = dict(zip(topo.agents, ports))

    # 4 · Run-file --------------------------------------------------------
    t0 = compute_t0(opts.slot, opts.holdoff)
    runfile = {
        "slot_sec": opts.slot,
        "t0_epoch_ms": int(t0 * 1000),
        "rounds": opts.rounds,
        "agents": {
            aid: {
                "pub": aid2port[aid],
                "host": "127.0.0.1",
                "neigh": topo.neighbour_map[aid],
                "initial": init_vals[aid],
            }
            for aid in topo.agents
        },
        "algorithm": {"name": opts.algo, "params": {}},
        "initial_range": [opts.init_min, opts.init_max],
        "seed": opts.seed,
    }
    runfile_path = out_dir / "runfile.json"
    runfile_path.write_text(json.dumps(runfile, indent=2), encoding="utf-8")

    # 5 · Spawn agents ----------------------------------------------------
    tees: List[Tee] = []
    procs: Dict[str, sp.Popen] = {}

    agent_script = Path(__file__).parent / "core" / "agent.py"

    root_dir = Path(__file__).resolve().parent
    base_env = os.environ.copy()
    base_env["PYTHONPATH"] = f"{root_dir}:{base_env.get('PYTHONPATH', '')}"

    for aid in topo.agents:
        log_path = out_dir / f"agent_{aid}.csv"

        proc_env = base_env.copy()
        p = sp.Popen(
            [
                sys.executable,
                str(agent_script),
                "--id",
                aid,
                "--runfile",
                str(runfile_path),
                "--algo",
                opts.algo,
                "--initial",
                str(init_vals[aid]),
                "--eps",
                str(opts.eps),
            ],
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
            env=proc_env,
        )

        procs[aid] = p
        tee = Tee(p.stdout, log_path)  # Path is fine – Tee will open it
        tee.start()
        tees.append(tee)

    print(
        f"[runner] t₀ in {opts.holdoff * opts.slot:.2f}s – "
        f"{len(procs)} agents running"
    )

    # 6 · Monitor ---------------------------------------------------------
    try:
        while procs:
            for aid, proc in list(procs.items()):
                if proc.poll() is not None:
                    print(f"[runner] {aid} exited (code {proc.returncode})")
                    procs.pop(aid)
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("[runner] ^C – terminating …")
        for proc in procs.values():
            proc.terminate()
    finally:
        for tee in tees:
            tee.stop()

    print(f"[runner] logs in {out_dir}")


if __name__ == "__main__":
    try:
        main(parse_args())
    except Exception as exc:
        sys.stderr.write(f"runner fatal error: {exc}\n")
        sys.exit(1)
