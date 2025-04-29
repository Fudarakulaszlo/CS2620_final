"""algorithms/wmsr.py

Weighted Mean‑Subsequence Reduced (W‑MSR) consensus algorithm
------------------------------------------------------------

Implements the synchronous *F‑local malicious model* variant commonly used
in resilient consensus literature (LeBlanc et al., 2013).  At every round
an agent:

1. Receives one scalar value from each neighbour
2. Discards up to *F* of the **largest** values that exceed its own current
   value, and up to *F* of the **smallest** values that are below it
3. Updates to the arithmetic mean of the remaining values **plus its own**
   current value

Parameters (supplied in the YAML run‑file)::

    algorithm:
      name: wmsr
      params:
        F: 1        # (non‑negative int) maximum number of malicious
                    # neighbours per agent the network design tolerates

Convergence predicate
~~~~~~~~~~~~~~~~~~~~
An agent reports *converged* when the absolute change in its local value
falls below ``eps`` (runner CLI ``--eps``).  The runner terminates the
whole experiment once **all** agents satisfy this predicate or the fixed
round limit is reached.
"""

from __future__ import annotations

import math
from typing import Iterable, Mapping, MutableMapping

from core.algorithm import Algorithm, register_algorithm

__all__ = ["WMSR"]


@register_algorithm("wmsr")  # registers class under key 'wmsr'
class WMSR(Algorithm):
    """Python reference implementation of scalar W‑MSR."""

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def initialise(
        self,
        *,
        agent_id: str,
        initial_value: float,
        neighbours: Iterable[str],
        params: Mapping[str, float] | None = None,
    ) -> None:  # noqa: D401 – override
        self.id = agent_id
        self._value = float(initial_value)
        self._neigh = list(neighbours)
        # Number of malicious neighbours tolerated
        self._F = int(params.get("F", 0) if params else 0)
        if self._F < 0:
            raise ValueError("F must be ≥ 0")
        self._delta = math.inf  # change magnitude from last step

    # ------------------------------------------------------------------
    # Core update
    # ------------------------------------------------------------------

    def step(self, round_no: int, inbox: MutableMapping[str, float]) -> float:  # noqa: D401 – override
        """Perform one W‑MSR update and return next value to broadcast."""

        current = self._value
        neighbour_vals = list(inbox.values())

        # Partition neighbour values relative to current value
        lower = sorted(v for v in neighbour_vals if v < current)
        higher = sorted((v for v in neighbour_vals if v > current), reverse=True)

        # Drop up to F extreme values on each side
        pruned = neighbour_vals.copy()
        for v in lower[: self._F]:
            pruned.remove(v)
        for v in higher[: self._F]:
            pruned.remove(v)

        # Include own value in the averaging set
        pruned.append(current)

        # Resilient average (uniform weights)
        next_val = sum(pruned) / len(pruned)

        # Track convergence metric
        self._delta = abs(next_val - current)
        self._value = next_val
        return next_val

    # ------------------------------------------------------------------
    # Convergence helper
    # ------------------------------------------------------------------

    def converged(self, *, eps: float) -> bool:  # noqa: D401 – override
        return self._delta <= eps
