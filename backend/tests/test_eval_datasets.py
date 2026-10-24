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
