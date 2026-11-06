# Implementation Plan: Chuyển lõi agent sang Dify và tích hợp tính năng Dify

**Branch**: `feat/dify-runtime` | **Date**: 2026-11-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-dify-core-migration/spec.md`

## Summary

Thay lõi LangGraph (`backend/app/runtime/graph.py`) bằng Dify. Mỗi lượt chat gọi hai ứng dụng Dify:

- `eduagent-triage` (Workflow): phân loại an toàn và định tuyến chọn agent, chạy song song trong workflow.
- `eduagent-runner` (Chatflow): chạy agent với tool MCP, kiểm duyệt đầu vào/đầu ra cấp ứng dụng, bộ nhớ hội thoại
  và gợi ý câu hỏi.

Backend chỉ giữ những gì Dify không làm được hoặc thuộc về nền tảng:
- tài khoản, lớp, đồng ý của phụ huynh, Hub, phiên bản agent;
- ẩn thông tin cá nhân trước khi gửi đi;
- phân quyền tool qua MCP HTTP;
- ghi nhật ký, chi phí;
- đồng bộ tài liệu lớp sang kho tri thức Dify (mỗi lớp một kho).

Giao thức SSE với web giữ nguyên, thêm hai sự kiện `citations` và `suggestions`. Engine cũ nằm sau cờ
`RUNTIME_ENGINE` cho tới khi so sánh xong, rồi bị xóa.

Chi tiết quyết định: [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript + React 19 (web)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic, `httpx` (client Dify), `mcp` (server streamable
HTTP); Dify self-host (bản ổn định ≥ 1.13.3, ghim trong `infra/dify/README.md`). Bỏ `langgraph` ở bước dọn dẹp.

**Storage**: PostgreSQL (dữ liệu nền tảng, bản sao hội thoại); Dify (bộ nhớ hội thoại, kho tri thức từng lớp).
pgvector chỉ còn dùng cho engine cũ.

**Testing**: pytest (offline, `httpx.MockTransport` + fixture SSE/JSON ghi từ Dify thật), `@pytest.mark.dify` cho
test tích hợp tùy chọn; vitest + Playwright cho web.

**Target Platform**: Máy demo local (Windows + Docker Desktop), Dify chạy container riêng ở `127.0.0.1:8080`.

**Project Type**: Web application (backend FastAPI + web React).

**Performance Goals**: chữ đầu tiên ≤ 3 giây ở p95 khi chạy local (SC-004).

**Constraints**: test không cần Dify (FR-027); không gửi thông tin cá nhân sang Dify (FR-011); Dify dùng ~4 GB RAM;
cấu hình Dify phải dựng lại được từ repo (FR-026).

**Scale/Scope**: một workspace Dify, dữ liệu demo (4 tài khoản, vài lớp, 7 agent nền tảng + agent giáo viên); 3
ứng dụng Dify; 1 migration; khoảng 15 file backend và 4 file web thay đổi.

Không còn mục NEEDS CLARIFICATION. Các điểm phụ thuộc hành vi Dify thực tế được gom vào spike (research R12).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

File `.specify/memory/constitution.md` hiện chỉ có nguyên tắc I và II. Phần báo cáo ở đầu file nhắc tới nguyên tắc
III–V, nhưng phần nội dung không có, nên plan chỉ chấm theo I và II.

| Nguyên tắc | Trước Phase 0 | Sau Phase 1 | Ghi chú |
|---|---|---|---|
| I. Tài liệu và spec viết bằng tiếng Việt | Đạt | Đạt | plan, research, data-model, contracts, quickstart đều bằng tiếng Việt; tên định danh, API, khóa cấu hình giữ tiếng Anh như nguyên tắc cho phép |
| II. Không tự commit | Đạt | Đạt | `/speckit-plan` chỉ ghi file vào working tree; không có hook tự commit (`.specify/extensions.yml` không tồn tại) |

**Kết quả**: qua gate, không có vi phạm cần giải trình.

Feature có nới các biện pháp an toàn hiện có (bỏ chủ đề cấm theo lớp, bỏ LLM review "không đưa đáp án"). Thay đổi
này đến từ clarification của người dùng, không vi phạm nguyên tắc nào đang có hiệu lực. Nếu nguyên tắc III ("An
toàn học sinh là lõi, không được nới lỏng") được bổ sung vào constitution như phần báo cáo nhắc tới, hai thay đổi
này phải được giải trình lại trong Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/001-dify-core-migration/
├── plan.md              # File này
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── dify-apps.md     # input/output của triage, runner, runner-raw, Knowledge API
│   ├── chat-sse.md      # SSE giữa backend và web (+ citations, suggestions, context_reset)
│   └── mcp-tools.md     # MCP qua HTTP, kiểm tra quyền tool
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks tạo, không phải /speckit-plan
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── config.py                 # + runtime_engine, dify_*, mcp_token, mcp_public_url
│   ├── main.py                   # mount /mcp; /api/health báo engine
│   ├── runtime/
│   │   ├── engine.py             # MỚI: run_turn() chọn langgraph | dify
│   │   ├── dify_client.py        # MỚI: triage (blocking), runner (SSE), stop, suggested, ánh xạ sự kiện
│   │   ├── dify_turn.py          # MỚI: lượt chat trên Dify (redact → triage → handle → runner → lưu)
│   │   ├── prompts.py            # bỏ blocked_topics; dùng chung cho cả hai engine
│   │   ├── graph.py, router.py   # engine cũ; xóa ở bước dọn dẹp
│   ├── tools/
│   │   ├── server.py             # streamable HTTP + bearer token; guard và log chuyển vào handler
│   │   ├── registry.py           # guard() dùng chung; execute() của engine cũ gọi cùng handler
│   │   ├── context.py            # handle có TTL, hàng đợi sự kiện tool, citations
│   │   └── impl.py               # class_doc_search, quiz_generator đọc kho Dify
│   ├── knowledge/
│   │   ├── dify_datasets.py      # MỚI: tạo kho, tải lên, trạng thái, xóa, retrieve
│   │   ├── service.py, router.py # đồng bộ sang Dify khi engine = dify
│   ├── guard/rules.py            # giữ redact(); phần chặn xóa ở bước dọn dẹp
│   ├── guard/classifier.py       # xóa ở bước dọn dẹp
│   ├── classes/{router,schemas}.py  # bỏ blocked_topics
│   ├── chat/router.py            # gọi engine.run_turn(); lưu dify_conversation_id, citations, suggestions
│   ├── certify/pipeline.py       # gọi engine; runner-raw, hội thoại mới mỗi tình huống
│   └── agents/router.py          # sandbox gọi engine.run_turn()
├── migrations/versions/0006_dify_runtime.py   # MỚI
├── scripts/seed_demo.py          # đẩy tài liệu demo sang Dify khi engine = dify
└── tests/
    ├── fixtures/dify/            # MỚI: *.sse, *.json ghi từ spike
    ├── test_runtime_dify.py      # MỚI
    ├── test_mcp_http.py          # MỚI
    ├── test_dify_datasets.py     # MỚI
    └── test_chat.py, test_certify.py, test_documents_tools.py, test_classes.py  # cập nhật

web/src/
├── components/ChatPanel.tsx          # xử lý citations, suggestions, notice context_reset
├── components/chat/MessageBody.tsx   # hiển thị trích dẫn và nút câu hỏi gợi ý
├── features/classes/PolicyTab.tsx    # bỏ ô chủ đề cấm
└── api-client/types.ts               # bỏ blocked_topics; kiểu cho citations/suggestions

infra/dify/                       # MỚI
├── README.md                     # ghim phiên bản, cổng, mạng, import DSL, ghi chú spike
├── eduagent-triage.yml
├── eduagent-runner.yml
├── eduagent-runner-raw.yml
├── moderation-keywords.txt       # nguồn duy nhất của bộ từ khóa kiểm duyệt
└── preset-responses.json         # câu trả lời cài sẵn khi bị chặn

eval/run_redteam.py, run_routing.py, run_certify.py   # thêm --engine, cột engine trong kết quả
.env.example, README.md, docs/PLAN-DIFY.md, docs/BAO-CAO.md  # cập nhật
```

**Structure Decision**: Giữ cấu trúc web application hiện có (`backend/`, `web/`, `infra/`, `eval/`). Code Dify
nằm trong `app/runtime/` và `app/knowledge/`, đúng ranh giới module hiện tại. Cấu hình Dify nằm trong `infra/dify/`
cạnh `infra/docker-compose.yml`.

## Thứ tự triển khai

| Bước | Nội dung | Điều kiện xong | Story |
|---|---|---|---|
| 0 | Spike Dify: trả lời 6 câu hỏi ở research R12, ghi fixture | `infra/dify/README.md` có ghi chú spike; dừng nếu không đạt | — |
| 1 | `engine.py` + cờ cấu hình; chat, sandbox, certify gọi `run_turn()` | test hiện có pass với `langgraph` | — |
| 2 | MCP qua HTTP: guard và log trong handler, handle có TTL, hàng đợi sự kiện tool | test MCP HTTP pass; engine cũ dùng cùng handler | US1 |
| 3 | DSL triage + runner; `dify_client`, `dify_turn`; migration 0006 | demo chat với `dify`; thứ tự SSE đúng | US1, US2 |
| 4 | Guard: bộ phân loại, kiểm duyệt cấp ứng dụng, ánh xạ `guard_events`, `context_reset`, stop; bỏ `blocked_topics` | kịch bản 4–6, 9, 11, 13–14 của quickstart | US2 |
| 5 | Kho tri thức: `dify_datasets.py`, đồng bộ tài liệu, `class_doc_search` qua Dify, seed | kịch bản 8; SC-007 | US5 |
| 6 | Citations + suggestions (backend + web) | kịch bản 7 | US4 |
| 7 | Kiểm định qua runner-raw; sandbox | kịch bản 10 | US3 |
| 8 | Usage `triage`/`agent`, tracing, `--engine` cho eval; chạy so sánh | bảng so sánh trong `docs/BAO-CAO.md` | US6 |
| 9 | Dọn dẹp: mặc định `dify`, xóa engine cũ, `document_chunks`, `langgraph`; cập nhật tài liệu | `grep langgraph` rỗng; README dựng được từ đầu | — |

## Rủi ro

| Rủi ro | Ảnh hưởng | Giảm thiểu |
|---|---|---|
| Fixed Value không nhận biến cho tham số `ctx` | mô hình thấy handle | dự phòng R6: handle ngắn hạn trong prompt, server kiểm tra |
| Guard của Dify yếu hơn guard cũ với tiếng Việt | tỉ lệ chặn giảm | từ khóa có dấu và không dấu; đo ở bước 8; báo người dùng nếu vượt ngưỡng SC-002 |
| Hai lần gọi Dify làm tăng độ trễ | trượt SC-004 | đo ở spike; triage dùng model nhỏ và blocking ngắn |
| Dify đổi API/tên sự kiện giữa các bản | gãy stream | ghim phiên bản; fixture ghi sẵn |
| Dữ liệu nằm ở hai nơi (Postgres + Dify) | lệch trạng thái | Dify chỉ giữ bộ nhớ hội thoại và kho tri thức; nguồn sự thật cho hiển thị và nhật ký vẫn là Postgres |

## Complexity Tracking

Không có vi phạm constitution cần giải trình.
