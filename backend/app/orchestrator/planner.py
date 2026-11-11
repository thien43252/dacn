"""Calls eduagent-planner and re-checks its plan (specs/002-multi-agent-orchestration/contracts/dify-apps.md §2).

The model may be wrong or prompt-injected, so every rule that matters is enforced here and not in the prompt:
agents come only from the roster (FR-039), the requested agent leads (FR-005), the step graph has no cycle, and the
limits of FR-008 and FR-025 hold. A plan that cannot be used means the fast path (FR-006).
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from app.agents.manifest import FALLBACK_SLUG
from app.agents.service import ResolvedAgent
from app.guard import dify_rules
from app.llm.base import Usage
from app.runtime.dify_client import DifyClient, DifyError
from app.runtime.prompts import planner_roster

log = logging.getLogger("eduagent.orchestrator")

TITLE_MAX = 80
QUESTION_MAX = 200
OPTION_MAX = 60
OPTIONS_MAX = 6
TASK_MAX = 2000
GOAL_MAX = 500
HISTORY_MESSAGES = 6
HISTORY_MESSAGE_CHARS = 500
HISTORY_CHARS = 3000


@dataclass
class Limits:
    max_steps: int = 5
    max_agents: int = 3
    max_questions: int = 3

    @classmethod
    def from_settings(cls, settings) -> "Limits":
        return cls(settings.orch_max_steps, settings.orch_max_agents, settings.orch_max_questions)


@dataclass
class Plan:
    goal: str
    lead: str
    steps: list[dict[str, Any]]
    missing: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    confirm_interpretation: str = ""
    answers_pending: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def step_title_fallback(agent: ResolvedAgent) -> str:
    return f"Phần việc của {agent.manifest.name}"[:TITLE_MAX]


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _lead(raw_lead: str, requested: str, by_slug: dict[str, ResolvedAgent]) -> str:
    if requested in by_slug:
        return requested
    if raw_lead in by_slug:
        return raw_lead
    if FALLBACK_SLUG in by_slug:
        return FALLBACK_SLUG
    return next(iter(by_slug))


def _topological(steps: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Steps in dependency order (stable for ties); None when the graph has a cycle."""
    pending = {step["key"]: set(step["depends_on"]) for step in steps}
    order: list[dict[str, Any]] = []
    done: set[str] = set()
    while pending:
        ready = [step for step in steps if step["key"] in pending and pending[step["key"]] <= done]
        if not ready:
            return None
        for step in ready:
            order.append(step)
            done.add(step["key"])
            del pending[step["key"]]
    return order


def _questions(raw: Any, limit: int) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        question = _text(item.get("question"), QUESTION_MAX)
        if not question:
            continue
        qid = _text(item.get("id"), 16)
        if not qid or qid in seen:
            qid = f"q{len(questions) + 1}"
            while qid in seen:
                qid += "_"
        seen.add(qid)
        options = [_text(option, OPTION_MAX) for option in item.get("options") or [] if _text(option, OPTION_MAX)]
        questions.append({"id": qid, "question": question, "options": options[:OPTIONS_MAX]})
        if len(questions) >= limit:
            break
    return questions


def validate_plan(
    raw: Any,
    agents: list[ResolvedAgent],
    *,
    requested_agent: str = "",
    interactive: bool = True,
    can_ask: bool = True,
    limits: Limits | None = None,
    fallback_goal: str = "",
) -> Plan | None:
    """Applies every rule of the table in contracts/dify-apps.md §2. None means: take the fast path."""
    limits = limits or Limits()
    if not isinstance(raw, dict) or not agents or not isinstance(raw.get("steps", []), list):
        return None
    by_slug = {agent.slug: agent for agent in agents}
    lead = _lead(_text(raw.get("lead"), 48).lstrip("@"), requested_agent, by_slug)
    goal = _text(raw.get("goal"), GOAL_MAX) or _text(fallback_goal, GOAL_MAX)

    # Steps: unknown agents become the lead; empty or repeated keys are dropped.
    steps: list[dict[str, Any]] = []
    keys: set[str] = set()
    for item in raw.get("steps") or []:
        if not isinstance(item, dict):
            continue
        key = _text(item.get("key"), 16)
        if not key or key in keys or key in ("analyze", "synthesis"):
            continue
        keys.add(key)
        slug = _text(item.get("agent"), 48).lstrip("@")
        agent = by_slug.get(slug) or by_slug[lead]
        title = _text(item.get("title"), TITLE_MAX)
        if not title or dify_rules.contains_blocked_keyword(title):
            title = step_title_fallback(agent)
        depends = item.get("depends_on") if isinstance(item.get("depends_on"), list) else []
        steps.append(
            {
                "key": key,
                "agent": agent.slug,
                "title": title,
                "task": _text(item.get("task"), TASK_MAX) or goal,
                "depends_on": [_text(dep, 16) for dep in depends],
            }
        )
    # Dependencies on unknown keys or on the step itself are dropped; a cycle that remains means no plan.
    for step in steps:
        step["depends_on"] = list(dict.fromkeys(d for d in step["depends_on"] if d in keys and d != step["key"]))
    ordered = _topological(steps)
    if ordered is None:
        return None

    # Limits, in dependency order: what does not fit is cut, and edges to it are removed.
    kept: list[dict[str, Any]] = []
    used_agents = {lead}
    for step in ordered:
        if len(kept) >= limits.max_steps:
            break
        if step["agent"] not in used_agents and len(used_agents) >= limits.max_agents:
            continue
        used_agents.add(step["agent"])
        kept.append(step)
    kept_keys = {step["key"] for step in kept}
    for step in kept:
        step["depends_on"] = [dep for dep in step["depends_on"] if dep in kept_keys]
    if not kept:
        kept = [
            {
                "key": "s1",
                "agent": lead,
                "title": step_title_fallback(by_slug[lead]),
                "task": goal or "Trả lời yêu cầu của người dùng.",
                "depends_on": [],
            }
        ]

    assumptions = [_text(a, 300) for a in raw.get("assumptions") or [] if isinstance(a, str) and _text(a, 300)]
    missing = _questions(raw.get("missing"), limits.max_questions)
    confirm = _text(raw.get("confirm_interpretation"), 400)
    if not (interactive and can_ask):
        # Nobody to ask, or no question left this turn: decide and say so (FR-007, FR-041).
        assumptions += [f"Chưa rõ “{q['question']}”, mình chọn phương án hợp lý nhất." for q in missing]
        if confirm:
            assumptions.append(confirm)
        missing, confirm = [], ""
    return Plan(
        goal=goal,
        lead=lead,
        steps=kept,
        missing=missing,
        assumptions=assumptions,
        confirm_interpretation=confirm,
        answers_pending=bool(raw.get("answers_pending", False)),
    )


def format_history(messages: list[tuple[str, str]]) -> str:
    """The last few messages as "Người dùng:/Trợ lý:" lines, newest kept when over budget."""
    lines = [
        f"{'Người dùng' if role == 'user' else 'Trợ lý'}: {' '.join(content.split())[:HISTORY_MESSAGE_CHARS]}"
        for role, content in messages[-HISTORY_MESSAGES:]
        if content.strip()
    ]
    while lines and len("\n".join(lines)) > HISTORY_CHARS:
        lines.pop(0)
    return "\n".join(lines)


async def plan_request(
    client: DifyClient,
    *,
    user_id: str,
    query: str,
    role: str,
    agents: list[ResolvedAgent],
    requested_agent: str = "",
    history: str = "",
    resume: dict[str, Any] | None = None,
    interactive: bool = True,
    can_ask: bool = True,
    limits: Limits | None = None,
) -> tuple[Plan | None, Usage | None]:
    """eduagent-planner, then validate_plan. (None, usage) when Dify fails or the plan is unusable (FR-006)."""
    limits = limits or Limits()
    requested = requested_agent if requested_agent in {agent.slug for agent in agents} else ""
    inputs = {
        "query": query[:4000],
        "role": role,
        "roster": planner_roster(agents, role),
        "requested_agent": requested,
        "history": history[:HISTORY_CHARS],
        "resume": json.dumps(resume, ensure_ascii=False) if resume else "",
        "interactive": "true" if interactive else "false",
        "can_ask": "true" if can_ask and interactive else "false",
        "limits": json.dumps(asdict(limits)),
    }
    try:
        result = await client.run_planner(inputs, user=user_id)
    except DifyError as error:
        log.warning("planner failed, fast path: %s", error)
        return None, None
    if not result.ok:
        log.info("planner returned no usable plan, fast path")
        return None, result.usage
    plan = validate_plan(
        result.plan,
        agents,
        requested_agent=requested,
        interactive=interactive,
        can_ask=can_ask,
        limits=limits,
        fallback_goal=query,
    )
    return plan, result.usage
