"""Conversation event stream (research R2): seq ordering, replay after a given seq, viewer filtering, 404 outside."""

from app.chat import events
from tests.helpers import chat, class_with_student, conversation_id_of


async def test_seq_is_increasing_and_replay_follows_after(as_user, fake_llm, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user)
    first = await chat(student, "Câu một", class_id=room["id"], agent="tro-ly-lop")
    conversation_id = conversation_id_of(first)
    await chat(student, "Câu hai", class_id=room["id"], conversation_id=conversation_id)
    messages = (await student.get(f"/api/chat/conversations/{conversation_id}/messages")).json()
    seqs = [m["seq"] for m in messages]
    assert seqs == sorted(seqs) == list(range(1, len(seqs) + 1))
    assert first[-1]["seq"] == 2

    async with sessionmaker() as db:
        replay = await events.stored_events(db, conversation_id, student.user["id"], after=2)
    assert [event["seq"] for event in replay] == [3, 4]


async def test_visible_to_filters_replay(as_user, fake_llm, sessionmaker) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    other = await as_user("student")
    await other.post("/api/classes/join", json={"code": room["join_code"]})
    group = (
        await teacher.post(
            "/api/chat/groups",
            json={
                "class_id": room["id"],
                "title": "Lớp",
                "members": [student.user["id"], other.user["id"]],
                "agents": ["tro-ly-lop"],
            },
        )
    ).json()
    await chat(student, "Mình mệt mỏi lắm, không muốn sống nữa.", class_id=room["id"], conversation_id=group["id"])
    async with sessionmaker() as db:
        mine = await events.stored_events(db, group["id"], student.user["id"])
        theirs = await events.stored_events(db, group["id"], other.user["id"])
    assert len(mine) > len(theirs)


async def test_outsiders_get_404_on_events(as_user) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    conversation_id = conversation_id_of(await chat(student, "Xin chào", class_id=room["id"]))
    assert (await teacher.get(f"/api/chat/conversations/{conversation_id}/events")).status_code == 404


def test_publish_reaches_only_listed_viewers() -> None:
    listener_a, listener_b = events._Listener("a"), events._Listener("b")
    events._listeners["c1"].update({listener_a, listener_b})
    try:
        events.publish("c1", {"type": "message"}, visible_to=["a"])
        assert listener_a.queue.qsize() == 1 and listener_b.queue.qsize() == 0
    finally:
        events._listeners.pop("c1", None)
