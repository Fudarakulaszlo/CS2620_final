import importlib
import pytest

from core.algorithm import get_algorithm, list_algorithms


def test_wmsr_registered():
    """
    Importing the plugin module should register 'wmsr'
    in the global algorithm registry.
    """
    importlib.import_module("algorithms.wmsr")

    assert "wmsr" in list_algorithms()
    AlgoCls = get_algorithm("wmsr")
    assert callable(AlgoCls)


def test_missing_algorithm():
    """
    Accessing an unknown key must raise KeyError.
    """
    with pytest.raises(KeyError):
        get_algorithm("__does_not_exist__")
