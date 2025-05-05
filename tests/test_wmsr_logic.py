# tests/test_wmsr_logic.py
import math
import pytest

from algorithms.wmsr import WMSR

# (F, inbox, expected next value)
CASES = [
    # F = 0 → keep own value plus every neighbour
    (0, {"B": 1.0, "C": 2.0}, (0.0 + 1.0 + 2.0) / 3),
    # F = 1 → prune one max (100) and one min (-2)
    (1, {"B": 5.0, "C": -2.0, "D": 100.0}, (0.0 + 5.0) / 2),
    # F = 2 → prune two highest and two lowest
    (
        2,
        {"B": 5.0, "C": -2.0, "D": 100.0, "E": -10.0, "F": 1.0},
        (0.0 + 1.0) / 2,  # own value (0) and 1 remain
    ),
]


@pytest.mark.parametrize("F,inbox,expected", CASES)
def test_wmsr_step(F, inbox, expected):
    """
    Verify W-MSR step() correctly prunes extreme neighbour values
    and always keeps the agent’s own current value.
    """
    alg = WMSR()
    alg.initialise(
        agent_id="A",
        initial_value=0.0,
        neighbours=list(inbox.keys()),
        params={"F": F},
    )
    next_val = alg.step(0, inbox)
    assert math.isclose(next_val, expected, rel_tol=1e-9)
