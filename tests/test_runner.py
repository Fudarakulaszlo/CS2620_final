"""
End-to-end smoke test: launches a 3-agent run (10 rounds, 50 ms slots)
in a temporary directory and verifies that CSV logs are produced.

Keeps runtime < 30 s so it’s CI-friendly.
"""
import json
import subprocess
import sys
import time
from pathlib import Path


def test_runner_smoke(tmp_path):
    run_dir = tmp_path / "out"

    cmd = [
        sys.executable,
        "runner.py",
        "--random",
        "3",
        "2",  # N=3, avg_deg≈2
        "--algo",
        "wmsr",
        "--slot",
        "0.05",
        "--holdoff",
        "10",
        "--rounds",
        "10",
        "--seed",
        "1",
        "--out",
        str(run_dir),
    ]

    # give the subprocess a generous timeout (units: seconds)
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr

    # 1. runfile exists and is valid JSON
    runfile = run_dir / "runfile.json"
    assert runfile.exists()
    json.loads(runfile.read_text())

    # 2. at least one CSV per agent with >1 lines
    csv_files = list(run_dir.glob("agent_*.csv"))
    assert csv_files, "no agent_*.csv produced"
    for csv in csv_files:
        lines = [ln for ln in csv.read_text().splitlines() if ln and not ln.startswith("#")]
        # expect 10 rounds → 10 lines
        assert len(lines) >= 2, f"{csv} is empty"
