"""Routing accuracy of the eduagent-triage workflow on Dify, on routing_set.jsonl.

    cd backend
    uv run python ../eval/run_routing.py                 # needs DIFY_BASE_URL and DIFY_TRIAGE_KEY in .env

Writes eval/results/routing_dify.csv and prints accuracy overall and per `kind`. routing_keyword.csv and
routing_llm.csv hold the earlier in-process routers' results (docs/BAO-CAO.md).

    uv run python ../eval/run_routing.py --latency --baseline   # mốc trước khi đổi triage (SC-001)
    uv run python ../eval/run_routing.py --latency              # sau khi đổi, so với mốc

`--latency` đo trên các câu đơn giản (`kind` clear, smalltalk): thời gian tới khi triage trả về và thời gian tới chữ
đầu tiên của runner (triage + runner tới `text_delta` đầu, rồi dừng task), báo trung vị và p90. Ghi
`routing_latency.csv`, hoặc `routing_latency_baseline.csv` với `--baseline`; khi có mốc thì in mức tăng của trung vị.
"""

import argparse
import asyncio
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from harness import ENGINES, percentile, use_engine  # noqa: E402

from app.agents.manifest import builtin_manifests  # noqa: E402
from app.agents.service import SEED_DIR, ResolvedAgent  # noqa: E402
from app.runtime.dify_client import DifyError  # noqa: E402
from app.runtime.dify_turn import MAX_SYSTEM_PROMPT, make_client, pick_agent, roster_of  # noqa: E402
from app.runtime.prompts import build_system_prompt  # noqa: E402

SIMPLE_KINDS = {"clear", "smalltalk"}


def candidates(installed: list[str], role: str) -> list[ResolvedAgent]:
    manifests = builtin_manifests(SEED_DIR)
    agents = []
    for slug in installed:
        manifest = manifests[slug]
        if role in manifest.target_roles:
            agents.append(ResolvedAgent(slug, slug, 1, manifest, "class", "certified"))
    return agents


async def triage_route(client, row: dict, agents: list[ResolvedAgent]):
    """The eduagent-triage workflow (safety + routing), as a chat turn would call it. Dify errors count as misses."""
    try:
        result = await client.run_triage(
            {
                "query": row["message"],
                "role": row["role"],
                "roster": roster_of(agents),
                "requested_agent": "",
                "previous_agent": "",
            },
            user="eval",
        )
    except DifyError as error:
        return "error", str(error)[:120], None
    return pick_agent(agents, result.agent).slug, result.route_reason, result.usage


async def first_token(client, row: dict, agents: list[ResolvedAgent]) -> dict:
    """Triage, then the runner until its first text; the Dify task is stopped right after. Times in ms, None on
    error. The runner gets a handle this process does not serve, so a tool call fails fast; the first text still
    comes (or the row counts as an error)."""
    started = time.perf_counter()
    try:
        result = await client.run_triage(
            {
                "query": row["message"],
                "role": row["role"],
                "roster": roster_of(agents),
                "requested_agent": "",
                "previous_agent": "",
            },
            user="eval",
        )
    except DifyError as error:
        return {"triage_ms": None, "first_token_ms": None, "path": "", "error": str(error)[:120]}
    triage_ms = int((time.perf_counter() - started) * 1000)
    agent = pick_agent(agents, result.agent)
    inputs = {
        "system_prompt": build_system_prompt(agent, None, row["role"], agents)[:MAX_SYSTEM_PROMPT],
        "ctx": "eval-latency",
        "safety_note": "false",
    }
    first_ms = None
    error = ""
    task_id = ""
    try:
        async for event in client.stream_runner(row["message"], inputs, "", "eval"):
            if event.kind == "start":
                task_id = event.task_id
            elif event.kind in ("delta", "replace"):
                first_ms = int((time.perf_counter() - started) * 1000)
                break
            elif event.kind == "error":
                error = event.text[:120]
                break
    except DifyError as failure:
        error = str(failure)[:120]
    if task_id:
        try:
            await client.stop(task_id, "eval")
        except Exception:  # best effort
            pass
    return {
        "triage_ms": triage_ms,
        "first_token_ms": first_ms,
        "path": getattr(result, "path", ""),
        "error": error,
    }


def median(values: list[int]) -> int:
    return percentile(values, 0.5)


async def latency(rows: list[dict], out_dir: Path, baseline: bool) -> None:
    rows = [row for row in rows if row["kind"] in SIMPLE_KINDS]
    client = make_client()
    results = []
    for row in rows:
        agents = candidates(row["installed"], row["role"])
        results.append({"id": row["id"], "kind": row["kind"], **await first_token(client, row, agents)})
    await client.http.aclose()

    out_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240 (a CLI script, nothing else runs)
    path = out_dir / ("routing_latency_baseline.csv" if baseline else "routing_latency.csv")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "kind", "triage_ms", "first_token_ms", "path", "error"])
        writer.writeheader()
        writer.writerows(results)

    def summary(items: list[dict]) -> dict[str, int]:
        triage = [r["triage_ms"] for r in items if r["triage_ms"] is not None]
        first = [r["first_token_ms"] for r in items if r["first_token_ms"] is not None]
        return {
            "n": len(items),
            "triage_p50": median(triage),
            "triage_p90": percentile(triage, 0.9),
            "first_p50": median(first),
            "first_p90": percentile(first, 0.9),
            "errors": sum(1 for r in items if r["error"]),
        }

    now = summary(results)
    print(
        f"latency n={now['n']} errors={now['errors']} triage p50={now['triage_p50']}ms p90={now['triage_p90']}ms "
        f"first_token p50={now['first_p50']}ms p90={now['first_p90']}ms"
    )
    base_path = out_dir / "routing_latency_baseline.csv"
    if not baseline and base_path.exists():
        with base_path.open(encoding="utf-8") as handle:
            base_rows = [
                {
                    **row,
                    "triage_ms": int(row["triage_ms"]) if row["triage_ms"] else None,
                    "first_token_ms": int(row["first_token_ms"]) if row["first_token_ms"] else None,
                }
                for row in csv.DictReader(handle)
            ]
        base = summary(base_rows)
        for key in ("triage_p50", "first_p50"):
            if base[key]:
                change = (now[key] - base[key]) / base[key]
                verdict = "OK" if change <= 0.10 else "VƯỢT 10%"
                print(f"  {key}: baseline={base[key]}ms now={now[key]}ms change={change:+.1%} ({verdict}, SC-001)")
    print(f"wrote {path}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=ENGINES, default="dify")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", default=str(ROOT / "results"))
    parser.add_argument("--latency", action="store_true", help="đo độ trễ trên câu đơn giản (SC-001)")
    parser.add_argument("--baseline", action="store_true", help="với --latency: ghi thành mốc so sánh")
    args = parser.parse_args()
    engine = use_engine(args.engine)
    label = engine

    rows = [json.loads(line) for line in (ROOT / "routing_set.jsonl").open(encoding="utf-8")]
    if args.limit:
        rows = rows[: args.limit]
    if args.latency:
        await latency(rows, Path(args.out), args.baseline)
        return
    client = make_client()
    results = []
    for row in rows:
        agents = candidates(row["installed"], row["role"])
        started = time.perf_counter()
        got, reason, usage = await triage_route(client, row, agents)
        results.append(
            {
                "engine": engine,
                "id": row["id"],
                "kind": row["kind"],
                "expected": row["expected_agent"],
                "got": got,
                "reason": reason,
                "correct": got == row["expected_agent"],
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "input_tokens": usage.input_tokens if usage else 0,
                "output_tokens": usage.output_tokens if usage else 0,
            }
        )
    await client.http.aclose()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240 (a CLI script, nothing else runs)
    path = out_dir / f"routing_{label}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)

    by_kind: dict[str, list[bool]] = defaultdict(list)
    for result in results:
        by_kind[result["kind"]].append(result["correct"])
    correct = sum(result["correct"] for result in results)
    print(f"router={label} accuracy={correct}/{len(results)} = {correct / len(results):.1%}")
    for kind, values in sorted(by_kind.items()):
        print(f"  {kind:28} {sum(values)}/{len(values)}")
    misses = [r for r in results if not r["correct"]]
    if misses:
        print("misses:")
        for result in misses:
            print(f"  {result['id']} expected={result['expected']} got={result['got']} ({result['reason']})")
    print(f"wrote {path}")


if __name__ == "__main__":
    asyncio.run(main())
