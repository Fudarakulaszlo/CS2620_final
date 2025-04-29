"""core/agent.py – deterministic sender IDs (CRC‑32)

Fix for the **empty inbox** problem: Python’s built‑in `hash()` is salted
per process, so the 4‑byte sender IDs we embedded in each message didn’t
match across agents.  Consequently every receiver discarded incoming
packets as “unknown sender”, and the algorithm never updated.

We now use **`zlib.crc32(id.encode())`** instead of `hash(id)` so the
value is stable across all processes and runs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, MutableMapping
import importlib
import struct
import zlib  # NEW – deterministic 32‑bit hash

from comm.zmq_transport import ZmqTransport, build_endpoint
from core.algorithm import Algorithm, get_algorithm
from sync.timeslot import SlotConfig, wait_for_round_start

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: List[str] | None = None) -> argparse.Namespace:  # noqa: D401
    p = argparse.ArgumentParser(description="Distributed consensus agent")
    p.add_argument("--id", required=True)
    p.add_argument("--runfile", required=True)
    p.add_argument("--algo", required=True)
    p.add_argument("--eps", type=float, default=0.0)
    p.add_argument("--initial", type=float, default=0.0)
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_runfile(path: Path) -> Dict:
    with path.open("rt", encoding="utf-8") as fh:
        return json.load(fh)


def crc32_id(aid: str) -> int:
    """Stable 32‑bit ID for *aid* (same across processes)."""
    return zlib.crc32(aid.encode()) & 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_agent(opts: argparse.Namespace) -> None:
    cfg = load_runfile(Path(opts.runfile))

    slot_cfg = SlotConfig(cfg["slot_sec"], cfg["t0_epoch_ms"] / 1000)
    rounds: int = cfg["rounds"]

    agents_cfg = cfg["agents"]
    my_cfg = agents_cfg[opts.id]

    neigh_ids = my_cfg["neigh"]
    neigh_endpoints = [
        build_endpoint(agents_cfg[n]["host"], agents_cfg[n]["pub"]) for n in neigh_ids
    ]
    transport = ZmqTransport(pub_port=my_cfg["pub"], neigh_endpoints=neigh_endpoints)

    # dynamic plugin load --------------------------------------------------
    importlib.import_module(f"algorithms.{opts.algo}")
    AlgoCls = get_algorithm(opts.algo)
    alg: Algorithm = AlgoCls()
    alg.initialise(
        agent_id=opts.id,
        initial_value=opts.initial,
        neighbours=neigh_ids,
        params=cfg.get("algorithm", {}).get("params", {}),
    )
    value = opts.initial

    my_crc = crc32_id(opts.id)

    csv_out = sys.stdout
    eps = opts.eps

    for k in range(rounds):
        wait_for_round_start(slot_cfg, k)

        # --- broadcast ----------------------------------------------------
        header = my_crc.to_bytes(4, "big") + k.to_bytes(4, "big")
        transport.send(header + struct.pack("!d", value))

        # --- gather -------------------------------------------------------
        inbox: MutableMapping[str, float] = {}
        deadline = slot_cfg.deadline(k)
        while time.time() < deadline:
            raw = transport.recv_nowait()
            if not raw or len(raw) != 16:
                time.sleep(0.00005)
                continue
            src_crc = int.from_bytes(raw[0:4], "big")
            if int.from_bytes(raw[4:8], "big") != k:
                continue
            src_id = _crc_lookup(src_crc, agents_cfg)
            if not src_id:
                continue
            inbox[src_id] = struct.unpack("!d", raw[8:16])[0]

        value = alg.step(k, inbox)
        csv_out.write(f"{k},{value}\n")
        csv_out.flush()
        if eps > 0 and alg.converged(eps=eps):
            csv_out.write(f"# converged {k}\n"); csv_out.flush(); break

    transport.close()


# ---------------------------------------------------------------------------
# CRC reverse lookup (tiny N → linear scan)
# ---------------------------------------------------------------------------

def _crc_lookup(crc: int, agents_cfg: Dict[str, Dict]) -> str | None:
    for aid in agents_cfg:
        if crc32_id(aid) == crc:
            return aid
    return None


if __name__ == "__main__":
    run_agent(parse_args())
