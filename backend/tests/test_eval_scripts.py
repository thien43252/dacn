"""Smoke test: the experiment scripts run end to end offline (fake judge, unreachable Dify) and write results."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

EVAL = Path(__file__).resolve().parents[2] / "eval"
BACKEND = Path(__file__).resolve().parents[1]


def run(script: str, *args: str, out: Path, **extra_env: str) -> str:
    env = {
        **os.environ,
        "LLM_PROVIDER": "fake",
        "PYTHONIOENCODING": "utf-8",
        **extra_env,
    }
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


# Nothing listens there: every Dify call fails at once, which the scripts must survive and report.
NO_DIFY = {"DIFY_BASE_URL": "http://127.0.0.1:9", "DIFY_TIMEOUT_S": "2"}


@pytest.mark.slow
def test_experiment_scripts_run_offline(tmp_path: Path) -> None:
    out = run("run_routing.py", "--limit", "3", out=tmp_path, **NO_DIFY)
    assert "router=dify accuracy=" in out
    assert (tmp_path / "routing_dify.csv").read_text("utf-8").startswith("engine,")
    run("run_redteam.py", "--limit", "2", "--benign", "1", out=tmp_path, **NO_DIFY)
    summary = (tmp_path / "redteam_summary_dify.md").read_text("utf-8")
    assert "Engine: `dify`" in summary and "| full |" in summary and "| prompt_only |" in summary
    rows = (tmp_path / "redteam_full_dify.csv").read_text("utf-8")
    assert rows.startswith("engine,") and ",unjudged," in rows
    run("run_certify.py", "--only", "giai-bai-nhanh", "on-thi-hoa-9", "--redteam-cases", "2", out=tmp_path, **NO_DIFY)
    rows = (tmp_path / "certify_dify.csv").read_text("utf-8")
    # The static stage rejects giai-bai-nhanh before any Dify call.
    assert rows.startswith("engine,") and "dify,giai-bai-nhanh,reject," in rows and ",rejected," in rows
