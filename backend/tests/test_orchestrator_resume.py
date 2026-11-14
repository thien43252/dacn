"""Pausing for the user and resuming (specs/002-multi-agent-orchestration User Story 1, research R7, R14), offline
against recorded-shape planner responses."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.chat.models import ChatMessage
from app.chat.router import ChatIn
from app.orchestrator.models import RunStep, TurnRun
from app.runtime.dify_turn import run_dify_turn
from tests.dify_fake import deltas_sse, planner_body, rows, triage_body
from tests.helpers import chat, class_with_student, parse_sse, reply_text

MISSING = planner_body("planner_missing.json")
ANSWERED = planner_body("planner_resume_answer.json")
NEW_TOPIC = planner_body("planner_resume_new_topic.json")


def kinds(events: list[dict]) -> list[str]:
    return [e["type"] for e in events]


def notices(events: list[dict]) -> list[str]:
    return [e["kind"] for e in events if e["type"] == "notice"]


async def asked(as_user, dify, planner: dict = MISSING):
    """A student's request that the planner cannot do without asking. Returns the users, the class, the events, the
    waiting run and the conversation id."""
    teacher, student, parent, room = await class_with_student(as_user)
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = planner
    events = await chat(student, "Làm đề ôn tập cho em", class_id=room["id"])
    conversation_id = next(e["conversation_id"] for e in events if e["type"] == "conversation")
    return teacher, student, parent, room, events, conversation_id


async def the_run(sessionmaker, conversation_id: str) -> TurnRun:
    [run] = await rows(sessionmaker, TurnRun, TurnRun.conversation_id == conversation_id)
    return run


async def answer(student, room, conversation_id: str, run_id: str, message: str, **reply) -> list[dict]:
    return await chat(
        student,
        message,
        class_id=room["id"],
        conversation_id=conversation_id,
        reply={"run_id": run_id, **reply},
    )


async def test_missing_information_pauses_with_a_question_card(app, as_user, dify, sessionmaker) -> None:
    *_, events, conversation_id = await asked(as_user, dify)
    assert kinds(events)[-2:] == ["ask", "done"]
    ask, done = events[-2], events[-1]
    assert done["status"] == "awaiting_user" and done["path"] == "full"
    assert ask["kind"] == "clarify" and ask["skippable"] is True
    assert [q["id"] for q in ask["questions"]] == ["q1", "q2"]
    assert ask["questions"][0]["options"] == ["Toán – chương 1", "Toán – chương 2", "Tiếng Anh"]
    # Nothing ran yet: no step, no synthesis.
    assert [e["key"] for e in events if e["type"] == "step"] == ["analyze", "analyze"]
    assert dify.calls("/chat-messages") == []

    run = await the_run(sessionmaker, conversation_id)
    assert run.status == "awaiting_user" and run.clarify_rounds == 1 and run.expires_at is not None
    assert run.pending["kind"] == "clarify" and run.pending["ask_message_id"] == ask["message_id"]
    [message] = await rows(sessionmaker, ChatMessage, ChatMessage.role == "assistant")
    assert message.id == ask["message_id"] and message.status == "awaiting_user"
    assert message.meta["ask"]["state"] == "open" and message.meta["ask"]["run_id"] == run.id
    assert "Em muốn ôn môn nào" in message.content


async def test_answers_through_the_card_resume_the_run(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room, events, conversation_id = await asked(as_user, dify)
    run = await the_run(sessionmaker, conversation_id)
    dify.planner = ANSWERED
    dify.runner = [deltas_sse("Ghi chú đề.", conversation_id=""), deltas_sse("Đề ôn tập ", "Toán chương 2.")]
    events = await answer(
        student, room, conversation_id, run.id,
        "Em muốn ôn môn nào, chương nào?\nToán – chương 2\n\nĐề gồm bao nhiêu câu?\n10",
        answers={"q1": "Toán – chương 2", "q2": "10"},
    )

    [plan_event] = [e for e in events if e["type"] == "plan"]
    assert plan_event["resumed"] is True and plan_event["run_id"] == run.id
    assert "ask" not in kinds(events) and "analyze" not in [e.get("key") for e in events]
    assert reply_text(events) == "Đề ôn tập Toán chương 2."
    assert events[-1]["status"] == "ok" and events[-1]["path"] == "full"

    [_, resumed] = dify.calls("#planner")
    resume = json.loads(resumed["inputs"]["resume"])
    assert resume["questions"][0] == {"question": "Em muốn ôn môn nào, chương nào?", "answer": "Toán – chương 2"}
    assert resume["skipped"] is False and resume["new_message"] == ""
    assert resumed["inputs"]["can_ask"] == "false"  # one clarify round per turn (FR-008)
    [_, synthesis] = dify.calls("/chat-messages")
    # The main Dify conversation gets the request and the extra information, not the question card (FR-031).
    assert synthesis["query"].startswith("Làm đề ôn tập cho em") and "Thông tin bổ sung" in synthesis["query"]
    assert "Toán – chương 2" in synthesis["query"]

    run = await the_run(sessionmaker, conversation_id)
    assert run.status == "done" and run.pending is None and run.expires_at is None
    assert run.resume_answers[1] == {"question": "Đề gồm bao nhiêu câu?", "answer": "10"}
    [step] = await rows(sessionmaker, RunStep)
    assert step.status == "done" and "10 câu" in step.task
    ask_message = (await rows(sessionmaker, ChatMessage, ChatMessage.status == "awaiting_user"))[0]
    assert ask_message.meta["ask"]["state"] == "answered"
    assert ask_message.meta["ask"]["answers"] == {"q1": "Toán – chương 2", "q2": "10"}
    [user_reply] = await rows(sessionmaker, ChatMessage, ChatMessage.role == "user", ChatMessage.content.like("%10"))
    assert user_reply.meta["reply_to"] == {"run_id": run.id, "ask_message_id": ask_message.id}


async def test_done_steps_are_kept_when_resuming(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room, _, conversation_id = await asked(as_user, dify)
    run = await the_run(sessionmaker, conversation_id)
    async with sessionmaker() as db:
        step = await db.get(RunStep, (await rows(sessionmaker, RunStep))[0].id)
        step.status, step.note = "done", "Ghi chú đã có."
        await db.commit()
    dify.planner = ANSWERED
    dify.runner = [deltas_sse("Kết quả.")]
    events = await answer(student, room, conversation_id, run.id, "Toán", answers={"q1": "Toán – chương 1"})
    [plan_event] = [e for e in events if e["type"] == "plan"]
    assert [(s["key"], s["status"]) for s in plan_event["steps"]] == [("s1", "done")]
    # Only the synthesis ran; it got the note that was already there.
    [synthesis] = dify.calls("/chat-messages")
    assert "Ghi chú đã có." in synthesis["inputs"]["system_prompt"]
    assert json.loads(dify.calls("#planner")[1]["inputs"]["resume"])["done_steps"][0]["key"] == "s1"


async def test_skip_all_goes_on_with_assumptions(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room, _, conversation_id = await asked(as_user, dify)
    run = await the_run(sessionmaker, conversation_id)
    dify.planner = ANSWERED
    dify.runner = [deltas_sse("Ghi chú.", conversation_id=""), deltas_sse("Đề.")]
    events = await answer(student, room, conversation_id, run.id, "Cứ làm luôn", skip_all=True)
    assert events[-1]["status"] == "ok"
    assert json.loads(dify.calls("#planner")[1]["inputs"]["resume"])["skipped"] is True
    [_, synthesis] = dify.calls("/chat-messages")
    assert "Giả định đã dùng" in synthesis["inputs"]["system_prompt"]
    assert "Em muốn ôn môn nào, chương nào?" in synthesis["inputs"]["system_prompt"]
    reply = (await rows(sessionmaker, ChatMessage, ChatMessage.role == "assistant", ChatMessage.status == "ok"))[0]
    assert "Đề trắc nghiệm, mức trung bình" in reply.meta["assumptions"]
    assert any("Đề gồm bao nhiêu câu?" in item for item in reply.meta["assumptions"])
    ask_message = (await rows(sessionmaker, ChatMessage, ChatMessage.status == "awaiting_user"))[0]
    assert ask_message.meta["ask"]["state"] == "skipped"


async def test_a_typed_answer_resumes_when_the_planner_reads_it_as_one(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room, _, conversation_id = await asked(as_user, dify)
    dify.planner = ANSWERED  # answers_pending = true
    dify.runner = [deltas_sse("Ghi chú.", conversation_id=""), deltas_sse("Đề.")]
    events = await chat(student, "Toán chương 2, 10 câu", class_id=room["id"], conversation_id=conversation_id)
    assert events[-1]["status"] == "ok" and notices(events) == []
    resume = json.loads(dify.calls("#planner")[1]["inputs"]["resume"])
    assert resume["new_message"] == "Toán chương 2, 10 câu"
    run = await the_run(sessionmaker, conversation_id)
    assert run.status == "done" and run.resume_answers[0]["answer"] == "Toán chương 2, 10 câu"


async def test_a_different_request_cancels_the_waiting_run(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room, _, conversation_id = await asked(as_user, dify)
    dify.planner = NEW_TOPIC  # answers_pending = false
    dify.runner = [deltas_sse("Ghi chú Pytago.", conversation_id=""), deltas_sse("Pytago là…")]
    events = await chat(student, "Thôi, giải thích Pytago đi", class_id=room["id"], conversation_id=conversation_id)
    assert notices(events) == ["pending_cancelled"]
    assert reply_text(events) == "Pytago là…" and events[-1]["status"] == "ok"
    runs = await rows(sessionmaker, TurnRun, TurnRun.conversation_id == conversation_id)
    assert sorted(run.status for run in runs) == ["cancelled", "done"]
    ask_message = (await rows(sessionmaker, ChatMessage, ChatMessage.status == "awaiting_user"))[0]
    assert ask_message.meta["ask"]["state"] == "cancelled"


async def test_only_one_question_round_per_turn(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room, _, conversation_id = await asked(as_user, dify)
    run = await the_run(sessionmaker, conversation_id)
    dify.planner = MISSING  # the planner asks again; the backend does not
    dify.runner = [deltas_sse("Ghi chú.", conversation_id=""), deltas_sse("Đề.")]
    events = await answer(student, room, conversation_id, run.id, "Toán", answers={"q1": "Toán – chương 1"})
    assert "ask" not in kinds(events) and events[-1]["status"] == "ok"
    run = await the_run(sessionmaker, conversation_id)
    assert run.clarify_rounds == 1 and run.status == "done"
    assert any("Đề gồm bao nhiêu câu?" in item for item in run.assumptions)


async def test_an_expired_question_is_a_new_request(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room, _, conversation_id = await asked(as_user, dify)
    run = await the_run(sessionmaker, conversation_id)
    async with sessionmaker() as db:
        await db.execute(
            update(TurnRun).where(TurnRun.id == run.id).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await db.commit()
    dify.planner = NEW_TOPIC
    dify.runner = [deltas_sse("Ghi chú.", conversation_id=""), deltas_sse("Trả lời mới.")]
    events = await answer(student, room, conversation_id, run.id, "Toán", answers={"q1": "Toán – chương 1"})
    assert notices(events) == ["pending_expired"]
    assert reply_text(events) == "Trả lời mới."
    # The planner was asked about a new request, not to resume.
    assert all(call["inputs"]["resume"] == "" for call in dify.calls("#planner"))
    runs = {r.id: r for r in await rows(sessionmaker, TurnRun, TurnRun.conversation_id == conversation_id)}
    assert runs[run.id].status == "expired" and runs[run.id].pending is None
    ask_message = (await rows(sessionmaker, ChatMessage, ChatMessage.status == "awaiting_user"))[0]
    assert ask_message.meta["ask"]["state"] == "expired"

    # A later reply to the expired run only gets the notice.
    events = await answer(student, room, conversation_id, run.id, "Toán", answers={"q1": "Toán – chương 1"})
    assert notices(events) == ["pending_expired"]


async def test_switching_multi_step_off_cancels_and_answers_fast(app, as_user, dify, sessionmaker) -> None:
    teacher, student, _, room, _, conversation_id = await asked(as_user, dify)
    run = await the_run(sessionmaker, conversation_id)
    url = f"/api/classes/{room['id']}/policy"
    await teacher.put(url, json={**(await teacher.get(url)).json(), "multi_step": False})
    dify.runner = [deltas_sse("Trả lời nhanh.")]
    events = await answer(student, room, conversation_id, run.id, "Toán", answers={"q1": "Toán – chương 1"})
    assert notices(events) == ["pending_cancelled"]
    assert events[-1]["path"] == "fast" and reply_text(events) == "Trả lời nhanh."
    assert (await the_run(sessionmaker, conversation_id)).status == "cancelled"


async def test_a_blocked_reply_cancels_the_run(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room, _, conversation_id = await asked(as_user, dify)
    run = await the_run(sessionmaker, conversation_id)
    dify.triage = triage_body("triage_block.json")
    events = await answer(student, room, conversation_id, run.id, "xấu", answers={"q1": "xấu"})
    assert events[-1]["status"] == "blocked"
    assert (await the_run(sessionmaker, conversation_id)).status == "cancelled"
    assert len(dify.calls("#planner")) == 1


async def test_withdrawn_consent_cancels_the_run(app, as_user, dify, sessionmaker) -> None:
    _, student, parent, room, _, conversation_id = await asked(as_user, dify)
    run = await the_run(sessionmaker, conversation_id)
    await parent.put(f"/api/parent/children/{student.user['id']}/consent", json={"allow_agents": False})
    events = await answer(student, room, conversation_id, run.id, "Toán", answers={"q1": "Toán – chương 1"})
    assert events[-1]["status"] == "consent_required"
    run = await the_run(sessionmaker, conversation_id)
    assert run.status == "cancelled" and run.pending is None


async def test_a_reply_for_another_run_is_handled_as_typed_text(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room, _, conversation_id = await asked(as_user, dify)
    dify.planner = NEW_TOPIC
    dify.runner = [deltas_sse("Ghi chú.", conversation_id=""), deltas_sse("Mới.")]
    events = await answer(student, room, conversation_id, "not-a-run", "Toán", answers={"q1": "Toán – chương 1"})
    # The planner judged the text (new_message set), found a new request, and the run was cancelled.
    assert json.loads(dify.calls("#planner")[1]["inputs"]["resume"])["new_message"] == "Toán"
    assert notices(events) == ["pending_cancelled"]
    [user_reply] = await rows(sessionmaker, ChatMessage, ChatMessage.role == "user", ChatMessage.content == "Toán")
    assert "reply_to" not in (user_reply.meta or {})


async def test_one_open_run_per_conversation(app, as_user, dify, sessionmaker) -> None:
    *_, conversation_id = await asked(as_user, dify)
    run = await the_run(sessionmaker, conversation_id)
    async with sessionmaker() as db:
        db.add(
            TurnRun(
                conversation_id=conversation_id, user_id=run.user_id, status="running", request_message_id="x"
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()


@pytest.mark.parametrize("kind", ["certify", "chat"])
async def test_without_a_person_the_run_never_pauses(app, as_user, dify, sessionmaker, kind) -> None:
    """Certification and eval (forced path) cannot answer: questions become assumptions (FR-041, research R14)."""
    _, student, _, room = await class_with_student(as_user)
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = MISSING
    dify.runner = [deltas_sse("Ghi chú.", conversation_id=""), deltas_sse("Đề.")]
    payload = ChatIn(message="Làm đề ôn tập cho em", class_id=room["id"])
    body = "".join(
        [
            chunk
            async for chunk in run_dify_turn(
                student.user["id"], room["id"], "student", payload, kind=kind, force_path="full"
            )
        ]
    )
    events = parse_sse(body)
    assert "ask" not in kinds(events) and events[-1]["status"] == "ok" and events[-1]["path"] == "full"
    [call] = dify.calls("#planner")
    assert call["inputs"]["interactive"] == "false" and call["inputs"]["can_ask"] == "false"
    [run] = await rows(sessionmaker, TurnRun)
    assert run.interactive is False and run.clarify_rounds == 0
    assert any("Em muốn ôn môn nào" in item for item in run.assumptions)


async def test_interpretation_is_confirmed_before_any_step(app, as_user, dify, sessionmaker) -> None:
    interpretation = "Em muốn một đề trắc nghiệm 10 câu Toán chương 2"
    confirm_plan = planner_body("planner_resume_answer.json", answers_pending=False, confirm_interpretation=interpretation)
    _, student, _, room, events, conversation_id = await asked(as_user, dify, confirm_plan)
    ask = events[-2]
    assert ask["type"] == "ask" and ask["kind"] == "confirm" and ask["skippable"] is False
    assert ask["confirm"]["summary"] == interpretation
    run = await the_run(sessionmaker, conversation_id)
    assert run.pending["confirm"]["source"] == "interpretation" and run.clarify_rounds == 1

    events = await answer(student, room, conversation_id, run.id, "Không", decision="reject")
    assert "mình chưa làm gì" in reply_text(events).lower() and events[-1]["status"] == "ok"
    assert dify.calls("/chat-messages") == []  # no step ran
    run = await the_run(sessionmaker, conversation_id)
    assert run.status == "cancelled"
    assert [s.status for s in await rows(sessionmaker, RunStep)] == ["pending"]
    ask_message = (await rows(sessionmaker, ChatMessage, ChatMessage.status == "awaiting_user"))[0]
    assert ask_message.meta["ask"]["state"] == "rejected"


async def test_an_approved_interpretation_runs_the_plan(app, as_user, dify, sessionmaker) -> None:
    interpretation = "Em muốn một đề trắc nghiệm 10 câu"
    confirm_plan = planner_body("planner_resume_answer.json", answers_pending=False, confirm_interpretation=interpretation)
    _, student, _, room, _, conversation_id = await asked(as_user, dify, confirm_plan)
    run = await the_run(sessionmaker, conversation_id)
    dify.runner = [deltas_sse("Ghi chú.", conversation_id=""), deltas_sse("Đề.")]
    events = await answer(student, room, conversation_id, run.id, "Đồng ý", decision="approve")
    assert events[-1]["status"] == "ok" and reply_text(events) == "Đề."
    assert len(dify.calls("#planner")) == 1  # the plan is already known
    [_, synthesis] = dify.calls("/chat-messages")
    assert interpretation in synthesis["query"]
    assert (await the_run(sessionmaker, conversation_id)).status == "done"


async def test_with_questions_and_an_interpretation_only_the_questions_are_asked(app, as_user, dify, sessionmaker) -> None:
    both = planner_body("planner_missing.json", confirm_interpretation="Em muốn đề trắc nghiệm")
    *_, events, conversation_id = await asked(as_user, dify, both)
    assert events[-2]["kind"] == "clarify"
    run = await the_run(sessionmaker, conversation_id)
    assert "Em muốn đề trắc nghiệm" in run.assumptions


async def test_resume_after_reloading_the_page(app, as_user, dify, sessionmaker) -> None:
    """SC-010: the card is rebuilt from the history and its run id resumes the run."""
    _, student, _, room, _, conversation_id = await asked(as_user, dify)
    history = (await student.get(f"/api/chat/conversations/{conversation_id}/messages")).json()
    [card] = [m for m in history if m["status"] == "awaiting_user"]
    ask = card["meta"]["ask"]
    assert ask["state"] == "open" and ask["kind"] == "clarify" and len(ask["questions"]) == 2
    dify.planner = ANSWERED
    dify.runner = [deltas_sse("Ghi chú.", conversation_id=""), deltas_sse("Đề.")]
    events = await answer(student, room, conversation_id, ask["run_id"], "Tiếng Anh", answers={"q1": "Tiếng Anh"})
    assert events[-1]["status"] == "ok" and [e for e in events if e["type"] == "plan"][0]["resumed"] is True


async def test_a_crashed_running_run_is_closed_but_a_waiting_one_is_not(app, as_user, dify, sessionmaker) -> None:
    """T089: only abandoned `running` runs are closed silently; a waiting run goes through resume with a notice."""
    _, student, _, room, _, conversation_id = await asked(as_user, dify)
    dify.planner = NEW_TOPIC
    dify.runner = [deltas_sse("Ghi chú.", conversation_id=""), deltas_sse("Mới.")]
    events = await chat(student, "Câu khác", class_id=room["id"], conversation_id=conversation_id)
    assert notices(events) == ["pending_cancelled"]
    ask_message = (await rows(sessionmaker, ChatMessage, ChatMessage.status == "awaiting_user"))[0]
    assert ask_message.meta["ask"]["state"] == "cancelled"
    # A run left `running` (a crashed turn) does not block the next full-path request.
    async with sessionmaker() as db:
        await db.execute(update(TurnRun).where(TurnRun.status == "done").values(status="running"))
        await db.commit()
    events = await chat(student, "Câu nữa", class_id=room["id"], conversation_id=conversation_id)
    assert events[-1]["status"] == "ok"
    statuses = sorted(r.status for r in await rows(sessionmaker, TurnRun))
    assert statuses == ["cancelled", "cancelled", "done"]
