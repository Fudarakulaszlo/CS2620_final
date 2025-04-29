"""topo.py

Utilities for loading or generating network topologies for
*distributed_consensus* runs.

The **canonical interchange format** is a YAML file that lists agents and
an (undirected) edge list.  Example::

    agents: [A, B, C, D]
    edges:
      - [A, B]
      - [B, C]
      - [C, D]
      - [D, A]

If you omit the ``agents`` key the loader infers the agent set from the
edge list.  Self‑loops are rejected; duplicate edges are collapsed.

The helper :func:`random_connected` can create a random connected graph
(with probability 1) of given order and expected average degree – useful
for quick benches without hand‑crafting YAML.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple

import yaml

__all__ = [
    "Topology",
    "load_yaml",
    "random_connected",
]


@dataclass(slots=True, frozen=True)
class Topology:
    """In‑memory topology (undirected)."""

    agents: Tuple[str, ...]
    edges: Tuple[Tuple[str, str], ...]  # canonicalised (low, high)

    # ---------------------------------------------------------
    # Convenience views
    # ---------------------------------------------------------

    @property
    def neighbour_map(self) -> Dict[str, List[str]]:
        """Return ``id → [neighbours]`` mapping (order arbitrary)."""
        neigh: Dict[str, List[str]] = {a: [] for a in self.agents}
        for a, b in self.edges:
            neigh[a].append(b)
            neigh[b].append(a)
        return neigh


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------


def load_yaml(path: str | Path) -> Topology:
    """Parse YAML topology file → :class:`Topology`."""

    with Path(path).open("rt", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict):
        raise ValueError("Top-level YAML must map keys → values")

    agents: List[str] = list(data.get("agents", []))
    edges_raw: Sequence[Sequence[str]] = data.get("edges", [])

    # Infer agents from edges if not explicitly listed
    if not agents:
        s: Set[str] = set()
        for u, v in edges_raw:
            s.add(u)
            s.add(v)
        agents = sorted(s)

    # Validate -------------------------------------------------------------
    if len(set(agents)) != len(agents):
        raise ValueError("Duplicate agent IDs in 'agents' list")

    agents_set = set(agents)
    edges: Set[Tuple[str, str]] = set()
    for pair in edges_raw:
        if len(pair) != 2:
            raise ValueError(f"Malformed edge entry: {pair}")
        u, v = pair
        if u == v:
            raise ValueError("Self-loops are not allowed")
        if u not in agents_set or v not in agents_set:
            raise ValueError(f"Edge references unknown agent: {pair}")
        # canonicalise ordering to dedupe
        edges.add(tuple(sorted((u, v))))

    return Topology(tuple(agents), tuple(sorted(edges)))


# ---------------------------------------------------------------------------
# Random generator (Erdős–Rényi + ensure connectivity)
# ---------------------------------------------------------------------------


def random_connected(n: int, avg_degree: float, *, seed: int | None = None) -> Topology:
    """Generate a *connected* random undirected graph with ~avg_degree.

    We pick edge probability *p* such that expected degree = *avg_degree*,
    then keep sampling until the produced graph is connected (with *p* ≥
    ln(n)/n that converges quickly).  Suitable for **small n** (≤ 1000).
    """

    if n < 2:
        raise ValueError("Need at least 2 agents")
    if avg_degree <= 0:
        raise ValueError("avg_degree must be > 0")

    rng = random.Random(seed)
    agents = tuple(f"A{i}" for i in range(n))

    # Edge probability for given expected degree
    p = min(max(avg_degree / (n - 1), 0.0), 1.0)

    while True:
        edges: Set[Tuple[str, str]] = set()
        for i in range(n):
            for j in range(i + 1, n):
                if rng.random() < p:
                    edges.add((agents[i], agents[j]))

        topo = Topology(agents, tuple(sorted(edges)))
        if _is_connected(topo):
            return topo


# ---------------------------------------------------------------------------
# Connectivity helper
# ---------------------------------------------------------------------------


def _is_connected(topo: Topology) -> bool:  # simple BFS
    if not topo.agents:
        return True
    neigh = topo.neighbour_map
    seen: Set[str] = set()
    frontier = [topo.agents[0]]
    while frontier:
        u = frontier.pop()
        if u in seen:
            continue
        seen.add(u)
        frontier.extend(neigh[u])
    return len(seen) == len(topo.agents)
