"""The Dify DSLs in infra/dify/ stay in line with the files the backend reads (research R3), offline."""

import importlib.util
import json
from pathlib import Path

import pytest
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
    assert [o["variable"] for o in end["data"]["outputs"]] == [
        "verdict",
        "category",
        "reason",
        "agent",
        "route_reason",
        "path",
    ]


def code_main(app: str, node_id: str):
    """`main()` of a Code node, run here exactly as Dify runs it."""
    [node] = [n for n in dsl(app)["workflow"]["graph"]["nodes"] if n["id"] == node_id]
    namespace: dict = {}
    exec(node["data"]["code"], namespace)  # noqa: S102 (our own DSL)
    return namespace["main"]


def test_triage_path_branch_runs_in_parallel_and_defaults_to_fast() -> None:
    """Feature 002 contracts/dify-apps.md §1: the branch starts from Start (not after safety) and only an exact
    "full" counts."""
    graph = dsl("eduagent-triage.yml")["workflow"]["graph"]
    edges = {(edge["source"], edge["target"]) for edge in graph["edges"]}
    assert ("start", "path") in edges and ("path", "merge") in edges
    [path] = [n for n in graph["nodes"] if n["id"] == "path"]
    assert path["data"]["type"] == "llm" and path["data"]["model"]["completion_params"]["temperature"] == 0
    merge = code_main("eduagent-triage.yml", "merge")
    roster = json.dumps([{"slug": "gia-su-toan"}, {"slug": "tro-ly-lop"}])
    decision = json.dumps({"agent": "gia-su-toan", "route_reason": "ui"})
    assert merge("safe", decision, roster, "full")["path"] == "full"
    assert merge("safe", decision, roster, " Full.\n")["path"] == "full"
    for odd in ("", "fast", "đầy đủ", "full path please", None):
        assert merge("safe", decision, roster, odd)["path"] == "fast"


def test_planner_inputs_and_outputs_match_the_contract() -> None:
    graph = dsl("eduagent-planner.yml")["workflow"]["graph"]
    [start] = [n for n in graph["nodes"] if n["data"]["type"] == "start"]
    assert [v["variable"] for v in start["data"]["variables"]] == [
        "query",
        "role",
        "roster",
        "requested_agent",
        "history",
        "resume",
        "interactive",
        "can_ask",
        "limits",
    ]
    [end] = [n for n in graph["nodes"] if n["data"]["type"] == "end"]
    assert [o["variable"] for o in end["data"]["outputs"]] == ["ok", "plan"]


def test_planner_parse_node() -> None:
    parse = code_main("eduagent-planner.yml", "parse")
    raw = {
        "goal": "Ôn Pytago",
        "lead": "@gia-su-toan",
        "missing": [{"id": "q1", "question": "Lớp mấy?", "options": ["7", 8]}, {"question": ""}],
        "steps": [{"key": "s1", "agent": "tao-de", "title": "Soạn bài", "task": "Soạn", "depends_on": []}, "x"],
    }
    result = parse("Đây là kế hoạch:\n```json\n" + json.dumps(raw, ensure_ascii=False) + "\n```")
    assert result["ok"] == "true"
    plan = json.loads(result["plan"])
    assert plan["lead"] == "gia-su-toan" and len(plan["steps"]) == 1
    assert plan["missing"] == [{"id": "q1", "question": "Lớp mấy?", "options": ["7", "8"], "why": ""}]
    assert plan["answers_pending"] is False and plan["assumptions"] == []
    assert parse("Xin lỗi, tôi không lập được kế hoạch.") == {"ok": "false", "plan": "{}"}
    assert parse('{"steps": "nope"}')["ok"] == "false"


def test_orchestration_prompt_blocks_pass_the_runner_moderation() -> None:
    """STEP_MODE and SYNTHESIS_MODE travel in system_prompt, which the runner's keyword moderation scans."""
    from app.orchestrator.prompts import STEP_MODE, SYNTHESIS_MODE

    for part in (STEP_MODE, SYNTHESIS_MODE):
        assert not dify_rules.contains_blocked_keyword(part)


def test_presets_are_the_ones_the_backend_recognises() -> None:
    config = dsl("eduagent-runner.yml")["workflow"]["features"]["sensitive_word_avoidance"]["config"]
    assert dify_rules.is_preset_input_block(config["inputs_config"]["preset_response"])
    assert "111" in dify_rules.presets()["self_harm_support"]


def test_review_outputs_match_the_contract() -> None:
    graph = dsl("eduagent-review.yml")["workflow"]["graph"]
    [start] = [n for n in graph["nodes"] if n["data"]["type"] == "start"]
    assert [v["variable"] for v in start["data"]["variables"]] == ["question", "reply", "role", "no_direct_answers"]
    [end] = [n for n in graph["nodes"] if n["data"]["type"] == "end"]
    assert [o["variable"] for o in end["data"]["outputs"]] == ["verdict", "category", "reason"]
    assert {"answer_withheld", "output_blocked"} <= set(dify_rules.presets())


def review_parse():
    """`main()` of the review app's Code node, run here exactly as Dify runs it."""
    [node] = [n for n in dsl("eduagent-review.yml")["workflow"]["graph"]["nodes"] if n["id"] == "parse"]
    namespace: dict = {}
    exec(node["data"]["code"], namespace)  # noqa: S102 (our own DSL file)
    return namespace["main"]


def reviewer(**answer) -> str:
    return "Kết quả: " + json.dumps(answer, ensure_ascii=False)


@pytest.mark.parametrize(
    ("text", "no_direct_answers", "verdict"),
    [
        # Withholding an answer needs both the class policy and a specific exercise.
        (reviewer(is_exercise=True, verdict="block", category="academic_integrity", reason="x = 2"), "true", "block"),
        (
            reviewer(is_exercise=False, verdict="block", category="academic_integrity", reason="tóm tắt"),
            "true",
            "allow",
        ),
        (reviewer(verdict="block", category="academic_integrity", reason="thiếu is_exercise"), "true", "allow"),
        (reviewer(is_exercise=True, verdict="block", category="academic_integrity", reason="x"), "false", "allow"),
        (reviewer(is_exercise="true", verdict="block", category="academic_integrity", reason="chuỗi"), "true", "block"),
        # Other categories do not depend on the policy or on is_exercise.
        (
            reviewer(is_exercise=False, verdict="block", category="unsafe", reason="hướng dẫn nguy hiểm"),
            "false",
            "block",
        ),
        # A block without a known category, or anything unreadable, keeps the answer.
        (reviewer(is_exercise=True, verdict="block", category="", reason="thiếu nhóm"), "true", "allow"),
        ("không phải JSON", "true", "allow"),
        ("", "true", "allow"),
    ],
)
def test_review_parse_only_withholds_answers_to_specific_exercises(text, no_direct_answers, verdict) -> None:
    result = review_parse()(text, no_direct_answers)
    assert result["verdict"] == verdict
    assert set(result) == {"verdict", "category", "reason"}
    if verdict == "allow":
        assert result["category"] == ""
