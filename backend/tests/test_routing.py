import json
from pathlib import Path

from app.agents.manifest import builtin_manifests
from app.agents.service import SEED_DIR, ResolvedAgent
from app.llm.fake import FakeChatModel, Scripted
from app.runtime.router import keyword_route, route
from tests.helpers import chat, class_with_student

ROUTING_SET = Path(__file__).resolve().parents[2] / "eval" / "routing_set.jsonl"


def agents(*slugs: str) -> list[ResolvedAgent]:
    manifests = builtin_manifests(SEED_DIR)
    return [ResolvedAgent(slug, slug, 1, manifests[slug], "class", "certified") for slug in slugs]


CLASS_AGENTS = agents("tro-ly-lop", "gia-su-toan", "luyen-tieng-anh", "on-tap-tai-lieu", "cham-van")


async def test_mention_and_ui_choice_win_over_the_router() -> None:
    model = FakeChatModel()
    chosen, _ = await route("@cham-van giải phương trình này", CLASS_AGENTS, role="student", model=model)
    assert (chosen.agent.slug, chosen.reason) == ("cham-van", "mention")
    chosen, _ = await route("Xin chào", CLASS_AGENTS, role="student", requested="gia-su-toan", model=model)
    assert (chosen.agent.slug, chosen.reason) == ("gia-su-toan", "chosen")
    assert model.calls == []


async def test_mention_of_unavailable_agent_goes_to_fallback() -> None:
    chosen, _ = await route("@tao-de cho mình xem đề", CLASS_AGENTS, role="student", model=FakeChatModel())
    assert (chosen.agent.slug, chosen.reason) == ("tro-ly-lop", "mention_unavailable")


async def test_llm_router_answer_is_used_and_validated() -> None:
    model = FakeChatModel()
    model.script('{"agent": "luyen-tieng-anh", "confidence": 0.9, "reason": "ngữ pháp tiếng Anh"}', tier="small")
    chosen, usage = await route("Thì hiện tại hoàn thành dùng khi nào?", CLASS_AGENTS, role="student", model=model)
    assert (chosen.agent.slug, chosen.reason) == ("luyen-tieng-anh", "llm")
    assert usage is not None and model.calls[0]["tier"] == "small"
    # The candidate list (with capabilities) is in the prompt; the message is fenced as data.
    prompt = model.calls[0]["messages"][0].content
    assert "gia-su-toan" in prompt and "<<<" in prompt

    # An agent that is not a candidate, or low confidence, never reaches the user.
    model.script('{"agent": "tao-de", "confidence": 0.99}', tier="small")
    chosen, _ = await route("Giải thích định lý Pytago", CLASS_AGENTS, role="student", model=model)
    assert chosen.reason == "keyword" and chosen.agent.slug == "gia-su-toan"
    model.script('{"agent": "cham-van", "confidence": 0.2}', tier="small")
    chosen, _ = await route("hmm", CLASS_AGENTS, role="student", model=model)
    assert (chosen.agent.slug, chosen.reason) == ("tro-ly-lop", "fallback")


def test_keyword_router_handles_missing_diacritics_and_follow_ups() -> None:
    assert keyword_route("rut gon phan so 18/24 the nao", CLASS_AGENTS).agent.slug == "gia-su-toan"
    assert keyword_route("Chào bạn!", CLASS_AGENTS).agent.slug == "tro-ly-lop"
    follow_up = keyword_route("tiếp đi", CLASS_AGENTS, previous="gia-su-toan")
    assert (follow_up.agent.slug, follow_up.reason) == ("gia-su-toan", "sticky")


async def test_keyword_baseline_accuracy_on_routing_set() -> None:
    """Regression floor for the offline router; the LLM router is measured with eval/run_routing.py."""
    rows = [json.loads(line) for line in ROUTING_SET.open(encoding="utf-8")]
    manifests = builtin_manifests(SEED_DIR)
    correct = 0
    for row in rows:
        candidates = [
            ResolvedAgent(slug, slug, 1, manifests[slug], "class", "certified")
            for slug in row["installed"]
            if row["role"] in manifests[slug].target_roles
        ]
        chosen, _ = await route(row["message"], candidates, role=row["role"], mode="keyword")
        correct += chosen.agent.slug == row["expected_agent"]
    assert correct / len(rows) >= 0.7


async def test_chat_routes_without_mention_and_follows_class_subjects(as_user, fake_llm) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    hub = {agent["slug"]: agent for agent in (await teacher.get("/api/hub/agents")).json()}
    for slug in ("gia-su-toan", "luyen-tieng-anh"):
        await teacher.post(f"/api/classes/{room['id']}/agents", json={"agent_id": hub[slug]["id"]})
    # Guards and the router share the small tier, so answer the router by its system prompt.
    fake_llm.respond_with(
        lambda messages, system, tools, tier: (
            Scripted(text='{"agent": "luyen-tieng-anh", "confidence": 0.8}') if "bộ định tuyến" in system else None
        )
    )
    events = await chat(student, "Phân biệt make và do giúp mình", class_id=room["id"])
    agent_event = next(event for event in events if event["type"] == "agent")
    assert (agent_event["agent"], agent_event["reason"]) == ("luyen-tieng-anh", "llm")

    # Limiting the class to maths removes the English agent for students.
    policy = (await teacher.get(f"/api/classes/{room['id']}/policy")).json()
    await teacher.put(f"/api/classes/{room['id']}/policy", json={**policy, "allowed_subjects": ["toan"]})
    slugs = {a["slug"] for a in (await student.get("/api/chat/agents", params={"class_id": room["id"]})).json()}
    assert slugs == {"tro-ly-lop", "gia-su-toan"}
