"""Routing accuracy on routing_set.jsonl.

    cd backend
    uv run python ../eval/run_routing.py                 # keyword router (offline baseline)
    uv run python ../eval/run_routing.py --router llm    # LLM router with the provider configured in .env

Writes eval/results/routing_<router>.csv and prints accuracy overall and per `kind`.
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

from app.agents.manifest import builtin_manifests  # noqa: E402
from app.agents.service import SEED_DIR, ResolvedAgent  # noqa: E402
from app.llm.registry import get_chat_model  # noqa: E402
from app.runtime.router import route  # noqa: E402


def candidates(installed: list[str], role: str) -> list[ResolvedAgent]:
    manifests = builtin_manifests(SEED_DIR)
    agents = []
    for slug in installed:
        manifest = manifests[slug]
        if role in manifest.target_roles:
            agents.append(ResolvedAgent(slug, slug, 1, manifest, "class", "certified"))
    return agents


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--router", choices=["keyword", "llm"], default="keyword")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    rows = [json.loads(line) for line in (ROOT / "routing_set.jsonl").open(encoding="utf-8")]
    if args.limit:
        rows = rows[: args.limit]
    model = get_chat_model() if args.router == "llm" else None
    results = []
    for row in rows:
        agents = candidates(row["installed"], row["role"])
        started = time.perf_counter()
        chosen, usage = await route(row["message"], agents, role=row["role"], model=model, mode=args.router)
        results.append(
            {
                "id": row["id"],
                "kind": row["kind"],
                "expected": row["expected_agent"],
                "got": chosen.agent.slug,
                "reason": chosen.reason,
                "correct": chosen.agent.slug == row["expected_agent"],
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "input_tokens": usage.input_tokens if usage else 0,
                "output_tokens": usage.output_tokens if usage else 0,
            }
        )

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"routing_{args.router}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)

    by_kind: dict[str, list[bool]] = defaultdict(list)
    for result in results:
        by_kind[result["kind"]].append(result["correct"])
    correct = sum(result["correct"] for result in results)
    print(f"router={args.router} accuracy={correct}/{len(results)} = {correct / len(results):.1%}")
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
