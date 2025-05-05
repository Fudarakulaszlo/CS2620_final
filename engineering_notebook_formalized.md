# Distributed Consensus Framework – Engineering Notebook  
*CS 2620 Final Project*  
Karen Li & Áron Vékássy
May 2025

---

## 0 · Table of Contents
1. Motivation & Problem Statement  
2. Guiding Constraints  
3. Architecture Overview  
4. Communication Layer  
5. Time‑Slot Synchronisation  
6. Algorithm Plug‑in Layer  
7. Orchestrator & Experiment Workflow  
8. Instrumentation & Visualisation  
9. Lessons Learned  
10. Future Work  

---

## 1 · Motivation & Problem Statement
Consensus algorithms such as **W‑MSR** guarantee resilient agreement in
the presence of up to _F_ faulty agents *if* their synchrony assumptions
hold.  Most textbooks stop at pseudocode—what we wanted was a **drop‑in
framework** that lets us iterate on algorithms, vary topologies, and run
hundreds of simulations *without touching the transport code every time*.

These algorithms differ from the traditional ones that we covered in class,
since agents cannot rely on their knowledge of the topology, like they can 
in the Byzantine generals problem. In robotics contexts, robots can't
know the topology in the network they are in, since it is usally a wireless
network that yields a time-varying topology due to frequent message drops and
the robots moving around.

Key goals:

* Pure **Python**, runs on one laptop first, scales to multiple hosts
  later, communication will be swapped to ROS2
* **Broadcast semantics** (agents don’t know their neighbourhood in
  algorithm logic).  
* **Pluggable**: swap W‑MSR for Metropolis, Median or Push‑Sum with two lines.  
* **Reproducibility**: topology + parameters captured in a single
  `runfile.json`.  
* Built‑in **visualisation** and **unit tests** so regressions surface
  early.

---

## 2 · Guiding Constraints
| Constraint | Design Impact |
|------------|---------------|
| Single machine for v1 | No real packet loss → start with TCP on localhost. |
| Agents *cannot* rely on topology knowledge | Orchestrator filters PUB/SUB connections so only neighbours’ messages arrive. |
| Deterministic “round” semantics | Introduced a **time‑slot barrier** instead of per‑message ACKs. |
| Fault-tolerance parameter _F_ must be tunable | Passed through `algorithm.params` in the run‑file; exposed as `--F` flag. |
| Minimal external deps | Added only `pyzmq`, `pyyaml`, `matplotlib`, `pytest`. |

---

## 3 · Architecture Overview
```
 runner.py      topo.py         core/agent.py         algorithms/
    │              │                   │                    │
    │  YAML / rnd   │                  │<─── registry ──────┤
    ├──── spawn ───▶│    SlotConfig    │ plug‑in step()     │
    │               │      ▲           │                    │
    │               │      │           │          comm/zmq_transport.py
    │               │   sync.timeslot  │                   ▲
    │<── CSV logs ──┤                  PUB/SUB           ZeroMQ
```

* **runner** writes the run‑file, spawns agents, tees logs.  
* **agent** binds one PUB and one SUB, loops over time‑slots.  
* **algorithm plug‑in** sees only `inbox: {id→value}`.  
* **transport** hides ZeroMQ specifics; can be replaced later.

---

## 4 · Communication Layer
We wrapped **ZeroMQ PUB/SUB** in `comm/zmq_transport.ZmqTransport`.

### Why ZeroMQ?
* “Radio” pattern matches broadcast.
* In‑proc, IPC, TCP all share the same API → painless unit tests.
* Built‑in subscription filter

### Message Format
```
[ src_id_crc32 | round_no | payload_float64 ]  = 16 bytes
```
CRC‑32 gives constant‑time sender lookup while keeping frames small.

---

## 5 · Time‑Slot Synchronisation
Textbook consensus assumes rounds advance only after *all* neighbour
messages arrive.  A naive barrier server works—but is a single point of
failure. We chose **time‑slots**:

```text
slot_sec = 0.10
t0       = now + holdoff·slot
window_k = [t0 + k·slot , t0 + (k+1)·slot)
```

* Agents broadcast once per window, buffer everything until `deadline(k)`.
* Progress is guaranteed even if a message is lost.
* One magic number (`slot_sec`) controls throughput vs. loss tolerance.

Edge‑case maths lives in `sync.timeslot.SlotConfig` and is fuzz‑tested.

This setup is not completely unrealistic, since robots often have access to GPS clocks.
We leave the time slot length tunable, to account for heterogeneous robot teams,
or communication delays.

---

## 6 · Algorithm Plug‑in Layer
```python
class Algorithm(ABC):
    def initialise(self, *, agent_id, initial_value, neighbours, params): ...
    def step(self, round_no, inbox: dict[str,float]) -> float: ...
    def converged(self, eps: float) -> bool:                ...
```

Registration via decorator:

```python
@register_algorithm("wmsr")
class WMSR(Algorithm):
    ...
```

### W‑MSR Highlights
* Keeps own value, prunes _F_ highs & lows from `inbox`.
* Step is `mean( kept_values )`.
* Unit‑tested for _F_ = 0, 1, 2.

---

## 7 · Orchestrator & Workflow
```bash
# 8‑node, avg deg ≈3, slot 100 ms, F = 2
python runner.py --random 8 3 --algo wmsr \
                 --slot 0.10 --holdoff 60 \
                 --rounds 500 --F 2 --seed 7
```

Runner duties:

1. Build / load topology (`topo.py`).  
2. Choose contiguous free ports.  
3. Assign per‑agent random initial values `[init_min, init_max]`.  
4. Write `runfile.json`.  
5. Spawn `core/agent.py` once per node.  
6. Tee each agent’s stdout→`agent_<ID>.csv`.  
7. Graceful shutdown on Ctrl‑C.

The run‑file and logs make experiments reproducible.

---

## 8 · Instrumentation & Visualisation
* `plot_run.py` renders trajectories from CSV in one command.  
* Slots/second and bandwidth stats recorded in each agent’s stdout.  
* `pytest` suite covers basic unit tests for timing maths, registry, W‑MSR logic, ZeroMQ echo, and
  topology generator.

---

## 9 · Lessons Learned
* The biggest debugging pain was **process startup latency**: import time
  can make agents miss the first few slots; Increasing `--holdoff` solved it.
  First it was set to 3 seconds, turns out that is still too little to spawn 3 processes.
* There was a lot of fiddling around with synchronization. Not really sure if this can
  be done nicely without having access to synchronized clocks, since the algo is synchronized
  and most clock sync methods can't deal with malicious agents.

---

## 10 · Future Work
| Idea | Benefit |
|------|---------|
| ROS2 multicast transport | Can be deployed on robots and run physical experiments |
| Multiple algorithms in one run | Compare Median vs W‑MSR on identical topology. |
| Fault injection layer | Drop / delay messages to empirically validate _F_-resilience. |

---
