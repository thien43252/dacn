"""Smoke test: the experiment scripts run end to end offline (fake provider) and write their results."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

EVAL = Path(__file__).resolve().parents[2] / "eval"
BACKEND = Path(__file__).resolve().parents[1]


def run(script: str, *args: str, out: Path) -> str:
    env = {**os.environ, "LLM_PROVIDER": "fake", "EMBEDDING_PROVIDER": "fake", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, str(EVAL / script), *args, "--out", str(out)],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return result.stdout


@pytest.mark.slow
def test_experiment_scripts_run_offline(tmp_path: Path) -> None:
    assert "accuracy=" in run("run_routing.py", out=tmp_path)
    run("run_redteam.py", "--limit", "6", "--benign", "2", "--modes", "off", "full", out=tmp_path)
    summary = (tmp_path / "redteam_summary.md").read_text("utf-8")
    assert "| full |" in summary and "| off |" in summary
    run("run_certify.py", "--only", "giai-bai-nhanh", "on-thi-hoa-9", "--redteam-cases", "5", out=tmp_path)
    rows = (tmp_path / "certify.csv").read_text("utf-8")
    assert "giai-bai-nhanh,reject," in rows and ",rejected," in rows
