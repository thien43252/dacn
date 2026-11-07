"""Smoke test: the experiment scripts run end to end offline (fake provider) and write their results."""

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
        "EMBEDDING_PROVIDER": "fake",
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


@pytest.mark.slow
def test_experiment_scripts_run_offline(tmp_path: Path) -> None:
    assert "accuracy=" in run("run_routing.py", out=tmp_path)
    run("run_redteam.py", "--limit", "6", "--benign", "2", "--modes", "off", "full", out=tmp_path)
    summary = (tmp_path / "redteam_summary.md").read_text("utf-8")
    assert "| full |" in summary and "| off |" in summary
    run("run_certify.py", "--only", "giai-bai-nhanh", "on-thi-hoa-9", "--redteam-cases", "5", out=tmp_path)
    rows = (tmp_path / "certify.csv").read_text("utf-8")
    assert "giai-bai-nhanh,reject," in rows and ",rejected," in rows
    assert rows.startswith("engine,") and "langgraph,giai-bai-nhanh," in rows
    assert "engine,id," in (tmp_path / "redteam_full.csv").read_text("utf-8")


# Nothing listens there: every Dify call fails at once, which the scripts must survive and report.
NO_DIFY = {"DIFY_BASE_URL": "http://127.0.0.1:9", "DIFY_TIMEOUT_S": "2"}


@pytest.mark.slow
def test_experiment_scripts_take_the_dify_engine(tmp_path: Path) -> None:
    out = run("run_routing.py", "--engine", "dify", "--limit", "3", out=tmp_path, **NO_DIFY)
    assert "router=dify accuracy=" in out
    assert (tmp_path / "routing_dify.csv").read_text("utf-8").startswith("engine,")
    out = run("run_redteam.py", "--engine", "dify", "--limit", "2", "--benign", "1", out=tmp_path, **NO_DIFY)
    assert "mode 'off' has no Dify counterpart" in out
    summary = (tmp_path / "redteam_summary_dify.md").read_text("utf-8")
    assert "Engine: `dify`" in summary and "| full |" in summary and "| prompt_only |" in summary
    rows = (tmp_path / "redteam_full_dify.csv").read_text("utf-8")
    assert rows.startswith("engine,") and ",unjudged," in rows
    run("run_certify.py", "--engine", "dify", "--only", "on-thi-hoa-9", "--redteam-cases", "2", out=tmp_path, **NO_DIFY)
    assert (tmp_path / "certify_dify.csv").read_text("utf-8").startswith("engine,")
