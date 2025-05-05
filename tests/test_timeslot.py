import time
import math
import pytest

from sync.timeslot import compute_t0, SlotConfig


@pytest.mark.parametrize("slot", [0.02, 0.10])
def test_deadline_and_round(slot, monkeypatch):
    """
    Verify that:
      • round_at() maps now → correct k
      • deadline(k) returns the end-of-slot timestamp
    across a couple of slot widths.
    """
    holdoff = 5
    t0 = compute_t0(slot, holdoff)
    cfg = SlotConfig(slot_sec=slot, t0_epoch=t0)

    # check first four rounds
    for k in range(4):
        fake_now = t0 + k * slot + slot / 2          # mid-slot
        monkeypatch.setattr(time, "time", lambda: fake_now)

        assert cfg.round_at() == k
        assert math.isclose(cfg.deadline(k), t0 + (k + 1) * slot, rel_tol=1e-9)

    # time before t0 → round -1
    monkeypatch.setattr(time, "time", lambda: t0 - 1e-4)
    assert cfg.round_at() == -1
