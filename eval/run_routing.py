"""Routing accuracy of the eduagent-triage workflow on Dify, on routing_set.jsonl.

    cd backend
    uv run python ../eval/run_routing.py                 # needs DIFY_BASE_URL and DIFY_TRIAGE_KEY in .env

Writes eval/results/routing_dify.csv and prints accuracy overall and per `kind`. routing_keyword.csv and
routing_llm.csv hold the earlier in-process routers' results (docs/BAO-CAO.md).
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

from harness import ENGINES, use_engine  # noqa: E402

from app.agents.manifest import builtin_manifests  # noqa: E402
from app.agents.service import SEED_DIR, ResolvedAgent  # noqa: E402
from app.runtime.dify_client import DifyError  # noqa: E402
from app.runtime.dify_turn import make_client, pick_agent, roster_of  # noqa: E402


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


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=ENGINES, default="dify")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", default=str(ROOT / "results"))
    args = parser.parse_args()
    engine = use_engine(args.engine)
    label = engine

    rows = [json.loads(line) for line in (ROOT / "routing_set.jsonl").open(encoding="utf-8")]
    if args.limit:
        rows = rows[: args.limit]
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
