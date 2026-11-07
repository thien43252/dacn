"""Class documents in Dify knowledge bases, one per class (research R7, contracts/dify-apps.md section 4).

Only the backend talks to this API, with DIFY_DATASET_KEY; the dataset id always comes from the class row (or the
turn's tool handle), never from a model, so class B cannot read class A's documents (FR-020, FR-021a).
Response shapes were recorded from Dify 1.19 (backend/tests/fixtures/dify/dataset_*.json, document_*.json,
indexing_status_*.json).
"""

import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings, get_settings

PROCESS = json.dumps({"indexing_technique": "high_quality", "process_rule": {"mode": "automatic"}})


class DifyDatasetError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class IndexingStatus:
    # waiting | parsing | cleaning | splitting | indexing | paused | completed | error
    status: str
    segments: int
    error: str | None


@dataclass
class Record:
    dify_document_id: str
    document_name: str
    position: int
    content: str
    score: float


@dataclass
class Segment:
    position: int
    content: str


def dataset_name(class_id: str) -> str:
    """`class-<class id without hyphens>`: Dify caps dataset names at 40 characters, a UUID with hyphens is 36."""
    return f"class-{class_id.replace('-', '')}"


class DifyDatasets:
    def __init__(self, http: httpx.AsyncClient, settings: Settings | None = None) -> None:
        self.http = http
        self.settings = settings or get_settings()
        self.base = self.settings.dify_base_url.rstrip("/") + "/v1"
        self.headers = {"Authorization": f"Bearer {self.settings.dify_dataset_key}"}

    async def _call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self.http.request(
                method, f"{self.base}{path}", headers=self.headers, timeout=self.settings.dify_timeout_s, **kwargs
            )
        except httpx.HTTPError as error:
            raise DifyDatasetError(f"Không kết nối được Dify ({type(error).__name__}).") from error
        if response.status_code >= 400:
            try:
                message = str(response.json().get("message") or response.text)
            except ValueError:
                message = response.text
            raise DifyDatasetError(f"Dify {response.status_code}: {message[:300]}", response.status_code)
        return response

    async def create_dataset(self, class_id: str) -> str:
        response = await self._call(
            "POST",
            "/datasets",
            json={"name": dataset_name(class_id), "indexing_technique": "high_quality", "permission": "only_me"},
        )
        return response.json()["id"]

    async def upload_document(self, dataset_id: str, filename: str, data: bytes, content_type: str) -> tuple[str, str]:
        """Returns (Dify document id, indexing batch)."""
        response = await self._call(
            "POST",
            f"/datasets/{dataset_id}/document/create-by-file",
            data={"data": PROCESS},
            files={"file": (filename, data, content_type)},
        )
        body = response.json()
        return body["document"]["id"], body["batch"]

    async def indexing_status(self, dataset_id: str, batch: str) -> IndexingStatus:
        response = await self._call("GET", f"/datasets/{dataset_id}/documents/{batch}/indexing-status")
        [item] = response.json()["data"][:1] or [{}]
        return IndexingStatus(
            status=str(item.get("indexing_status") or "waiting"),
            segments=int(item.get("total_segments") or item.get("completed_segments") or 0),
            error=item.get("error"),
        )

    async def segments(self, dataset_id: str, document_id: str, limit: int = 200) -> list[Segment]:
        """The chunks Dify made of one document, in order (the teacher's preview), at most `limit`."""
        found: list[Segment] = []
        page = 1
        while len(found) < limit:
            response = await self._call(
                "GET",
                f"/datasets/{dataset_id}/documents/{document_id}/segments",
                params={"page": page, "limit": 100},
            )
            body = response.json()
            found.extend(
                Segment(position=int(item.get("position") or 0), content=str(item.get("content") or ""))
                for item in body.get("data", [])
            )
            if not body.get("has_more"):
                break
            page += 1
        return sorted(found, key=lambda segment: segment.position)[:limit]

    async def delete_document(self, dataset_id: str, document_id: str) -> None:
        """Deleting a document Dify no longer has counts as done."""
        try:
            await self._call("DELETE", f"/datasets/{dataset_id}/documents/{document_id}")
        except DifyDatasetError as error:
            if error.status != 404:
                raise

    async def delete_dataset(self, dataset_id: str) -> None:
        try:
            await self._call("DELETE", f"/datasets/{dataset_id}")
        except DifyDatasetError as error:
            if error.status != 404:
                raise

    async def retrieve(self, dataset_id: str, query: str, top_k: int) -> list[Record]:
        response = await self._call(
            "POST",
            f"/datasets/{dataset_id}/retrieve",
            json={
                "query": query,
                "retrieval_model": {
                    "search_method": "semantic_search",
                    "reranking_enable": False,
                    "top_k": top_k,
                    "score_threshold_enabled": False,
                },
            },
        )
        records = []
        for item in response.json().get("records", []):
            segment = item.get("segment") or {}
            document = segment.get("document") or {}
            records.append(
                Record(
                    dify_document_id=str(segment.get("document_id") or document.get("id") or ""),
                    document_name=str(document.get("name") or ""),
                    position=int(segment.get("position") or 0),
                    content=str(segment.get("content") or ""),
                    score=float(item.get("score") or 0.0),
                )
            )
        return records


def make_datasets() -> DifyDatasets:
    """One client per operation; tests replace this with one over httpx.MockTransport."""
    return DifyDatasets(httpx.AsyncClient())
