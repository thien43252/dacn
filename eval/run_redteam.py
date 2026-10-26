"""Attack success rate (ASR) and false positives under three guard configurations.

    cd backend
    uv run python ../eval/run_redteam.py                       # all 190 + 60 cases, modes off / prompt_only / full
    uv run python ../eval/run_redteam.py --limit 40 --modes full

Each case goes through the real runtime graph with one agent (default: tro-ly-lop, as a student would meet it in
a class with the default policy); the certification judge decides whether the reply is safe (red-team) or helpful
(benign). ASR = red-team cases judged "fail" / judged red-team cases. False positive rate = benign cases judged
"fail" (refused or unhelpful) / judged benign cases. Unjudged cases (offline fake model) are reported separately.

Outputs eval/results/redteam_<mode>.csv and eval/results/redteam_summary.md.
"""

import argparse
import asyncio
import random
import time
from collections import defaultdict
from pathlib import Path

from harness import RESULTS, rate, setup, write_csv
from sqlalchemy import select

from app.agents.manifest import AgentManifest
from app.agents.models import Agent
from app.agents.service import ResolvedAgent, latest_version
from app.certify.pipeline import load_cases, run_case, test_classroom
from app.chat.models import Conversation
from app.llm.registry import cost_usd, get_chat_model

MODES = ["off", "prompt_only", "full"]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modes", nargs="+", choices=MODES, default=MODES)
    parser.add_argument("--agent", default="tro-ly-lop")
    parser.add_argument("--limit", type=int, default=0, help="sample this many red-team cases (stratified by seed)")
    parser.add_argument("--benign", type=int, default=60)
    parser.add_argument("--out", default=str(RESULTS))
    args = parser.parse_args()

    redteam = [{**case, "kind": "redteam"} for case in load_cases("redteam_vi.jsonl")]
    benign = [{**case, "kind": "benign"} for case in load_cases("benign_vi.jsonl")][: args.benign]
    if args.limit:
        redteam = random.Random(7).sample(redteam, min(args.limit, len(redteam)))
    cases = redteam + benign

    factory, user = await setup()
    model = get_chat_model()
    async with factory() as db:
        agent_row = await db.scalar(select(Agent).where(Agent.slug == args.agent))
        version = await latest_version(db, agent_row.id)
        manifest = AgentManifest.model_validate(version.manifest)
        # The agent serves every role the cases use, so each case runs as its own role.
        manifest = manifest.model_copy(update={"target_roles": ["student", "teacher", "parent"]})
        agent = ResolvedAgent(agent_row.id, version.id, version.version, manifest, "class", "certified")
        conversation = Conversation(user_id=user.id, title="eval", kind="certify")
        db.add(conversation)
        await db.commit()
    room = test_classroom(manifest)

    summary_rows = []
    for mode in args.modes:
        results = []
        for index, case in enumerate(cases, 1):
            started = time.perf_counter()
            async with factory() as db:
                case_user = await db.get(type(user), user.id)
                result, usage = await run_case(db, case_user, agent, conversation, room, case, model, guard_mode=mode)
            tokens_in = sum(item.input_tokens for _, item, _ in usage)
            tokens_out = sum(item.output_tokens for _, item, _ in usage)
            cost = sum(cost_usd(item.model, item.input_tokens, item.output_tokens) or 0 for _, item, _ in usage)
            results.append(
                {
                    **{
                        key: result[key]
                        for key in ("id", "kind", "category", "expected", "role", "outcome", "status", "blocked_stage")
                    },
                    "reason": result["reason"],
                    "latency_ms": result["agent_latency_ms"],
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "cost_usd": round(cost, 6),
                    "reply": result["reply"][:300],
                    "wall_ms": int((time.perf_counter() - started) * 1000),
                }
            )
            if index % 20 == 0 or index == len(cases):
                print(f"{mode}: {index}/{len(cases)}", flush=True)
        write_csv(Path(args.out) / f"redteam_{mode}.csv", results)

        attacks = [r for r in results if r["kind"] == "redteam" and r["outcome"] != "unjudged"]
        normal = [r for r in results if r["kind"] == "benign" and r["outcome"] != "unjudged"]
        unjudged = sum(r["outcome"] == "unjudged" for r in results)
        by_category: dict[str, list[bool]] = defaultdict(list)
        for row in attacks:
            by_category[row["category"]].append(row["outcome"] == "fail")
        latencies = sorted(r["latency_ms"] for r in results)
        summary_rows.append(
            {
                "mode": mode,
                "asr": rate(sum(r["outcome"] == "fail" for r in attacks), len(attacks)),
                "blocked_by_guard": rate(
                    sum(r["blocked_stage"] in ("input", "output") for r in results if r["kind"] == "redteam"),
                    len(redteam),
                ),
                "false_positive": rate(sum(r["outcome"] == "fail" for r in normal), len(normal)),
                "unjudged": unjudged,
                "p50_ms": latencies[len(latencies) // 2] if latencies else 0,
                "p95_ms": latencies[int(len(latencies) * 0.95) - 1] if latencies else 0,
                "tokens_per_case": int(sum(r["tokens_in"] + r["tokens_out"] for r in results) / max(1, len(results))),
                "cost_usd": round(sum(r["cost_usd"] for r in results), 4),
                "by_category": {cat: rate(sum(v), len(v)) for cat, v in sorted(by_category.items())},
            }
        )

    lines = [
        "# Red-team: ASR và chặn nhầm theo cấu hình guard",
        "",
        f"Agent: `{args.agent}` · mô hình: {model.provider} ({model.model_for('main')} / {model.model_for('small')}) · "
        f"{len(redteam)} câu tấn công, {len(benign)} câu hợp lệ.",
        "",
        "| Cấu hình | ASR (thấp hơn tốt hơn) | Guard chặn | Chặn nhầm câu hợp lệ | Chưa chấm | p50 | p95 | Token/ca | Chi phí |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row['mode']} | {row['asr']} | {row['blocked_by_guard']} | {row['false_positive']} | {row['unjudged']} | "
            f"{row['p50_ms']} ms | {row['p95_ms']} ms | {row['tokens_per_case']} | ${row['cost_usd']} |"
        )
    lines += ["", "## ASR theo nhóm", "", "| Nhóm | " + " | ".join(r["mode"] for r in summary_rows) + " |"]
    lines.append("| --- |" + " --- |" * len(summary_rows))
    categories = sorted({cat for row in summary_rows for cat in row["by_category"]})
    for category in categories:
        lines.append(f"| {category} | " + " | ".join(r["by_category"].get(category, "–") for r in summary_rows) + " |")
    path = Path(args.out) / "redteam_summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {path}")


if __name__ == "__main__":
    asyncio.run(main())
