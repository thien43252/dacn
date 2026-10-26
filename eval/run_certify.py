"""Precision and recall of the certification pipeline on 20 labelled agents (eval/certify_agents.yaml).

    cd backend
    uv run python ../eval/run_certify.py                         # full pipeline, settings from .env
    uv run python ../eval/run_certify.py --redteam-cases 12      # cheaper run

"Positive" = an agent that should be rejected. The pipeline flags an agent when it is not certified (rejected or
sent to admin review), so:
    precision = bad agents flagged / all agents flagged
    recall    = bad agents flagged / all bad agents
The static stage alone is reported as a baseline, to show what the red-team run and the LLM judge add.

Outputs eval/results/certify.csv and eval/results/certify_summary.md.
"""

import argparse
import asyncio
from pathlib import Path

import yaml
from harness import RESULTS, ROOT, setup, write_csv

from app.agents.manifest import AgentManifest
from app.agents.models import Agent, AgentVersion
from app.certify.models import Certification
from app.certify.pipeline import run_certification
from app.certify.static import static_checks
from app.config import get_settings


def metrics(rows: list[dict], flagged_key: str) -> dict[str, str]:
    tp = sum(r[flagged_key] and r["expected"] == "reject" for r in rows)
    fp = sum(r[flagged_key] and r["expected"] == "accept" for r in rows)
    fn = sum(not r[flagged_key] and r["expected"] == "reject" for r in rows)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": f"{precision:.0%}", "recall": f"{recall:.0%}"}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--redteam-cases", type=int, default=0, help="override CERTIFY_REDTEAM_CASES")
    parser.add_argument("--only", nargs="*", default=[], help="slugs to run")
    parser.add_argument("--out", default=str(RESULTS))
    args = parser.parse_args()
    settings = get_settings()
    if args.redteam_cases:
        settings.certify_redteam_cases = args.redteam_cases

    entries = yaml.safe_load((ROOT / "certify_agents.yaml").read_text("utf-8"))
    if args.only:
        entries = [e for e in entries if e["manifest"]["slug"] in args.only]
    factory, user = await setup()
    rows = []
    for index, entry in enumerate(entries, 1):
        manifest = AgentManifest.model_validate(entry["manifest"])
        data = manifest.model_dump(mode="json")
        async with factory() as db:
            agent = Agent(slug=manifest.slug, owner_id=user.id, visibility="private", draft_manifest=data)
            db.add(agent)
            await db.flush()
            version = AgentVersion(agent_id=agent.id, version=1, manifest=data, certification_status="pending")
            db.add(version)
            await db.flush()
            certification = Certification(agent_id=agent.id, agent_version_id=version.id, requested_by=user.id)
            db.add(certification)
            await db.commit()
            certification_id = certification.id
        await run_certification(certification_id)
        async with factory() as db:
            done = await db.get(Certification, certification_id)
        report = done.report or {}
        static_errors = [f.id for f in static_checks(manifest) if not f.ok and f.severity == "error"]
        rows.append(
            {
                "slug": manifest.slug,
                "expected": entry["expected"],
                "flaw": entry.get("flaw", ""),
                "status": done.status,
                "score": "" if done.score is None else round(done.score, 3),
                "flagged": done.status != "certified",
                "static_flagged": bool(static_errors),
                "static_errors": " ".join(static_errors),
                "manifest_risk": (report.get("manifest_review") or {}).get("risk", ""),
                "cases": len(report.get("cases", [])),
                "unjudged": sum(case["outcome"] == "unjudged" for case in report.get("cases", [])),
                "duration_s": report.get("duration_s", ""),
                "reasons": " | ".join(report.get("decision", {}).get("reasons", [])),
            }
        )
        print(f"{index}/{len(entries)} {manifest.slug}: {done.status} (expected {entry['expected']})", flush=True)

    write_csv(Path(args.out) / "certify.csv", rows)
    full, static = metrics(rows, "flagged"), metrics(rows, "static_flagged")
    lines = [
        "# Kiểm định: precision / recall trên 20 agent có nhãn",
        "",
        f"{sum(r['expected'] == 'reject' for r in rows)} agent xấu, {sum(r['expected'] == 'accept' for r in rows)} agent tốt. "
        f"Mỗi agent {settings.certify_redteam_cases} câu red-team + {settings.certify_benign_cases} câu hợp lệ. "
        '"Gắn cờ" = không được cấp chứng nhận tự động (bị từ chối hoặc chờ duyệt).',
        "",
        "| Cách kiểm | Precision | Recall | Bắt đúng | Gắn cờ nhầm | Bỏ sót |",
        "| --- | --- | --- | --- | --- | --- |",
        f"| Chỉ kiểm tra tĩnh | {static['precision']} | {static['recall']} | {static['tp']} | {static['fp']} | {static['fn']} |",
        f"| Toàn bộ pipeline | {full['precision']} | {full['recall']} | {full['tp']} | {full['fp']} | {full['fn']} |",
        "",
        "| Agent | Nhãn | Kết quả | Điểm | Tĩnh | Rủi ro prompt | Chưa chấm |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['slug']} | {row['expected']} | {row['status']} | {row['score']} | {row['static_errors'] or '–'} | "
            f"{row['manifest_risk'] or '–'} | {row['unjudged']} |"
        )
    path = Path(args.out) / "certify_summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {path}")


if __name__ == "__main__":
    asyncio.run(main())
