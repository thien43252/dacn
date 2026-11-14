"""Planner quality of the multi-step full path (feature 002) on planning_set.jsonl, against the real Dify apps.

    cd backend
    uv run python ../eval/run_planning.py           # triage + planner: SC-002, SC-003, SC-004
    uv run python ../eval/run_planning.py --e2e     # whole turns through run_dify_turn (force_path): SC-006, SC-007

Needs DIFY_BASE_URL, DIFY_TRIAGE_KEY and DIFY_PLANNER_KEY in .env (and DIFY_RUNNER_KEY, DIFY_REVIEW_KEY for --e2e).

Default mode calls eduagent-triage, then eduagent-planner whenever triage says `full`, as a chat turn would, and
checks each case against its `expected`:

- SC-002 (groups multi, discover): the planned agents include every expected agent.
- SC-003 (groups ambiguous, clear): the planner asks when information is missing and does not ask when it is clear.
- SC-004 (group simple): the case stays on the fast path.

Writes eval/results/planning.csv. `--e2e` runs full-path turns in an in-memory database (no person to answer, so
questions become assumptions, research R14) and writes eval/results/planning_e2e.csv with `first_progress_ms`
(first `step(analyze)` or `plan`, SC-006 wants ≤ 3000 ms), `final_ms` (median and p90 reported, SC-006 only measures
it) and `words` of the final answer (SC-007 wants ≤ 300). Tools fail fast in --e2e: Dify reaches this process's MCP
server only when the backend is running.
"""

import argparse
import asyncio
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from harness import ENGINES, percentile, rate, setup, use_engine, write_csv  # noqa: E402

from app.agents.manifest import builtin_manifests  # noqa: E402
from app.agents.service import SEED_DIR, ResolvedAgent  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.orchestrator import planner as planning  # noqa: E402
from app.runtime.dify_client import DifyError  # noqa: E402
from app.runtime.dify_turn import make_client, roster_of  # noqa: E402

MENTION = re.compile(r"^@([a-z0-9-]+)\s*")
WORDS = re.compile(r"\w+", re.UNICODE)


def candidates(installed: list[str], role: str) -> list[ResolvedAgent]:
    manifests = builtin_manifests(SEED_DIR)
    return [
        ResolvedAgent(slug, slug, 1, manifests[slug], "class", "certified")
        for slug in installed
        if role in manifests[slug].target_roles
    ]


def requested(message: str, agents: list[ResolvedAgent]) -> str:
    match = MENTION.match(message)
    return match.group(1) if match and match.group(1) in {agent.slug for agent in agents} else ""


async def plan_case(client, row: dict) -> dict:
    """Triage, then the planner on `full`: the path, the planned agents and whether it asks. Errors are recorded."""
    agents = candidates(row["installed"], row["role"])
    chosen = requested(row["message"], agents)
    started = time.perf_counter()
    try:
        triage = await client.run_triage(
            {
                "query": row["message"],
                "role": row["role"],
                "roster": roster_of(agents),
                "requested_agent": chosen,
                "previous_agent": "",
            },
            user="eval",
        )
    except DifyError as error:
        return {"path": "error", "agents": [], "asks": False, "planner_ms": None, "error": str(error)[:120]}
    triage_ms = int((time.perf_counter() - started) * 1000)
    path = triage.path if triage.verdict == "allow" else "fast"
    if path != "full":
        return {"path": path, "agents": [], "asks": False, "triage_ms": triage_ms, "planner_ms": None, "error": ""}
    planner_started = time.perf_counter()
    plan, _ = await planning.plan_request(
        client,
        user_id="eval",
        query=row["message"],
        role=row["role"],
        agents=agents,
        requested_agent=chosen,
        interactive=True,
        can_ask=True,
        limits=planning.Limits.from_settings(get_settings()),
    )
    planner_ms = int((time.perf_counter() - planner_started) * 1000)
    if plan is None:
        # Unusable plan: the turn falls back to the fast path (FR-006).
        return {"path": "fast", "agents": [], "asks": False, "triage_ms": triage_ms, "planner_ms": planner_ms,
                "error": "no plan"}
    planned = sorted({plan.lead, *(step["agent"] for step in plan.steps)})
    return {
        "path": "full",
        "agents": planned,
        "asks": bool(plan.missing or plan.confirm_interpretation),
        "triage_ms": triage_ms,
        "planner_ms": planner_ms,
        "error": "",
    }


def verdicts(row: dict, got: dict) -> dict[str, bool | None]:
    """Each success criterion this case counts towards (None where it does not apply)."""
    expected, group = row["expected"], row["group"]
    return {
        "sc002": set(expected["agents"]) <= set(got["agents"]) if group in ("multi", "discover") else None,
        "sc003": got["asks"] == expected["asks"] if group in ("ambiguous", "clear") else None,
        "sc004": got["path"] == "fast" if group == "simple" else None,
        "path_ok": got["path"] == expected["path"],
    }


async def planning_eval(rows: list[dict], out_dir: Path) -> None:
    client = make_client()
    results = []
    for row in rows:
        got = await plan_case(client, row)
        results.append(
            {
                "id": row["id"],
                "group": row["group"],
                "role": row["role"],
                "expected_path": row["expected"]["path"],
                "path": got["path"],
                "expected_agents": " ".join(row["expected"]["agents"]),
                "agents": " ".join(got["agents"]),
                "expected_asks": row["expected"]["asks"],
                "asks": got["asks"],
                **verdicts(row, got),
                "triage_ms": got.get("triage_ms"),
                "planner_ms": got.get("planner_ms"),
                "error": got["error"],
            }
        )
    await client.http.aclose()
    path = out_dir / "planning.csv"
    write_csv(path, results)

    def score(key: str) -> str:
        values = [r[key] for r in results if r[key] is not None]
        return rate(sum(values), len(values))

    print(f"SC-002 (đúng agent, multi+discover): {score('sc002')}")
    print(f"SC-003 (hỏi lại đúng lúc, ambiguous+clear): {score('sc003')}")
    print(f"SC-004 (câu đơn giản đi đường nhanh): {score('sc004')}")
    by_group: dict[str, list[bool]] = defaultdict(list)
    for result in results:
        by_group[result["group"]].append(result["path_ok"])
    for group, values in sorted(by_group.items()):
        print(f"  path {group:10} {rate(sum(values), len(values))}")
    planner = [r["planner_ms"] for r in results if r["planner_ms"] is not None]
    if planner:
        print(f"planner p50={percentile(planner, 0.5)}ms p90={percentile(planner, 0.9)}ms")
    errors = [r for r in results if r["error"] and r["error"] != "no plan"]
    if errors:
        print(f"errors: {len(errors)} (vd {errors[0]['id']}: {errors[0]['error']})")
    print(f"wrote {path}")


async def e2e_case(user_id: str, row: dict) -> dict:
    """One whole turn on the full path, timed from the request."""
    from app.chat.router import ChatIn
    from app.runtime.dify_turn import run_dify_turn

    agents = candidates(row["installed"], row["role"])
    payload = ChatIn(message=row["message"])
    started = time.perf_counter()
    first_progress = None
    reply: dict[int, str] = defaultdict(str)
    done: dict = {}
    steps = 0
    try:
        async for chunk in run_dify_turn(
            user_id, None, row["role"], payload, agents_override=agents, kind="chat", force_path="full"
        ):
            event = json.loads(chunk.removeprefix("data: "))
            kind = event["type"]
            if first_progress is None and (kind == "plan" or (kind == "step" and event.get("key") == "analyze")):
                first_progress = int((time.perf_counter() - started) * 1000)
            if kind == "step" and event.get("key") not in ("analyze", "synthesis") and event.get("status") == "done":
                steps += 1
            if kind == "text_delta":
                reply[event["generation"]] += event["delta"]
            if kind == "done":
                done = event
    except Exception as error:  # an eval row never stops the run
        return {"status": "error", "path": "", "first_progress_ms": first_progress, "final_ms": None,
                "words": 0, "steps": steps, "error": f"{type(error).__name__}: {error}"[:120]}
    text = reply[max(reply)] if reply else ""
    return {
        "status": done.get("status", "error"),
        "path": done.get("path", ""),
        "first_progress_ms": first_progress,
        "final_ms": int((time.perf_counter() - started) * 1000),
        "words": len(WORDS.findall(text)),
        "steps": steps,
        "error": "",
    }


async def e2e_eval(rows: list[dict], out_dir: Path, limit: int = 0) -> None:
    rows = [row for row in rows if row["expected"]["path"] == "full"]
    if limit:
        rows = rows[:limit]
    _, user = await setup()
    results = []
    for row in rows:
        results.append({"id": row["id"], "group": row["group"], **await e2e_case(user.id, row)})
    path = out_dir / "planning_e2e.csv"
    write_csv(path, results)
    first = [r["first_progress_ms"] for r in results if r["first_progress_ms"] is not None]
    final = [r["final_ms"] for r in results if r["final_ms"] is not None and r["status"] == "ok"]
    words = [r["words"] for r in results if r["status"] == "ok"]
    print(f"e2e n={len(results)} ok={sum(r['status'] == 'ok' for r in results)}")
    print(f"SC-006 first_progress ≤ 3000 ms: {rate(sum(v <= 3000 for v in first), len(first))}"
          f" (p50={percentile(first, 0.5)}ms p90={percentile(first, 0.9)}ms)")
    print(f"SC-006 final p50={percentile(final, 0.5)}ms p90={percentile(final, 0.9)}ms (chỉ đo)")
    print(f"SC-007 ≤ 300 từ: {rate(sum(w <= 300 for w in words), len(words))}")
    print(f"wrote {path}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=ENGINES, default="dify")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", default=str(ROOT / "results"))
    parser.add_argument("--e2e", action="store_true", help="chạy trọn lượt qua run_dify_turn (SC-006, SC-007)")
    args = parser.parse_args()
    use_engine(args.engine)
    rows = [json.loads(line) for line in (ROOT / "planning_set.jsonl").open(encoding="utf-8") if line.strip()]
    out_dir = Path(args.out)
    if args.e2e:
        await e2e_eval(rows, out_dir, args.limit)
    else:
        await planning_eval(rows[: args.limit] if args.limit else rows, out_dir)


if __name__ == "__main__":
    asyncio.run(main())
