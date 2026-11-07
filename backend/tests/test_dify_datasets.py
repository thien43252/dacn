"""Class documents in Dify knowledge bases (US5), offline: a fake Knowledge API that answers with recorded shapes."""

import asyncio
import json

import httpx
import pytest

from app.classes.models import ClassRoom
from app.knowledge import dify_datasets
from app.knowledge.models import Document
from app.tools import context as handles
from app.tools import registry
from tests.dify_fake import fixture_text
from tests.helpers import class_with_student
from tests.test_documents_tools import LESSON, upload


class FakeKnowledge:
    """Datasets, documents and indexing state in memory; every request is recorded."""

    def __init__(self) -> None:
        self.datasets: dict[str, list[str]] = {}  # dataset id -> Dify document ids
        self.status = "completed"  # what indexing-status reports
        self.fail_delete = False
        self.requests: list[tuple[str, str]] = []
        self.retrieved: list[str] = []  # dataset ids searched
        self.uploads = 0

    async def handler(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path.removeprefix("/v1"), request.method
        self.requests.append((method, path))
        parts = path.strip("/").split("/")
        if method == "POST" and path == "/datasets":
            name = json.loads(request.content)["name"]
            if len(name) > 40:  # Dify 1.19 refuses longer names with 422
                return httpx.Response(
                    422, json={"code": "invalid_param", "message": "String should have at most 40 characters"}
                )
            assert name.startswith("class-")
            dataset_id = f"ds-{len(self.datasets) + 1}"
            self.datasets[dataset_id] = []
            body = json.loads(fixture_text("dataset_create.json"))
            return httpx.Response(200, json={**body, "id": dataset_id, "name": json.loads(request.content)["name"]})
        dataset_id = parts[1]
        if dataset_id not in self.datasets:
            return httpx.Response(
                404, json={"code": "dataset_not_found", "message": "Dataset not found.", "status": 404}
            )
        if path.endswith("/document/create-by-file"):
            self.uploads += 1
            document_id = f"doc-{dataset_id}-{self.uploads}"
            self.datasets[dataset_id].append(document_id)
            body = json.loads(fixture_text("document_create.json"))
            body["document"]["id"] = document_id
            return httpx.Response(200, json={**body, "batch": f"batch-{document_id}"})
        if path.endswith("/indexing-status"):
            name = "indexing_status_completed.json" if self.status == "completed" else "indexing_status_error.json"
            body = json.loads(fixture_text(name))
            if self.status not in ("completed", "error"):
                body["data"][0]["indexing_status"] = self.status
            return httpx.Response(200, json=body)
        if path.endswith("/retrieve"):
            self.retrieved.append(dataset_id)
            body = json.loads(fixture_text("dataset_retrieve.json"))
            documents = self.datasets[dataset_id]
            for record in body["records"]:
                record["segment"]["document_id"] = documents[0] if documents else "none"
            body["records"] = body["records"] if documents else []
            return httpx.Response(200, json=body)
        if method == "DELETE" and len(parts) == 4:
            if self.fail_delete:
                return httpx.Response(500, json={"code": "internal_server_error", "message": "boom", "status": 500})
            if parts[3] not in self.datasets[dataset_id]:
                return httpx.Response(404, text=fixture_text("document_delete_missing.json"))
            self.datasets[dataset_id].remove(parts[3])
            return httpx.Response(204)
        return httpx.Response(404, json={"code": "not_found", "message": "unknown", "status": 404})


@pytest.fixture
def knowledge(dify, monkeypatch) -> FakeKnowledge:
    """The `dify` fixture switches the engine; this routes the Knowledge API to the fake."""
    fake = FakeKnowledge()
    monkeypatch.setattr(
        dify_datasets,
        "make_datasets",
        lambda: dify_datasets.DifyDatasets(httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))),
    )
    return fake


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
