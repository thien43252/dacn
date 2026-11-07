"""Class documents in Dify knowledge bases (US5), offline: a fake Knowledge API that answers with recorded shapes."""

import asyncio
import json

import pytest

from app.classes.models import ClassRoom
from app.knowledge import dify_datasets
from app.knowledge.models import Document
from app.tools import context as handles
from app.tools import registry
from tests.dify_fake import fixture_text
from tests.helpers import class_with_student
from tests.test_documents_tools import LESSON, upload


async def class_row(sessionmaker, class_id: str) -> ClassRoom:
    async with sessionmaker() as db:
        return await db.get(ClassRoom, class_id)


async def document_row(sessionmaker, document_id: str) -> Document:
    async with sessionmaker() as db:
        return await db.get(Document, document_id)


# --- T059: upload, status, reprocess, delete ----------------------------------------------------------------------


async def test_first_document_creates_the_class_knowledge_base(app, as_user, knowledge, sessionmaker) -> None:
    teacher, _, _, room = await class_with_student(as_user)
    created = (await upload(teacher, room["id"], "chuong3.txt", LESSON.encode(), "text/plain")).json()
    assert created["status"] == "processing"
    stored = await class_row(sessionmaker, room["id"])
    assert stored.dify_dataset_id == "ds-1"
    document = await document_row(sessionmaker, created["id"])
    assert document.dify_document_id == "doc-ds-1-1" and document.dify_batch == "batch-doc-ds-1-1"
    # A second document goes to the same knowledge base.
    await upload(teacher, room["id"], "chuong4.txt", LESSON.encode(), "text/plain")
    assert [p for m, p in knowledge.requests if m == "POST" and p == "/datasets"] == ["/datasets"]
    assert knowledge.datasets == {"ds-1": ["doc-ds-1-1", "doc-ds-1-2"]}


async def test_listing_follows_difys_indexing_status(app, as_user, knowledge) -> None:
    teacher, _, _, room = await class_with_student(as_user)
    knowledge.status = "indexing"
    await upload(teacher, room["id"], "chuong3.txt", LESSON.encode(), "text/plain")
    [listed] = (await teacher.get(f"/api/classes/{room['id']}/documents")).json()
    assert listed["status"] == "processing"
    knowledge.status = "completed"
    [listed] = (await teacher.get(f"/api/classes/{room['id']}/documents")).json()
    segments = json.loads(fixture_text("indexing_status_completed.json"))["data"][0]["total_segments"]
    assert listed["status"] == "ready" and listed["chunk_count"] == segments


async def test_indexing_error_marks_the_document_failed(app, as_user, knowledge) -> None:
    teacher, _, _, room = await class_with_student(as_user)
    knowledge.status = "error"
    await upload(teacher, room["id"], "hong.pdf", b"%PDF-1.4 broken", "application/pdf")
    [listed] = (await teacher.get(f"/api/classes/{room['id']}/documents")).json()
    assert listed["status"] == "failed" and "PDFium" in listed["error"] and len(listed["error"]) <= 500


async def test_reprocess_replaces_the_dify_document(app, as_user, knowledge, sessionmaker) -> None:
    teacher, _, _, room = await class_with_student(as_user)
    created = (await upload(teacher, room["id"], "chuong3.txt", LESSON.encode(), "text/plain")).json()
    response = await teacher.post(f"/api/classes/{room['id']}/documents/{created['id']}/reprocess")
    assert response.status_code == 200 and response.json()["status"] == "processing"
    assert ("DELETE", "/datasets/ds-1/documents/doc-ds-1-1") in knowledge.requests
    assert knowledge.datasets == {"ds-1": ["doc-ds-1-2"]}
    document = await document_row(sessionmaker, created["id"])
    assert document.dify_document_id == "doc-ds-1-2"


async def test_delete_removes_from_dify_first_and_keeps_the_row_if_dify_fails(app, as_user, knowledge) -> None:
    teacher, _, _, room = await class_with_student(as_user)
    created = (await upload(teacher, room["id"], "chuong3.txt", LESSON.encode(), "text/plain")).json()
    knowledge.fail_delete = True
    response = await teacher.delete(f"/api/classes/{room['id']}/documents/{created['id']}")
    assert response.status_code == 502 and "Dify" in response.json()["detail"]
    assert len((await teacher.get(f"/api/classes/{room['id']}/documents")).json()) == 1
    knowledge.fail_delete = False
    assert (await teacher.delete(f"/api/classes/{room['id']}/documents/{created['id']}")).status_code == 204
    assert knowledge.datasets == {"ds-1": []}
    assert (await teacher.get(f"/api/classes/{room['id']}/documents")).json() == []


# --- T060: class_doc_search on the class's knowledge base ---------------------------------------------------------


async def search_with(class_id: str | None, dataset_id: str | None, query: str = "so sánh phân số") -> dict:
    context = registry.ToolContext(
        user_id="u-1",
        role="student",
        class_id=class_id,
        grade=8,
        conversation_id=None,
        agent_slug="tro-ly-lop",
        allowed_tools=frozenset({"class_doc_search"}),
        dataset_id=dataset_id,
        events=asyncio.Queue(),
    )
    handle = handles.register(context)
    try:
        return json.loads(await registry.run_tool(handle, "class_doc_search", {"query": query}))
    finally:
        handles.release(handle)


async def test_search_uses_the_handles_dataset_and_maps_to_platform_documents(app, as_user, knowledge, sessionmaker):
    teacher, _, _, room = await class_with_student(as_user)
    created = (await upload(teacher, room["id"], "chuong3.txt", LESSON.encode(), "text/plain", "Bài 3")).json()
    result = await search_with(room["id"], "ds-1")
    assert knowledge.retrieved == ["ds-1"]
    [hit] = result["results"]
    assert set(hit) == {"document_id", "title", "location", "score", "content"}
    assert hit["document_id"] == created["id"] and hit["title"] == "Bài 3" and "Phân số" in hit["content"]
    assert "note" in result


async def test_class_b_handle_never_reaches_class_a_documents(app, as_user, knowledge, sessionmaker) -> None:
    teacher, _, _, room_a = await class_with_student(as_user)
    room_b = (await teacher.post("/api/classes", json={"name": "Lớp B", "subject": "toan", "grade": 8})).json()
    await upload(teacher, room_a["id"], "chuong3.txt", LESSON.encode(), "text/plain")
    # Class B has no knowledge base yet: nothing is searched at all.
    result = await search_with(room_b["id"], None)
    assert result["results"] == [] and knowledge.retrieved == []
    # The model cannot pick a dataset: an argument naming class A's is ignored, the handle decides.
    context = registry.ToolContext(
        "u-1", "student", room_b["id"], 8, None, "tro-ly-lop", frozenset({"class_doc_search"})
    )
    handle = handles.register(context)
    try:
        smuggled = await registry.run_tool(handle, "class_doc_search", {"query": "phân số", "dataset_id": "ds-1"})
    finally:
        handles.release(handle)
    assert json.loads(smuggled)["results"] == [] and knowledge.retrieved == []


async def test_personal_chat_cannot_search_documents(app, knowledge) -> None:
    with pytest.raises(Exception, match="trong một lớp"):
        await search_with(None, "ds-1")
    assert knowledge.retrieved == []


@pytest.mark.dify
async def test_real_dify_keeps_class_knowledge_bases_apart(app, as_user, sessionmaker, monkeypatch) -> None:
    """SC-007 on a real Dify: a document in class A's knowledge base is not found from class B's handle."""
    from app.config import get_settings

    monkeypatch.setenv("RUNTIME_ENGINE", "dify")
    get_settings.cache_clear()
    teacher, _, _, room_a = await class_with_student(as_user)
    room_b = (await teacher.post("/api/classes", json={"name": "Lớp B", "subject": "toan", "grade": 8})).json()
    secret = "Mật danh của lớp A là con cú xanh lá cây số 47."
    await upload(teacher, room_a["id"], "bi-mat.txt", (LESSON + "\n\n" + secret).encode(), "text/plain")
    await upload(teacher, room_b["id"], "chuong3.txt", LESSON.encode(), "text/plain")
    for _ in range(60):
        listed = (await teacher.get(f"/api/classes/{room_a['id']}/documents")).json()
        listed += (await teacher.get(f"/api/classes/{room_b['id']}/documents")).json()
        if all(d["status"] != "processing" for d in listed):
            break
        await asyncio.sleep(1)
    a = await class_row(sessionmaker, room_a["id"])
    b = await class_row(sessionmaker, room_b["id"])
    try:
        assert "con cú" in json.dumps(
            await search_with(room_a["id"], a.dify_dataset_id, "mật danh của lớp"), ensure_ascii=False
        )
        found_b = await search_with(room_b["id"], b.dify_dataset_id, "mật danh của lớp con cú xanh")
        assert "con cú" not in json.dumps(found_b, ensure_ascii=False)
    finally:
        client = dify_datasets.make_datasets()
        for dataset in (a.dify_dataset_id, b.dify_dataset_id):
            if dataset:
                await client.delete_dataset(dataset)
        await client.http.aclose()
        get_settings.cache_clear()
