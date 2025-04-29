"""core/algorithm.py

Abstract interface and registry for consensus algorithms that plug into
*distributed_consensus* agents.

The **only** contract with the communication layer is:

* One call to :py:meth:`Algorithm.initialise` before round 0 to let the
  implementation cache static metadata (ID, initial value, parameters).  It
  *MUST NOT* perform network IO.
* One call to :py:meth:`Algorithm.step` at the end of every round with the
  accumulated inbox of neighbour values for that round.  The method must
  return the *value to broadcast in the **next** round*.

Anything beyond that (state storage, convergence heuristics, logging) is
up to the concrete algorithm subclass.

The small **registry** at the end makes CLI lookup easy::

    # runner.py
    AlgorithmCls = get_algorithm("wmsr")
    algo = AlgorithmCls()

Algorithms register themselves via the :pyfunc:`@register_algorithm`
decorator.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import Dict, Iterable, List, Mapping, MutableMapping, Type

__all__ = [
    "Algorithm",
    "register_algorithm",
    "get_algorithm",
    "list_algorithms",
]

# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class Algorithm(ABC):
    """Abstract base for all consensus algorithms.

    Subclasses **must** override :py:meth:`initialise` and
    :py:meth:`step`.  Any additional attributes are entirely at the
    algorithm designer’s discretion.
    """

    # Public ----------------------------------------------------------------

    @abstractmethod
    def initialise(
        self,
        *,
        agent_id: str,
        initial_value: float,
        neighbours: Iterable[str],
        params: Mapping[str, float] | None = None,
    ) -> None:
        """Called exactly once, right before round 0 starts.

        Parameters
        ----------
        agent_id
            External identifier of *this* agent (human‑readable).
        initial_value
            The value the agent should broadcast in round 0.
        neighbours
            Immutable list of neighbour IDs (order arbitrary).  The
            algorithm may *ignore* it if the theoretical model forbids
            topology knowledge.
        params
            Optional algorithm‑specific parameters from the topology YAML
            (e.g. ``F`` for W‑MSR).
        """

    @abstractmethod
    def step(self, round_no: int, inbox: MutableMapping[str, float]) -> float:  # noqa: D401
        """Compute and *return* the value to broadcast in round \*round_no + 1\*.

        ``inbox`` contains **all messages that arrived during this
        agent’s time‑slot for *round \*round_no\***.  Keys are
        neighbour IDs, values are the neighbour’s payload (usually a float).
        The implementation **must not mutate** the mapping outside its own
        call frame.
        """

    # Optional --------------------------------------------------------------

    def converged(self, *, eps: float) -> bool:  # noqa: D401 – simple predicate
        """Return **True** if the algorithm considers itself at equilibrium.

        Default fallback just returns **False** (never converged).  Agents
        are free to terminate the run when *all* local algorithms converge
        or when the orchestrator’s fixed round limit is hit – whichever
        comes first.
        """

        return False


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

_algorithms: Dict[str, Type[Algorithm]] = {}


def register_algorithm(name: str):  # noqa: D401 – decorator factory
    """Decorator to register *cls* under ``name``.

    Example
    -------
    >>> @register_algorithm("dummy")
    ... class Dummy(Algorithm):
    ...     ...  # doctest: +SKIP
    """

    def decorator(cls: Type[Algorithm]):
        if not inspect.isclass(cls) or not issubclass(cls, Algorithm):
            raise TypeError("@register_algorithm expects an Algorithm subclass")
        if name in _algorithms:
            raise KeyError(f"Algorithm name '{name}' already registered")
        _algorithms[name] = cls
        cls.__algo_name__ = name  # type: ignore[attr-defined]
        return cls

    return decorator


def get_algorithm(name: str) -> Type[Algorithm]:
    """Look up an algorithm class by ``name``.

    Raises ``KeyError`` if the name is unknown.
    """

    return _algorithms[name]


def list_algorithms() -> List[str]:
    """Return all registered algorithm names (sorted)."""

    return sorted(_algorithms.keys())
