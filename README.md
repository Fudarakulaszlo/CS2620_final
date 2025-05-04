# Distributed Consensus Demo (Time‐Slot, ZeroMQ, W‑MSR)

This repository is a **minimal, pluggable framework** for experimenting with
distributed consensus algorithms on one machine, one **agent = process**
per node.

* Transport   : **ZeroMQ PUB/SUB** (one socket pair per agent)  
* Sync model  : **Fixed time‑slots** (`slot_sec`) with a global `t₀`  
* Baseline    : **W‑MSR** (max‐F resilient) implementation in `algorithms/wmsr.py`

```
distributed_consensus/
├─ runner.py           # orchestrator CLI
├─ plot_run.py         # visualise trajectories
├─ topo.py             # load / generate graphs
├─ comm/zmq_transport.py
├─ sync/timeslot.py
├─ core/
│   ├─ agent.py
│   └─ algorithm.py
└─ algorithms/wmsr.py
```

---

## Quick start

```bash
# 1. Install deps (ZeroMQ + matplotlib + YAML)
pip install pyzmq matplotlib pyyaml

# 2. Run 8‑node random graph (avg degree 3), 300 rounds
python runner.py --random 8 5 --algo wmsr                  --slot 0.10 --holdoff 50                  --rounds 50 --seed 1                  --init-min -1 --init-max 1                  --F 1          # <── max faulty neighbours
```

The runner prints progress and writes:

```
run_YYYYMMDD-HHMMSS/
    runfile.json     # frozen runtime contract
    topo.yaml        # actual graph (if --random)
    agent_A0.csv     # “round,value” per agent
    …
```

Plot trajectories:

```bash
python plot_run.py run_YYYYMMDD-HHMMSS -o traj.png
```

---

## Runner CLI

| Flag | Meaning | Default |
|------|---------|---------|
| `--topo FILE` / `--random N D` | load YAML or build random connected graph | — |
| `--algo NAME` | algorithm plugin (registry key) | — |
| `--rounds K` | fixed run length | 50 |
| `--slot SEC` | slot width (global time units) | 0.10 |
| `--holdoff N` | slots between now and `t₀` (startup cushion) | 30 |
| `--init-min, --init-max` | per‑agent random initial values | 0.0 … 1.0 |
| `--seed S` | RNG seed (topology + initials) | none |
| `--F` | W‑MSR: max faulty neighbours | 1 |
| `--eps` | early‑stop tolerance (`0` = disabled) | 0 |
| `--base-port` | first TCP port to probe | 5500 |

---

## How **F** for W-MSR is wired

```
runner.py  --F 2
   └── runfile.json
         "algorithm": { "name": "wmsr",
                        "params": { "F": 2 } }
              └── agent.py
                     └── wmsr.initialise(params)
```

If you omit `--F`, the plugin defaults to `F = 0`.

---

## Extending

* **New algorithm:** drop `foo.py` in `algorithms/`, decorate a subclass with
  `@register_algorithm("foo")`.
* **Different transport:** implement `Transport` interface in `comm/`.
* **Multi‑host:** replace `host:127.0.0.1` in `runfile.json` with real IPs,
  start agents via SSH, keep the same run‐file.

