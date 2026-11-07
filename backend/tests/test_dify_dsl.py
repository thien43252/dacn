"""The Dify DSLs in infra/dify/ stay in line with the files the backend reads (research R3), offline."""

import importlib.util
from pathlib import Path

import yaml

from app.guard import dify_rules

DIFY = Path(__file__).resolve().parents[2] / "infra" / "dify"


def load_sync():
    spec = importlib.util.spec_from_file_location("sync_keywords", DIFY / "sync_keywords.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dsl(name: str) -> dict:
    return yaml.safe_load((DIFY / name).read_text(encoding="utf-8"))


def test_runner_moderation_matches_the_keyword_file() -> None:
    assert load_sync().problems() == []


def test_check_reports_a_keyword_file_ahead_of_the_dsl(monkeypatch) -> None:
    sync = load_sync()
    monkeypatch.setattr(sync, "keywords_text", lambda: "tu khoa moi")
    assert any("eduagent-runner.yml" in problem for problem in sync.problems())


def test_keywords_fit_difys_limits() -> None:
    keywords = dify_rules.keywords()
    assert 0 < len(keywords) <= 100  # Dify: at most 100 rows
    assert len("\n".join(keywords)) < 10000


def test_no_keyword_appears_in_a_system_prompt_part() -> None:
    """Dify's keyword moderation scans every input, system_prompt included; a match would block every turn."""
    from app.runtime.prompts import PLATFORM_RULES, SAFETY_NOTE

    for part in (PLATFORM_RULES, SAFETY_NOTE):
        assert not dify_rules.contains_blocked_keyword(part)
    for path in (Path(__file__).resolve().parents[2] / "seed" / "agents").glob("*.yaml"):
        assert not dify_rules.contains_blocked_keyword(path.read_text(encoding="utf-8")), path.name


def test_tool_ctx_is_a_fixed_variable_and_hidden_from_the_model() -> None:
    for name in ("eduagent-runner.yml", "eduagent-runner-raw.yml"):
        [agent] = [n for n in dsl(name)["workflow"]["graph"]["nodes"] if n["data"]["type"] == "agent"]
        tools = agent["data"]["agent_parameters"]["tools"]["value"]
        assert {tool["tool_name"] for tool in tools} == {
            "class_doc_search",
            "quiz_generator",
            "rubric_grader",
            "math_check",
            "progress_summary",
        }
        for tool in tools:
            assert tool["provider_name"] == "eduagent-tools" and tool["type"] == "mcp"
            # type "variable": with "mixed"/"constant" Dify would send the template text itself (spike T006).
            assert tool["parameters"]["ctx"] == {"auto": 0, "value": {"type": "variable", "value": ["start", "ctx"]}}


def test_triage_outputs_match_the_contract() -> None:
    [end] = [n for n in dsl("eduagent-triage.yml")["workflow"]["graph"]["nodes"] if n["data"]["type"] == "end"]
    assert [o["variable"] for o in end["data"]["outputs"]] == ["verdict", "category", "reason", "agent", "route_reason"]


def test_presets_are_the_ones_the_backend_recognises() -> None:
    config = dsl("eduagent-runner.yml")["workflow"]["features"]["sensitive_word_avoidance"]["config"]
    assert dify_rules.is_preset_input_block(config["inputs_config"]["preset_response"])
    assert "111" in dify_rules.presets()["self_harm_support"]
