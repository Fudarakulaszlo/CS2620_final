"""sync/timeslot.py

Slot‑based global synchronisation utilities.

This module is completely stateless; everything a caller needs is the
immutable :class:`SlotConfig` value object plus a couple of helper
functions.  The goal is to keep **all** timing logic in one place so that
changing the slot width or the start time requires _zero_ edits elsewhere
in the code base.

Usage example (agent side)  ────────────────────────────────────────────
>>> cfg = SlotConfig(slot_sec=0.10, t0_epoch=compute_t0(0.10, 3))
>>> for k in range(K):
...     wait_for_round_start(cfg, k)
...     broadcast(my_value)
...     harvest_‑msgs_until(cfg.deadline(k))
...     my_value = step(k, inbox)

All sleeps spin‑wait down to the sub‑millisecond range for good
slot‑boundary accuracy while still yielding to the OS most of the time.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Tuple

__all__ = [
    "SlotConfig",
    "compute_t0",
    "sleep_until",
    "wait_for_round_start",
]


@dataclass(frozen=True, slots=True)
class SlotConfig:
    """Immutable configuration for time‑slot synchronisation."""

    slot_sec: float  #: Width of a slot in **seconds** (e.g. ``0.10`` for 100 ms)
    t0_epoch: float  #: UNIX epoch seconds when *round 0* starts

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def slot_ms(self) -> int:
        """Slot width in *milliseconds* as an ``int`` (handy for logs)."""
        return int(self.slot_sec * 1000)

    def window(self, round_no: int) -> Tuple[float, float]:
        """Return *(start, end)* epoch seconds for *round \*round_no\**."""
        start = self.t0_epoch + round_no * self.slot_sec
        return start, start + self.slot_sec

    def deadline(self, round_no: int) -> float:
        """Epoch seconds for the *end* of *round \*round_no\**."""
        return self.t0_epoch + (round_no + 1) * self.slot_sec

    def round_at(self, now: Optional[float] = None) -> int:
        """Compute the *current* round number for the given ``now`` timestamp.

        Returns ``‑1`` if ``now`` is still before *t0* (pre‑sync warm‑up).
        """
        if now is None:
            now = time.time()
        if now < self.t0_epoch:
            return -1
        return int((now - self.t0_epoch) // self.slot_sec)


# ----------------------------------------------------------------------
# Public helper functions
# ----------------------------------------------------------------------

def compute_t0(slot_sec: float, holdoff_slots: int = 3) -> float:
    """Return an epoch start time that is *holdoff_slots* in the future.

    The small gap lets all processes finish startup and socket handshakes
    before round 0 begins.
    """
    return time.time() + holdoff_slots * slot_sec


def sleep_until(target_epoch: float) -> None:
    """Sleep until ``target_epoch`` with sub‑millisecond accuracy.

    We first sleep in coarse chunks (10 % of remaining time) and fall back
    to a short busy‑wait when < 1 ms remains to minimise boundary skew.
    """
    while True:
        now = time.time()
        delta = target_epoch - now
        if delta <= 0:
            break
        # Coarse sleep for most of the interval, then finer grained as we close in.
        coarse = min(delta * 0.1, 0.001)  # never longer than 1 ms
        time.sleep(coarse)


def wait_for_round_start(cfg: SlotConfig, round_no: int) -> None:
    """Block until the *start* of *round \*round_no\** according to ``cfg``."""
    start, _ = cfg.window(round_no)
    sleep_until(start)
