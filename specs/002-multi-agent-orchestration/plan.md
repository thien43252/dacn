# Implementation Plan: Xử lý yêu cầu nhiều bước với nhiều agent phối hợp

**Branch**: `002-multi-agent-orchestration` (chưa tạo; đang làm trên `feat/dify-runtime`) | **Date**: 2026-11-10 |
**Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-multi-agent-orchestration/spec.md`

## Summary

Biến mỗi lượt chat từ chuỗi cố định "triage → một agent → review" thành một quá trình có trạng thái. Câu hỏi đơn
giản vẫn đi **đường nhanh** như hiện nay. Yêu cầu phức tạp đi **đường đầy đủ**:

```
triage (an toàn + path) ─fast─▶ runner (1 agent) ─▶ review ─▶ kết quả           [không đổi]
        └─full─▶ planner ─▶ [hỏi lại / xác nhận → lưu turn_runs, dừng; lượt sau làm tiếp]
                        ─▶ phần việc của nhiều agent (song song theo phụ thuộc, tool tín hiệu → lập lại kế hoạch)
                        ─▶ tổng hợp (agent chính, stream) ─▶ review ─▶ một kết quả ngắn gọn + khung quá trình
```

Cách làm:
- **Backend điều phối, Dify chạy việc.** Module mới `backend/app/orchestrator/` giữ trạng thái và giới hạn.
- **Dify:** thêm nhánh `path` song song trong triage (không làm chậm đường nhanh); thêm app `eduagent-planner`;
  runner được dùng lại cho cả phần việc (hội thoại Dify riêng) lẫn bước tổng hợp (hội thoại chính).
- **Agent báo nhu cầu bằng tool tín hiệu.** Có 3 tool `request_help`, `ask_user`, `request_confirmation`. Handler chỉ
  ghi nhận rồi trả về ngay; backend xếp việc tiếp theo, nên không có lời gọi lồng nhau.
- **Xác nhận do nền tảng ép buộc.** Guard không chạy tool cần xác nhận; sau khi người dùng bấm "Đồng ý", backend tự
  chạy tool với đúng tham số đã lưu, đúng một lần.
- **Bộ tool cần xác nhận cho giáo viên** (bổ sung theo yêu cầu, R18): `save_class_document`, `set_agent_notes`,
  `install_agent`, `post_class_announcement`, `assign_practice`. Mỗi tool có phần xem trước, kiểm duyệt nội dung
  trước khi xin xác nhận, và gỡ lại được. Có thêm 2 bảng `class_announcements`, `assignments` và tab "Bảng tin" trên
  trang lớp.
- **Giao diện:** SSE có thêm `plan`, `step`, `ask`; web có thêm khung tiến trình, thẻ hỏi lại và xác nhận (chuyển thể
  từ `QuestionCard.tsx` có sẵn nhưng chưa dùng), và công tắc theo lớp.

Chi tiết quyết định: [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript + React 19 (web)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic, `httpx` (client Dify), `mcp` (server streamable HTTP);
Dify self-host 1.19.0 (đã ghim trong `infra/dify/README.md`), plugin `langgenius/agent`. Không thêm dependency mới.

**Storage**: PostgreSQL. Bảng mới `turn_runs`, `run_steps`, `class_announcements`, `assignments`; `usage_ledger.path`; khóa mới trong JSON
(`chat_messages.meta`, `classes.policy`). Dify giữ bộ nhớ hội thoại chính và các hội thoại phần việc.

**Testing**: pytest offline (SQLite in-memory, `httpx.MockTransport` + fixture ghi từ Dify 1.19.0); vitest cho web;
eval có kết nối Dify thật (`eval/run_planning.py`).

**Target Platform**: Máy demo local (Windows + Docker Desktop), Dify ở `127.0.0.1:8080`.

**Project Type**: Web application (backend FastAPI + web React).

**Performance Goals**:
- Đường nhanh: thời gian tới chữ đầu (trung vị) tăng ≤ 10% (SC-001).
- Đường đầy đủ: cập nhật đầu tiên của khung tiến trình ≤ 3 giây (SC-006).
- Thời gian tới kết quả cuối của đường đầy đủ chỉ đo, không đặt ngưỡng (clarify Q4).

**Constraints**:
- `system_prompt` của runner ≤ 12000 ký tự.
- Proxy SSRF của Dify đọc tối đa 60 giây mỗi lần gọi MCP, nên tool không được chờ lâu (R5).
- Không có hạn mức số lượt theo người dùng (clarify Q2).
- Test không cần Dify.
- Không gửi thông tin cá nhân sang Dify.
- Một hội thoại có tối đa một run đang mở.

**Scale/Scope**: dữ liệu demo (7 agent mẫu, vài lớp); 1 app Dify mới và 3 DSL sửa; 1 migration; khoảng 15 file backend
mới hoặc sửa (gồm module `class_feed`), khoảng 10 file web; 5 tool cần xác nhận + 1 tool thử; bộ eval khoảng 60 ca.

Không còn mục NEEDS CLARIFICATION.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Nguyên tắc | Trước Phase 0 | Sau Phase 1 | Ghi chú |
|---|---|---|---|
| I. Tài liệu và spec viết bằng tiếng Việt | Đạt | Đạt | plan, research, data-model, contracts, quickstart bằng tiếng Việt; định danh, API, khóa cấu hình giữ tiếng Anh |
| II. Không tự commit | Đạt | Đạt | chỉ ghi file vào working tree; không có `.specify/extensions.yml` nên không có hook tự commit |
| III. `dev.ps1` luôn chạy được bản mới nhất | Đạt (có điều kiện) | Đạt | feature thêm biến bắt buộc `DIFY_PLANNER_KEY`, migration `0008` (gồm 2 bảng của bộ tool xác nhận) và app Dify mới. Bước 8 cập nhật `dev.ps1`: kiểm tra và cảnh báo khi thiếu khóa Dify (gồm khóa mới); migration đã có sẵn qua `alembic upgrade head`. README mục chạy local và `infra/dify/README.md` (import planner) cập nhật cùng lúc. `tasks.md` phải có task này |

**Kết quả**: qua gate, không có vi phạm cần giải trình.

## Project Structure

### Documentation (this feature)

```text
specs/002-multi-agent-orchestration/
├── plan.md              # File này
├── research.md          # Phase 0: R1–R17
├── data-model.md        # Phase 1: turn_runs, run_steps, thay đổi bảng cũ, máy trạng thái
├── quickstart.md        # Phase 1: 29 kịch bản + lệnh đo
├── contracts/
│   ├── chat-sse.md      # reply trong ChatIn; plan/step/ask; awaiting_user; API ghi chú; policy.multi_step
│   ├── dify-apps.md     # triage.path; eduagent-planner; runner (tool tín hiệu, 3 cách gọi); review cho ghi chú
│   ├── mcp-tools.md     # tool tín hiệu, tool cần xác nhận (5 tool giáo viên + confirm_probe)
│   └── class-actions.md # REST cho thông báo lớp và bài luyện; giao diện Bảng tin
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks tạo, không phải /speckit-plan
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── config.py                    # + dify_planner_key, orch_*, enable_test_tools
│   ├── main.py                      # health: orchestrator on/off; router ghi chú
│   ├── orchestrator/                # MỚI
│   │   ├── __init__.py
│   │   ├── models.py                # TurnRun, RunStep (SQLAlchemy)
│   │   ├── planner.py               # gọi eduagent-planner, kiểm tra/cắt kế hoạch (contracts/dify-apps.md §2)
│   │   ├── steps.py                 # chạy DAG phần việc, timeout, đọc stream runner thành ghi chú, xử lý tín hiệu
│   │   ├── conductor.py             # máy trạng thái của run: bắt đầu, dừng hỏi, làm tiếp, huỷ, hết hạn, tổng hợp
│   │   ├── prompts.py               # khối STEP_MODE, SYNTHESIS_MODE; dựng query phần việc/tổng hợp
│   │   └── notes.py                 # review lười ghi chú + endpoint GET …/steps/{key}/note
│   ├── runtime/
│   │   ├── dify_turn.py             # tách _stream_runner() khỏi _answer(); rẽ nhánh fast/full sau triage; xử lý reply
│   │   ├── dify_client.py           # TriageResult.path; run_planner(); PlannerResult
│   │   └── prompts.py               # roster mở rộng (tools, is_fallback) cho planner
│   ├── tools/
│   │   ├── registry.py              # PlatformTool.requires_confirmation/signal/confirm_template/preview/share_review;
│   │   │                            #   ToolContext mở rộng; guard 2a, 6a, 6b, 7; confirm_probe khi enable_test_tools
│   │   ├── impl.py                  # request_help, ask_user, request_confirmation (ghi tín hiệu), confirm_probe
│   │   ├── actions.py               # MỚI: 5 tool giáo viên: args, preview(), execute() (R18)
│   │   └── server.py                # đăng ký 3 tool tín hiệu + 5 tool giáo viên với ctx
│   ├── class_feed/                  # MỚI: thông báo lớp + bài luyện
│   │   ├── models.py                # ClassAnnouncement, Assignment
│   │   └── router.py                # contracts/class-actions.md
│   ├── agents/service.py            # tách install_in_class() khỏi router để tool install_agent dùng lại
│   ├── knowledge/service.py         # create_text_document() cho save_class_document
│   ├── chat/router.py               # ChatIn.reply; usage có path; MessageOut giữ nguyên
│   ├── classes/schemas.py           # PolicyModel.multi_step
│   └── reports/service.py           # nhóm usage theo path
├── migrations/versions/0008_orchestration.py   # MỚI
└── tests/
    ├── fixtures/dify/               # + triage_path_*.json, planner_*.json, runner_step_*.sse
    ├── test_orchestrator.py         # MỚI: chọn đường, kế hoạch, DAG, giới hạn, tổng hợp, ghi chú, SSE
    ├── test_orchestrator_resume.py  # MỚI: dừng/làm tiếp/huỷ/hết hạn/đổi chủ đề/công tắc lớp/consent
    ├── test_signal_tools.py         # MỚI: tool tín hiệu, độ sâu nhờ, confirm_probe
    ├── test_confirm_tools.py        # MỚI: 5 tool giáo viên: quyền, xem trước, kiểm duyệt, chạy một lần, từ chối/hết hạn
    ├── test_class_actions.py        # MỚI: API thông báo/bài luyện, ai xem được gì, answer_key
    └── test_runtime_dify.py, test_dify_dsl.py, test_classes.py, test_reports.py   # cập nhật

web/src/
├── api-client/types.ts              # kiểu plan/step/ask, meta mới, ClassPolicy.multi_step
├── components/chat/ChatThread.tsx   # xử lý plan/step/ask/awaiting_user; gửi reply
├── components/chat/ProcessPanel.tsx # MỚI: khung tiến trình, thu gọn, mở ghi chú
├── components/chat/AskCard.tsx      # MỚI (chuyển thể từ QuestionCard.tsx; xoá QuestionCard nếu không còn dùng)
├── components/chat/MessageBody.tsx  # dòng tóm tắt quá trình + chip agent đóng góp + giả định
├── features/classes/PolicyTab.tsx   # công tắc multi_step
├── features/classes/ClassFeedTab.tsx      # MỚI: tab Bảng tin (thông báo + bài luyện; giáo viên đăng/xoá)
├── features/classes/StudentClassesPage.tsx, StudentHomePage.tsx   # thông báo, bài luyện, "Làm cùng gia sư"
├── features/family/ParentPages.tsx  # thông báo cho phụ huynh và bài luyện của con (trang phụ huynh hiện có)
├── api-client/classes.ts            # announcements, assignments
└── styles/chat-experience.css       # kiểu cho khung tiến trình và thẻ

infra/dify/
├── eduagent-planner.yml             # MỚI
├── eduagent-triage.yml              # + nhánh path
├── eduagent-runner.yml, eduagent-runner-raw.yml   # + 3 tool tín hiệu, max vòng 6
└── README.md                        # import planner, cập nhật MCP tool list, ghi chú hội thoại mồ côi

eval/
├── planning_set.jsonl               # MỚI (~60 ca, 5 nhóm)
├── run_planning.py                  # MỚI (--e2e)
├── run_routing.py                   # + --latency
└── redteam_vi.jsonl                 # + ~10 ca lách qua phối hợp

dev.ps1, .env.example, README.md, docs/BAO-CAO.md   # cập nhật
```

**Structure Decision**: Giữ cấu trúc web application hiện có. Logic điều phối nằm trong module riêng
`app/orchestrator/` để `dify_turn.py` chỉ còn rẽ nhánh và stream. Phần stream runner được tách thành hàm dùng chung
cho đường nhanh và bước tổng hợp, nên không có hai bản code stream.

## Thứ tự triển khai

| Bước | Nội dung | Điều kiện xong | Story |
|---|---|---|---|
| 0 | Spike Dify: nhánh `path` song song trong triage (đo độ trễ), app planner thô, runner gọi `conversation_id=""` và tool tín hiệu qua MCP; ghi fixture | fixture trong `tests/fixtures/dify/`; triage trung vị tăng ≤ 10% | — |
| 1 | Nền: migration `0008`, `orchestrator/models.py`, config, `PolicyModel.multi_step`, `usage_ledger.path`; tách `_stream_runner()` | test hiện có pass, không đổi hành vi | — |
| 2 | Triage `path` + rẽ nhánh; planner + kiểm tra; một phần việc + tổng hợp; SSE `plan`/`step` | kịch bản 1, 7 (một agent), 12; `test_orchestrator.py` phần chọn đường | US2 |
| 3 | Hỏi lại: `pending`, `ask`, `reply`, làm tiếp, huỷ, hết hạn, công tắc lớp; `AskCard` | kịch bản 2–6, 13–15, 19 | US1 |
| 4 | Nhiều agent: DAG song song, timeout, giới hạn, lỗi từng phần việc, contributors, trích dẫn gộp; huỷ khi rời đi | kịch bản 7–8, 16; SC-002 sơ bộ | US2 |
| 5 | Khung tiến trình + ghi chú: `ProcessPanel`, endpoint ghi chú, review lười, `meta.process` | kịch bản 9–11 | US3 |
| 6 | Xác nhận: `requires_confirmation`, guard bước 7, backend tự chạy tool đúng một lần, `confirm_probe`; `request_confirmation` | kịch bản 18, 28 | US4 |
| 6b | **Bộ tool cần xác nhận** (R18): bảng `class_announcements`, `assignments`, module `class_feed` + API; tách `install_in_class` sang service; `create_text_document`; `tools/actions.py` với 5 tool (args, `preview()`, kiểm duyệt chia sẻ, `execute()`); manifest mẫu; DSL runner bật 5 tool; web: tab Bảng tin, trang học sinh và phụ huynh, thẻ xác nhận có xem trước | kịch bản 20–27, 29; `test_confirm_tools.py`, `test_class_actions.py` | US4 |
| 7 | Tín hiệu giữa chừng: `request_help`, `ask_user` trong phần việc, lập lại kế hoạch, độ sâu 1; cập nhật DSL runner | kịch bản 17; `test_signal_tools.py` | US5 |
| 8 | Vận hành: `dev.ps1` kiểm tra khóa Dify, `.env.example`, README, `infra/dify/README.md`, health | `.\dev.ps1` chạy được từ đầu; health `orchestrator: on` | — |
| 9 | Đo: `planning_set.jsonl`, `run_planning.py`, `--latency`, red-team mở rộng; chỉnh prompt planner/triage và manifest mẫu nếu chưa đạt | SC-001–SC-008 ghi vào `docs/BAO-CAO.md` | — |

Bước 2 + 3 là MVP demo được: hệ thống biết hỏi lại, có khung phân tích, chạy với một agent.

## Rủi ro

| Rủi ro | Ảnh hưởng | Giảm thiểu |
|---|---|---|
| Nhánh `path` làm triage chậm | trượt SC-001 | chạy song song; model nhỏ; nhiệt độ 0; prompt ngắn; đo ở bước 0 |
| Planner chia việc quá đà hoặc hỏi thừa | trượt SC-002/SC-003, người dùng khó chịu | thiên về `fast`; ví dụ âm trong prompt; giới hạn cứng ở backend; eval ở bước 9 |
| Ghi chú dài làm `system_prompt` vượt 12000 | Dify cắt ngầm | cắt từng ghi chú theo ngân sách; giới hạn ghi chú 6000 ký tự |
| Dify không làm mới danh sách tool MCP khi import DSL | runner không thấy tool tín hiệu | README: cập nhật provider MCP trước khi import; `test_dify_dsl.py` kiểm tra DSL |
| Phần việc chạy song song làm nghẽn Dify local | chậm, timeout | `ORCH_MAX_AGENTS=3`; timeout từng phần việc; phần việc lỗi không làm hỏng cả lượt |
| Hội thoại Dify mồ côi tích tụ | DB Dify lớn dần | chấp nhận cho demo; ghi chú dọn dẹp trong README |
| Lách chính sách lớp qua phối hợp | lộ đáp án | mọi phần việc dùng `policy_block`; review trên kết quả cuối và ghi chú; ca red-team riêng (SC-008) |
| Tài liệu lớp chứa chỉ dẫn lừa agent gọi tool cần xác nhận (prompt injection) | đăng/giao nội dung giáo viên không muốn | backend ép xác nhận và cho xem trước đúng nội dung; tool không đổi được thiết lập an toàn; kiểm duyệt chia sẻ; ca red-team "tài liệu bảo agent giao bài" |
| Phạm vi tăng do 5 tool và tab Bảng tin | trễ các bước khác | bước 6b tách riêng, làm sau MVP (bước 2–3); bài luyện không có nộp/chấm |

## Complexity Tracking

Không có vi phạm constitution cần giải trình.
