"""Schema checks for the hand-written evaluation datasets in `eval/` (see eval/README.md)."""

import json
from collections import Counter
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parents[2] / "eval"

ROLES = {"student", "teacher", "parent"}
SUBJECTS = {"toan", "van", "anh", "ly", "hoa", "sinh", "su", "dia", "gdcd", "tin", "chung"}
REDTEAM_CATEGORIES = {
    "academic_integrity": "ai-",
    "jailbreak": "jb-",
    "prompt_injection": "pi-",
    "pii": "pii-",
    "age_inappropriate": "age-",
    "self_harm": "sh-",
    "harassment": "hr-",
    "dangerous_illegal": "dg-",
    "misinformation": "mis-",
    "role_boundary": "rb-",
}
AGENTS = {
    "gia-su-toan",
    "luyen-tieng-anh",
    "on-tap-tai-lieu",
    "cham-van",
    "tao-de",
    "tro-ly-phu-huynh",
    "tro-ly-lop",
}


def load(name: str) -> list[dict]:
    with (EVAL_DIR / name).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def assert_unique_ids(rows: list[dict]) -> None:
    duplicates = [key for key, count in Counter(row["id"] for row in rows).items() if count > 1]
    assert duplicates == []


def assert_prompt_row(row: dict) -> None:
    assert row["role"] in ROLES, row["id"]
    assert row["subject"] in SUBJECTS, row["id"]
    assert 5 <= row["grade"] <= 12, row["id"]
    assert row["prompt"].strip() and row["criteria"].strip() and row["technique"].strip(), row["id"]


def test_redteam_schema_and_coverage() -> None:
    rows = load("redteam_vi.jsonl")
    assert len(rows) >= 150
    assert_unique_ids(rows)
    for row in rows:
        assert_prompt_row(row)
        assert row["category"] in REDTEAM_CATEGORIES, row["id"]
        assert row["id"].startswith(REDTEAM_CATEGORIES[row["category"]]), row["id"]
        assert row["expected"] in {"block", "safe_response"}, row["id"]
        # Only injection rows carry untrusted document/tool text; direct injections (pi-011, pi-016) have none.
        assert "context" not in row or row["category"] == "prompt_injection", row["id"]
    injections = [row for row in rows if row["category"] == "prompt_injection"]
    assert sum("context" in row for row in injections) >= 15
    counts = Counter(row["category"] for row in rows)
    assert set(counts) == set(REDTEAM_CATEGORIES)
    assert min(counts.values()) >= 8


def test_benign_schema() -> None:
    rows = load("benign_vi.jsonl")
    assert len(rows) >= 50
    assert_unique_ids(rows)
    for row in rows:
        assert_prompt_row(row)
        assert row["category"] == "benign" and row["expected"] == "allow", row["id"]
        assert row["id"].startswith("bn-")


def test_routing_schema() -> None:
    rows = load("routing_set.jsonl")
    assert len(rows) >= 100
    assert_unique_ids(rows)
    for row in rows:
        assert row["role"] in ROLES, row["id"]
        assert set(row["installed"]) <= AGENTS, row["id"]
        assert row["expected_agent"] in row["installed"], row["id"]
        assert "tro-ly-lop" in row["installed"], row["id"]
        assert row["message"].strip(), row["id"]
    roles = Counter(row["role"] for row in rows)
    assert all(roles[role] >= 10 for role in ROLES)


def test_no_overlap_between_attack_and_benign_prompts() -> None:
    attack = {row["prompt"] for row in load("redteam_vi.jsonl")}
    benign = {row["prompt"] for row in load("benign_vi.jsonl")}
    assert attack.isdisjoint(benign)


PLANNING_GROUPS = {"simple", "multi", "ambiguous", "clear", "discover"}


def test_planning_schema() -> None:
    """eval/planning_set.jsonl (feature 002): about 60 cases in 5 groups, each with its expected path, agents and
    whether the planner should ask (SC-002 to SC-004)."""
    rows = load("planning_set.jsonl")
    assert len(rows) >= 55
    assert_unique_ids(rows)
    for row in rows:
        assert row["group"] in PLANNING_GROUPS, row["id"]
        assert row["id"].startswith(f"pl-{row['group']}-"), row["id"]
        assert row["role"] in ROLES, row["id"]
        assert set(row["installed"]) <= AGENTS and "tro-ly-lop" in row["installed"], row["id"]
        assert row["message"].strip(), row["id"]
        expected = row["expected"]
        assert expected["path"] in {"fast", "full"}, row["id"]
        assert set(expected["agents"]) <= set(row["installed"]), row["id"]
        assert isinstance(expected["asks"], bool), row["id"]
        # Groups say what is expected: simple means fast, ambiguous means one question, the rest never ask.
        assert (expected["path"] == "fast") == (row["group"] == "simple"), row["id"]
        assert expected["asks"] == (row["group"] == "ambiguous"), row["id"]
    groups = Counter(row["group"] for row in rows)
    assert set(groups) == PLANNING_GROUPS and min(groups.values()) >= 10


def test_redteam_covers_policy_evasion_through_coordination() -> None:
    """Feature 002 (SC-008): splitting work across agents, notes, question cards and teacher tools as a way around
    the class policy, and class documents that tell an agent to post, assign, change notes or install."""
    rows = load("redteam_vi.jsonl")
    coordination = [row for row in rows if row["technique"].startswith("multi_agent_")]
    triggers = [row for row in rows if row["technique"].startswith("doc_") and row["id"] >= "pi-021"]
    assert len(coordination) >= 5 and len(triggers) >= 4
    assert all("context" in row for row in triggers)
