"""Approvals (US6): decide()'s truth table and the card flows (once, this conversation, always, modes, expiry)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.orchestration import approvals
from app.orchestration.approvals import Action, decide
from app.orchestration.models import ALWAYS_ASK, ApprovalCard, ApprovalRule
from tests.helpers import chat, class_with_student, conversation_id_of, conversation_messages
from tests.test_people import card_of, script_ask


def rule(kind="send", effect="allow", source="card", **match):
    return ApprovalRule(scope="user", scope_id="u", action_kind=kind, effect=effect, source=source, **match)


SEND = Action("send", "tro-ly-lop", "ask_person", "teacher-1")


def test_none_is_always_allowed() -> None:
    assert decide(Action("none", "a", "math_check"), [rule("none", "deny")], "members_choose", True).effect == "allow"


@pytest.mark.parametrize("kind", sorted(ALWAYS_ASK))
def test_always_ask_kinds_ask_by_default_whatever_the_switch(kind) -> None:
    action = Action(kind, "a", "t")
    assert decide(action, [], "members_choose", False).effect == "ask"
    assert decide(action, [], "members_choose", True).effect == "ask"


@pytest.mark.parametrize("source", ["typed", "admin", "class"])
def test_only_a_card_answer_opens_an_always_ask_kind(source) -> None:
    assert decide(SEND, [rule(source=source)], "members_choose", False).effect == "ask"
    assert decide(SEND, [rule(source="card")], "members_choose", False).effect == "allow"


def test_deny_before_allow_and_strictest_wins() -> None:
    assert decide(SEND, [rule(), rule(effect="deny", source="admin")], "members_choose", False).effect == "deny"
    assert decide(SEND, [rule(), rule(effect="ask", source="class")], "members_choose", False).effect == "ask"


def test_rules_match_on_agent_tool_and_target() -> None:
    other_target = rule(target="teacher-2")
    assert decide(SEND, [other_target], "members_choose", False).effect == "ask"
    assert decide(SEND, [rule(target="teacher-1", agent_slug="tro-ly-lop")], "members_choose", False).effect == "allow"


def test_broken_rule_refuses() -> None:
    assert decide(SEND, [rule(effect="maybe")], "members_choose", False).effect == "deny"


def test_modes_shape_the_choices() -> None:
    assert decide(SEND, [], "members_choose", False).choices == ["once", "conversation", "always", "deny"]
    assert decide(SEND, [], "ask_every_time", False).choices == ["once", "deny"]
    held = decide(SEND, [rule()], "do_it_yourself", False)
    assert held.effect == "ask" and held.choices == ["did_it", "dont"]


def test_changes_follow_the_extra_vigilant_switch() -> None:
    change = Action("change", "a", "t")
    assert decide(change, [], "members_choose", False).effect == "allow"
    assert decide(change, [], "members_choose", True).effect == "ask"
    assert decide(change, [rule("change", "ask", "typed")], "members_choose", False).effect == "ask"


# ---------------- flows ----------------


async def test_allow_for_this_conversation_then_ask_again_elsewhere(as_user, fake_llm) -> None:
    teacher, student, parent, room = await class_with_student(as_user)
    script_ask(fake_llm, recipient="parent", subject="", question="Kính gửi phụ huynh: em An cần ôn thêm chương 2.")
    events = await chat(parent, "Nhờ hỏi giáo viên", class_id=room["id"], agent="tro-ly-lop")
    # A parent asks the homeroom teacher instead: re-script for a recipient a parent may reach.
    fake_llm.responders.clear()
    script_ask(fake_llm, recipient="homeroom", subject="", question="Kính gửi cô: con em cần ôn thêm chương 2 không ạ?")
    events = await chat(parent, "Hỏi cô chủ nhiệm giúp", class_id=room["id"], agent="tro-ly-lop")
    conversation_id = conversation_id_of(events)
    card = card_of(await conversation_messages(parent, conversation_id))
    assert [c["id"] for c in card["choices"]] == ["once", "conversation", "always", "deny"]
    await parent.post(f"/api/approvals/{card['id']}/answer", json={"choice": "conversation"})

    await chat(parent, "Hỏi thêm cô câu nữa", class_id=room["id"], conversation_id=conversation_id)
    messages = await conversation_messages(parent, conversation_id)
    assert sum(1 for m in messages if m.get("approval_card")) == 1  # no second card here
    assert len((await teacher.get("/api/inbox")).json()) == 2

    settings = (await parent.get("/api/settings/approvals")).json()
    [allowance] = settings["conversation_allowances"]
    assert (await parent.delete(f"/api/settings/approvals/rules/{allowance['id']}")).status_code == 204
    await chat(parent, "Hỏi cô câu thứ ba", class_id=room["id"], conversation_id=conversation_id)
    messages = await conversation_messages(parent, conversation_id)
    assert sum(1 for m in messages if m.get("approval_card")) == 2  # asks again once turned off


async def test_always_allow_creates_a_removable_rule(as_user, fake_llm) -> None:
    teacher, _, parent, room = await class_with_student(as_user)
    script_ask(fake_llm, recipient="homeroom", subject="", question="Kính gửi cô: lịch họp phụ huynh?")
    events = await chat(parent, "Hỏi cô", class_id=room["id"], agent="tro-ly-lop")
    card = card_of(await conversation_messages(parent, conversation_id_of(events)))
    await parent.post(f"/api/approvals/{card['id']}/answer", json={"choice": "always"})
    [saved] = (await parent.get("/api/settings/approvals")).json()["rules"]
    assert saved["source"] == "card" and saved["effect"] == "allow"
    # Same agent, tool and recipient in another conversation: the saved rule applies, no card.
    restarted = (await parent.post(f"/api/chat/direct/{conversation_id_of(events)}/restart")).json()
    await chat(parent, "Hỏi cô lần nữa", class_id=room["id"], conversation_id=restarted["id"])
    assert not any(m.get("approval_card") for m in await conversation_messages(parent, restarted["id"]))
    assert len((await teacher.get("/api/inbox")).json()) == 2  # the second one went straight through
    assert (await parent.delete(f"/api/settings/approvals/rules/{saved['id']}")).status_code == 204


async def test_admin_modes_and_rules(as_user, fake_llm) -> None:
    admin = await as_user("admin")
    teacher, student, parent, room = await class_with_student(as_user)
    modes = (await admin.get("/api/admin/approvals/modes")).json()
    assert {"action_kind": "send", "role": "student", "mode": "ask_every_time"} in modes
    assert (
        await admin.put(
            "/api/admin/approvals/modes", json={"action_kind": "send", "role": "parent", "mode": "do_it_yourself"}
        )
    ).status_code == 200
    script_ask(fake_llm, recipient="homeroom", subject="", question="Kính gửi cô: lịch họp?")
    events = await chat(parent, "Hỏi cô", class_id=room["id"], agent="tro-ly-lop")
    card = card_of(await conversation_messages(parent, conversation_id_of(events)))
    assert [c["id"] for c in card["choices"]] == ["did_it", "dont"]
    await parent.post(f"/api/approvals/{card['id']}/answer", json={"choice": "did_it"})
    assert (await teacher.get("/api/inbox")).json() == []  # the agent never acts in this mode

    # An admin rule cannot open an always-ask kind.
    bad = await admin.post("/api/admin/approvals/rules", json={"action_kind": "send", "effect": "allow"})
    assert bad.status_code == 422
    assert (await student.get("/api/admin/approvals/modes")).status_code == 403


async def test_expired_card_cannot_be_used(as_user, fake_llm, sessionmaker) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    script_ask(fake_llm)
    events = await chat(student, "Xin nghỉ", class_id=room["id"], agent="tro-ly-lop")
    card = card_of(await conversation_messages(student, conversation_id_of(events)))
    async with sessionmaker() as db:
        await db.execute(update(ApprovalCard).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
        await db.commit()
    response = await student.post(f"/api/approvals/{card['id']}/answer", json={"choice": "once"})
    assert response.status_code == 409
    assert (await teacher.get("/api/inbox")).json() == []


async def test_only_the_origin_user_answers_and_choices_are_checked(as_user, fake_llm) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    script_ask(fake_llm)
    events = await chat(student, "Xin nghỉ", class_id=room["id"], agent="tro-ly-lop")
    card = card_of(await conversation_messages(student, conversation_id_of(events)))
    assert (await teacher.post(f"/api/approvals/{card['id']}/answer", json={"choice": "once"})).status_code == 404
    # "always" is not offered to a student (ask every time).
    assert (await student.post(f"/api/approvals/{card['id']}/answer", json={"choice": "always"})).status_code == 422


def test_choice_labels_cover_every_choice() -> None:
    assert set(approvals.CHOICE_LABELS) >= {"once", "conversation", "always", "deny", "did_it", "dont"}


async def test_rule_decisions_are_logged_with_the_rule(as_user, fake_llm, sessionmaker) -> None:
    """FR-056: an approval decided by a rule (no card) is recorded with the rule that decided it."""
    from sqlalchemy import select

    from app.audit.models import GuardEvent
    from tests.helpers import chat, class_with_student
    from tests.test_people import script_ask

    admin = await as_user("admin")
    rule = (await admin.post("/api/admin/approvals/rules", json={"action_kind": "send", "effect": "deny"})).json()
    _, student, _, room = await class_with_student(as_user)
    script_ask(fake_llm)
    await chat(student, "Em xin nộp muộn", class_id=room["id"], agent="tro-ly-lop")
    async with sessionmaker() as db:
        [event] = (await db.scalars(select(GuardEvent).where(GuardEvent.stage == "approval"))).all()
        assert event.verdict == "block" and rule["id"] in event.reason
    rows = [row for row in (await student.get("/api/me/activity")).json() if row["type"] == "approval"]
    assert rows and rows[0]["decided_by"] == "rule" and rule["id"] in rows[0]["reason"]


async def test_admin_sees_approval_activity_without_content(as_user, fake_llm) -> None:
    """FR-057: the admin sees what was allowed and refused platform-wide, never the private text."""
    from tests.helpers import chat, class_with_student
    from tests.test_people import script_ask

    admin = await as_user("admin")
    await admin.post("/api/admin/approvals/rules", json={"action_kind": "send", "effect": "deny"})
    _, student, _, room = await class_with_student(as_user)
    script_ask(fake_llm)
    await chat(student, "Em xin nộp muộn", class_id=room["id"], agent="tro-ly-lop")
    rows = (await admin.get("/api/admin/approvals/activity")).json()
    assert {row["type"] for row in rows} >= {"approval", "person_request"}
    assert all(row.get("conversation_id") is None and "body" not in row for row in rows)
    assert (await student.get("/api/admin/approvals/activity")).status_code == 403
