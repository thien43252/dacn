# Research: Xử lý yêu cầu nhiều bước với nhiều agent phối hợp

Phase 0 của [plan.md](plan.md). Mỗi mục ghi quyết định, lý do và các phương án đã cân nhắc. Spec không còn
`[NEEDS CLARIFICATION]`; các mục dưới đây trả lời những câu hỏi về cách làm mà spec để lại cho plan.

## R1. Quá trình xử lý chạy ở đâu

**Decision**: Backend giữ vai trò điều phối, Dify chạy việc. Một module mới `app/orchestrator/` giữ trạng thái của
lượt xử lý (kế hoạch, phần việc, câu hỏi đang chờ, giới hạn), quyết định bước tiếp theo và ghi DB. Mọi lời gọi mô
hình vẫn đi qua các app Dify: triage, planner (mới), runner, review.

**Rationale**:
- `dify_turn.py` vốn đã điều phối một chuỗi cố định (triage → runner → review). Feature này chỉ biến chuỗi đó thành
  một vòng có kế hoạch và có trạng thái.
- Danh sách agent thay đổi theo từng lớp và vai trò. Graph của Dify là cố định nên không có "một node cho mỗi
  agent" được.
- Dừng chờ người dùng qua nhiều request HTTP cần trạng thái bền trong Postgres, thứ mà backend đã quản lý.
- Test offline bằng `httpx.MockTransport` và fixture vẫn dùng được như feature 001.

**Alternatives considered**:
- *Một Chatflow lớn trên Dify* (iteration, parallel, classifier): không gọi được agent động, việc dừng chờ người
  dùng phụ thuộc phiên bản Dify, khó test.
- *Đưa lại engine trong backend (LangGraph)*: có sẵn interrupt và checkpoint, nhưng đi ngược commit `5ee504b`
  (chỉ dùng Dify) và mất phần kiểm duyệt cấp ứng dụng của Dify.

## R2. Chọn đường nhanh hay đường đầy đủ mà không làm chậm câu hỏi đơn giản

**Decision**: Thêm vào `eduagent-triage` một nhánh LLM nhỏ chạy **song song** với nhánh phân loại an toàn, trả về
output mới `path` (`fast` | `full`). Nhánh này luôn chạy, kể cả khi người dùng đã chọn hoặc `@mention` agent.
Backend chỉ đi đường đầy đủ khi tất cả các điều kiện sau đều đúng:

- `triage.verdict == "allow"`;
- `triage.path == "full"`;
- lượt là chat thật (`kind == "chat"`), hoặc là eval/certify có bật cờ chạy đường đầy đủ;
- lớp bật `policy.multi_step` (không gian cá nhân luôn bật);
- đã cấu hình khóa planner (`DIFY_PLANNER_KEY`).

Còn lại đều đi đường nhanh, như hiện nay.

Tiêu chí `full` trong prompt của nhánh: yêu cầu cần từ hai chuyên môn trở lên; **hoặc** thiếu thông tin làm thay
đổi đáng kể kết quả; **hoặc** yêu cầu một hành động có tác dụng ra ngoài. Khi phân vân thì chọn `fast`.

**Rationale**: Hai nhánh song song nên độ trễ của triage gần như không đổi (SC-001). Không cần thêm một lần gọi
riêng cho mọi tin nhắn. Thiên về `fast` khi phân vân giúp giữ tỉ lệ đi đường nhanh của yêu cầu đơn giản ≥ 90%
(SC-002).

**Alternatives considered**:
- *Luôn gọi planner*: thêm một lần gọi LLM vào mọi lượt, trượt SC-001.
- *Heuristic theo độ dài hoặc từ khóa*: không nhận ra yêu cầu mơ hồ ngắn như "làm đề cho em".
- *Gộp hết vào planner, bỏ triage*: an toàn phải fail closed và chạy nhanh; trộn với việc lập kế hoạch thì prompt
  dài và khó đo riêng.

## R3. Planner

**Decision**: Thêm app Dify mới `eduagent-planner` (Workflow, blocking; khóa `DIFY_PLANNER_KEY`). Bên trong gồm một
node LLM sinh JSON và một node Code parse, cắt gọn kết quả. Hợp đồng ở
[contracts/dify-apps.md](contracts/dify-apps.md).

- **Inputs**: yêu cầu đã ẩn thông tin cá nhân; vai trò; danh sách agent mở rộng (thêm `tools` và `is_fallback`);
  agent được yêu cầu; đoạn hội thoại gần đây (tối đa 6 tin, mỗi tin 500 ký tự, lấy từ Postgres); `resume` (câu hỏi
  và câu trả lời khi làm tiếp); `interactive` (`false` ở chế độ không có người thật); các giới hạn.
- **Outputs**: `goal`, `lead`, `missing[]`, `confirm_interpretation`, `steps[]`, `answers_pending` (khi có câu hỏi
  đang chờ).
- **Backend kiểm tra lại toàn bộ** (`orchestrator/planner.py`):
  - slug phải thuộc danh sách agent; không thì đổi thành `lead`, hoặc bỏ nếu trùng;
  - đồ thị phần việc không được có vòng;
  - cắt theo giới hạn: tối đa 5 phần việc, 3 agent, 3 câu hỏi;
  - nếu người dùng đã chọn agent thì `lead` phải là agent đó (FR-005);
  - `missing` phải rỗng khi `interactive=false` hoặc lượt đã hết lần hỏi;
  - lỗi hoặc JSON hỏng thì quay về đường nhanh (FR-006).
- **Phần việc của agent chính**: kế hoạch có thể gồm cả phần việc của `lead`. Bước tổng hợp luôn do `lead` làm, nên
  kế hoạch chỉ có một phần việc cũng hợp lệ (lớp chỉ cài một agent, User Story 2 kịch bản 6).

**Rationale**: Giữ nguyên mẫu đang dùng cho triage và review (Workflow blocking, Code node kiểm tra JSON). Backend
kiểm tra lại vì LLM có thể bị prompt injection: FR-039 do backend bảo đảm, không do prompt.

**Alternatives considered**: Dùng structured output của node LLM trong Dify 1.19. Phụ thuộc vào việc model hỗ trợ,
và vẫn phải kiểm tra lại ở backend, nên không chọn.

## R4. Chạy một phần việc

**Decision**: Dùng lại `eduagent-runner` (streaming), gọi với `conversation_id=""` để mỗi phần việc là một hội thoại
Dify mới và không làm lẫn bộ nhớ hội thoại chính (FR-021).

- `system_prompt` dựng bằng `build_system_prompt()` của agent làm phần việc, cộng thêm khối `STEP_MODE`: "đây là
  phần việc nội bộ; viết ghi chú làm việc cho agent chính, không chào hỏi; nếu cần agent khác, cần người dùng hay
  cần xác nhận thì gọi tool tín hiệu rồi dừng".
- `query` gồm mục tiêu, mô tả phần việc, ghi chú của các phần việc phụ thuộc, và yêu cầu gốc.
- Stream được backend đọc hết để lấy ghi chú, không chuyển tiếp cho người dùng.
- Mỗi phần việc có `ToolContext` riêng (agent, quyền tool, `step_key`, hàng đợi sự kiện), nên tool và trích dẫn gắn
  đúng phần việc (FR-020).
- Các phần việc cùng tầng chạy đồng thời bằng `asyncio` (FR-019). Mỗi phần việc có hạn thời gian
  `ORCH_STEP_TIMEOUT_S` (mặc định 60 giây). Toàn lượt có hạn `ORCH_DEADLINE_S` (mặc định 120 giây, chốt an toàn
  theo Assumptions).
- Nếu kiểm duyệt đầu vào hoặc đầu ra của runner thay câu trả lời của một phần việc (`replace` hoặc câu cài sẵn) thì
  phần việc đó có trạng thái `blocked`. Hệ thống ghi một sự kiện an toàn có agent của phần việc (FR-043), và kết quả
  cuối nói rõ phần đó không làm được.

**Rationale**: Không phải tạo và bảo trì thêm một DSL agent thứ hai. Phần việc vẫn qua kiểm duyệt từ khóa của
runner. MCP tool, Fixed Value `ctx` và guard tool hoạt động y như hiện tại.

**Alternatives considered**:
- *App runner riêng ở chế độ blocking*: phải giữ thêm DSL giống hệt; blocking của chatflow agent cũng phải chờ tới
  hết.
- *Gọi LLM trực tiếp không qua agent node*: mất tool và kiểm duyệt.

Hệ quả chấp nhận được: Dify giữ thêm một hội thoại mồ côi cho mỗi phần việc. Ghi chú trong
`infra/dify/README.md`.

## R5. Agent báo tín hiệu trong lúc làm

**Decision**: Thêm ba tool MCP vào registry, dạng `PlatformTool(signal=True)`:

| Tool | Tham số | Ý nghĩa |
|---|---|---|
| `request_help` | `agent` (slug hoặc rỗng), `task` | cần agent khác làm một việc |
| `ask_user` | `questions[]` (1–3 câu, mỗi câu có `options[]` không bắt buộc) | cần thông tin từ người dùng |
| `request_confirmation` | `summary` | xin xác nhận cách hiểu trước một việc lớn (FR-017) |

Cách xử lý: handler **không chờ gì**. Nó ghi tín hiệu vào `ToolContext.signals` rồi trả ngay một câu "Đã ghi nhận,
hãy kết thúc phần việc với những gì đã có". Sau khi phần việc kết thúc, backend đọc tín hiệu:

- `request_help`: thêm một phần việc cho agent phù hợp (backend chọn theo slug hoặc theo danh sách agent; tối đa 1
  lần lập lại kế hoạch), rồi chạy lại phần việc gốc với kết quả mới.
- `ask_user`: dừng hỏi người dùng nếu lượt còn lần hỏi; nếu không thì ghi giả định rồi làm tiếp.
- `request_confirmation`: tính như một lần hỏi lại.

Tool tín hiệu chỉ hợp lệ trong phần việc của đường đầy đủ. Ở đường nhanh và bước tổng hợp, guard từ chối với lý do
"chỉ dùng trong phần việc". Phần việc do `request_help` tạo ra cũng không được gọi `request_help`, nên độ sâu nhờ
tối đa là 1 (FR-024). Tool tín hiệu được bật trong DSL runner như 5 tool hiện có, cùng tham số Fixed Value `ctx`.

**Rationale**: Nếu MCP lồng một lần gọi Dify khác bên trong lúc Dify đang chạy agent thì sẽ đụng giới hạn thời gian
đọc của proxy SSRF (`SSRF_DEFAULT_READ_TIME_OUT=60`) và timeout tool của plugin agent. Dùng "tool là tín hiệu, backend
là người xếp lịch" thì mọi việc nặng chạy ở tầng backend, có giới hạn và có trace.

**Alternatives considered**: `ask_agent` chạy agent B ngay trong tool call và trả kết quả về cho A. Bị loại vì timeout
và vì lời gọi lồng nhau khó dừng khi người dùng rời đi (FR-040).

## R6. Xác nhận hành động do nền tảng ép buộc

**Decision**:
- `PlatformTool` có thêm trường `requires_confirmation: bool`.
- Khi agent gọi một tool như vậy, guard **không chạy tool**. Nó ghi một yêu cầu xác nhận vào `ToolContext.signals`,
  gồm tool, tham số đã kiểm tra và một mô tả tác động dựng từ template của tool (không do LLM viết), rồi trả về "Cần
  người dùng xác nhận; hệ thống sẽ hỏi".
- Khi người dùng bấm "Đồng ý", **backend tự chạy tool** với đúng tham số đã lưu (FR-018), ghi `tool_calls` như mọi
  lần gọi khác, và đưa kết quả cho agent chính ở bước tổng hợp.
- Từ chối, hết hạn hoặc huỷ thì tool không chạy, và ghi chú "chưa thực hiện" được đưa vào bước tổng hợp.
- Ở đường nhanh, tool cần xác nhận cũng bị chặn theo cùng cách. Lượt đó được nâng lên đường đầy đủ để dừng hỏi xác
  nhận, vì FR-014 áp dụng cho mọi lượt, kể cả khi lớp tắt `multi_step` (FR-046).
- Xác nhận cho hành động không tính vào `clarify_rounds` (FR-016).

Các tool thật cần xác nhận được mô tả ở R18. Ngoài ra còn tool thử `confirm_probe` (ghi một dòng vào `tool_calls`,
không làm gì khác) để test cơ chế mà không đụng dữ liệu lớp. Tool thử chỉ được đăng ký khi `ENABLE_TEST_TOOLS=true`
(test, eval) và không có trong DSL runner dùng cho người dùng.

**Rationale**: FR-014 yêu cầu "bất kể agent hay nội dung hội thoại nói gì". Chỉ khi backend tự chạy tool sau khi
người dùng bấm nút thì mới bảo đảm được điều này, và tham số không bị agent đổi giữa lúc hỏi và lúc chạy.

## R7. Dừng chờ người dùng và làm tiếp

**Decision**:
- Bảng `turn_runs` lưu lượt xử lý đầy đủ (chi tiết ở [data-model.md](data-model.md)). Câu hỏi được lưu thành một
  `ChatMessage` của trợ lý với `status="awaiting_user"` và `meta.ask`. Trạng thái của câu hỏi (`open`, `answered`,
  `skipped`, `approved`, `rejected`, `expired`, `cancelled`) được cập nhật vào chính tin nhắn đó, nên lịch sử hiển thị
  lại đúng và nút không bấm lại được (FR-036).
- `ChatIn` thêm trường `reply` không bắt buộc: `{run_id, answers: {qid: text}, skip_all, decision: approve|reject}`.
  - Gửi qua thẻ câu hỏi (bấm lựa chọn hoặc gõ vào ô của thẻ) thì luôn là trả lời và làm tiếp (FR-009, FR-011). Chuỗi
    câu hỏi và câu trả lời được ghép thành nội dung tin nhắn người dùng.
  - Gõ vào ô chat chính trong lúc có câu hỏi đang chờ:
    - nếu đang chờ **làm rõ**, planner xét `answers_pending`; đúng thì làm tiếp, sai thì huỷ run cũ và xử lý như
      yêu cầu mới (FR-012);
    - nếu đang chờ **xác nhận**, luôn coi là từ chối và huỷ (User Story 4 kịch bản 3), không hỏi LLM.
- Mọi tin nhắn trả lời vẫn đi qua đủ cổng đồng ý, ẩn thông tin cá nhân và triage (FR-037). Bị chặn thì run bị huỷ.
- Một hội thoại chỉ có tối đa một run ở `running` hoặc `awaiting_user`. Ràng buộc này dùng unique index một phần,
  hỗ trợ cả Postgres và SQLite (`postgresql_where`, `sqlite_where`).
- Hết hạn (`ORCH_PENDING_TTL_H`, mặc định 24) được kiểm tra lười khi có tin nhắn tới, không cần job nền. Run hết hạn
  chuyển sang `expired`, tin nhắn mới được xử lý như yêu cầu mới, và một `notice` kiểu `pending_expired` được phát
  (Edge Cases).
- Khi làm tiếp, các phần việc đã xong được giữ nguyên (FR-011). Nếu một agent trong kế hoạch không còn dùng được thì
  gọi planner lập lại kế hoạch với danh sách agent hiện tại (Edge Cases). Nếu lớp vừa tắt `multi_step` thì run bị
  huỷ và tin nhắn đi đường nhanh.

**Rationale**: Không cần hàng đợi việc hay websocket. Mỗi lần làm tiếp là một request `/chat/stream` bình thường, nên
các cổng an toàn hiện có tự áp dụng.

## R8. Tổng hợp kết quả cuối

**Decision**: Agent chính chạy `eduagent-runner` một lần nữa trên **hội thoại Dify chính**
(`conversations.dify_conversation_id`). Câu trả lời được stream thẳng cho người dùng qua chính đoạn code của đường
nhanh: hàm `_stream_runner()` được tách từ `_answer()` hiện tại.

- `query` gồm yêu cầu gốc, cộng thêm khối "Thông tin bổ sung" chứa câu hỏi và câu trả lời nếu đã hỏi lại. Nhờ vậy bộ
  nhớ Dify của hội thoại chỉ có yêu cầu, thông tin bổ sung và kết quả cuối (FR-031).
- Ghi chú làm việc đi trong `system_prompt`, ở khối `SYNTHESIS_MODE`. Mỗi ghi chú bị cắt còn tối đa
  `12000 / số phần việc` ký tự. Khối này cũng nêu yêu cầu viết: ngắn gọn, tối đa 300 từ trừ khi tạo nội dung dài,
  nêu giả định, không chép nguyên văn ghi chú, nêu phần chưa làm được.
- Tên các agent đóng góp được giao diện hiển thị từ `meta.contributors`, không để LLM tự viết (FR-029).
- Trích dẫn là hợp các trích dẫn của mọi phần việc và của bước tổng hợp.
- `_review()`, gợi ý câu hỏi và `_store()` chạy như hiện nay trên kết quả cuối (FR-030).

**Rationale**: Dùng lại toàn bộ đường stream, kiểm duyệt và review đã ổn định. Không phải thêm một app tổng hợp mới.

**Alternatives considered**: App `eduagent-synth` riêng. Bị loại vì phải lặp lại cấu hình kiểm duyệt và MCP.

## R9. Kiểm duyệt ghi chú làm việc (clarify Q3)

**Decision**: Kiểm duyệt **lười** khi có người mở ghi chú lần đầu, kết quả được lưu lại.

- Endpoint `GET /api/chat/messages/{message_id}/steps/{step_key}/note`:
  1. Nếu kết quả cuối bị chặn thì trả `hidden` (Edge Cases).
  2. Nếu ghi chú đã có `note_review` thì trả luôn.
  3. Nếu chưa thì chạy kiểm duyệt từ khóa của runner (`dify_rules.contains_blocked_keyword`), rồi `eduagent-review`
     với đúng `role` và `no_direct_answers` của người xem và lớp, và lưu `visible` hoặc `hidden`.
- Bị chặn thì ghi `guard_events` với `stage="step_note"`, `detector="dify_review"`, và `agent_slug` của phần việc.
- Review lỗi thì trả `hidden` và **không lưu**, để lần mở sau thử lại. Ghi chú chưa kiểm duyệt không bao giờ được
  hiển thị (FR-030).
- Tiêu đề phần việc do planner viết. Tiêu đề bị cắt còn 80 ký tự và lọc từ khóa; trúng từ khóa thì thay bằng
  "Phần việc của <tên agent>".

**Rationale**: Phần lớn người dùng không mở ghi chú. Kiểm duyệt ngay sau mỗi lượt sẽ thêm N lần gọi review vào mọi
lượt nhiều agent.

**Alternatives considered**: Kiểm duyệt ngay khi phần việc xong. An toàn tương đương nhưng tốn chi phí với mọi lượt.

## R10. Mở rộng giao thức SSE

**Decision**: Thêm sự kiện `plan`, `step`, `ask`; trạng thái `done.status="awaiting_user"`; `tool.step_key`;
`notice.kind` mới `pending_expired` và `pending_cancelled`. Chi tiết ở [contracts/chat-sse.md](contracts/chat-sse.md).

- Sự kiện `agent` vẫn được phát cho agent chính trước khi stream kết quả cuối, nên phần code hiện tại không gãy.
- Ở đường đầy đủ, sự kiện `plan` được phát ngay sau khi planner trả về, kể cả khi chỉ dừng để hỏi, để khung tiến
  trình có cập nhật đầu tiên trong 3 giây (SC-006).
- Trước khi gọi planner, backend phát `step{key:"analyze", status:"running"}` để giao diện có tín hiệu ngay khi triage
  xong.

## R11. Giao diện

**Decision**:
- `ProcessPanel.tsx` (mới): khung tiến trình, thu gọn khi có `done`, mở lại được, lấy ghi chú qua endpoint ở R9.
- `AskCard.tsx`: chuyển thể từ `components/chat/QuestionCard.tsx`. Thành phần này đang có sẵn trong repo nhưng chưa
  được dùng; đã có điều hướng từng câu, phím số chọn lựa chọn, bỏ qua, gửi một lần. Phần cần sửa:
  - bỏ danh sách trường bắt buộc kiểu "brief";
  - thêm nút "Cứ làm luôn" (gửi `skip_all`);
  - thêm chế độ xác nhận gồm hai nút "Đồng ý" và "Không".
- `ChatThread.tsx` xử lý `plan`, `step`, `ask` và `awaiting_user`.
- `MessageBody.tsx` hiển thị dòng "Đã làm việc · N agent · X giây" và chip tên các agent đóng góp.
- `PolicyTab.tsx` thêm công tắc "Xử lý nhiều bước (nhiều agent phối hợp, hỏi lại khi thiếu thông tin)".
- Trong lúc có câu hỏi đang chờ, ô chat chính vẫn gõ được. Đây là cách người dùng đổi chủ đề (FR-012).

## R12. Cấu hình và giới hạn

**Decision**: Thêm vào `Settings` (đặt tên kiểu `ORCH_*` cho dễ nhóm):

| Khóa | Mặc định | FR |
|---|---|---|
| `DIFY_PLANNER_KEY` | rỗng; rỗng thì tắt đường đầy đủ | — |
| `ORCH_MAX_CLARIFY_ROUNDS` | 1 | FR-008 |
| `ORCH_MAX_QUESTIONS` | 3 | FR-008 |
| `ORCH_MAX_STEPS` | 5 | FR-025 |
| `ORCH_MAX_AGENTS` | 3 | FR-025 |
| `ORCH_MAX_REPLANS` | 1 | FR-025 |
| `ORCH_STEP_TIMEOUT_S` | 60 | FR-025, FR-026 |
| `ORCH_DEADLINE_S` | 120 | FR-025 |
| `ORCH_PENDING_TTL_H` | 24 | FR-013 |
| `ENABLE_TEST_TOOLS` | false | R6 |

`/api/health` báo thêm `orchestrator: "on" | "off (no planner key)"`.

## R13. Usage, tracing và báo cáo

**Decision**:
- `usage_ledger` thêm cột `path` (`fast` | `full`, nullable cho dữ liệu cũ).
- Thêm các purpose mới: `planner`, `step`, `synthesis`, `note_review`. Hai purpose `triage` và `output_guard` giữ
  nguyên.
- Báo cáo sử dụng hiện có nhóm thêm theo `path` (FR-042, clarify Q2).
- Trace của Langfuse có thêm span `plan`, `step:<key>` (loại `agent`) và `synthesis`, nằm dưới trace của lượt.
- `chat_messages.meta` lưu thêm `path`, `run_id`, `contributors` và `process` (tóm tắt các phần việc) để hiển thị
  lại (FR-035).

## R14. Chế độ không có người thật

**Decision**: Với `kind` thuộc `certify` hoặc `sandbox`, và với eval, backend gửi planner `interactive=false` và
không bao giờ dừng chờ: câu hỏi được coi là "Cứ làm luôn", xác nhận được coi là "Không" (FR-041).

Certify và sandbox mặc định vẫn đi **đường nhanh**, vì danh sách agent chỉ có một agent và cần giữ kết quả kiểm định
ổn định. Eval mới chạy đường đầy đủ qua cờ `force_path` chỉ dùng nội bộ (không có trong `ChatIn` công khai).

## R15. Bộ đánh giá

**Decision**:
- `eval/planning_set.jsonl` (mới), khoảng 60 ca, chia 5 nhóm: `simple` (kỳ vọng `fast`), `multi` (kỳ vọng tập agent),
  `ambiguous` (kỳ vọng hỏi lại), `clear` (kỳ vọng không hỏi), `discover` (vài ca chỉ lộ ra cần agent khác trong lúc
  làm, dùng cho kiểm tra thủ công User Story 5 và `--e2e`). Mỗi ca có `role`, `installed` và kỳ vọng tương ứng.
- `eval/run_planning.py` gọi triage và planner thật, tính các chỉ số SC-002, SC-003 và SC-004. Cờ `--e2e` chạy trọn
  lượt qua `run_dify_turn` để đo thời gian tới kết quả cuối (trung vị, p90) và độ dài kết quả (SC-006, SC-007).
- Thêm khoảng 10 ca "lách chính sách qua phối hợp" vào `eval/redteam_vi.jsonl` cho SC-008.
- SC-001 đo bằng `run_routing.py --latency` trước và sau thay đổi trên cùng bộ `simple`.

## R16. Rời đi giữa chừng

**Decision**: Generator SSE của lượt đầy đủ bọc mọi tác vụ phần việc trong một `asyncio.TaskGroup`. Khi client ngắt
kết nối:

- huỷ task group;
- gọi `stop` của Dify cho mọi `task_id` đang chạy (giống đường nhanh hiện tại);
- chuyển run sang `cancelled`.

Tool cần xác nhận chỉ chạy trong request mang `decision=approve`, tức lúc người dùng đang có mặt. Không có tác vụ nền
nào chạy tool sau khi request kết thúc (FR-040).

## R17. Những gì đổi trong Dify

| App | Thay đổi |
|---|---|
| `eduagent-triage` | thêm nhánh LLM `path` chạy song song và output `path` |
| `eduagent-planner` | **mới** |
| `eduagent-runner`, `eduagent-runner-raw` | bật thêm `request_help`, `ask_user`, `request_confirmation`; không đổi input |
| `eduagent-review` | không đổi; dùng lại cho ghi chú làm việc |

`test_dify_dsl.py` thêm kiểm tra cho các DSL này: planner có đủ input và output; runner bật tool tín hiệu với `ctx`
Fixed Value; triage có output `path`.

## R18. Bộ tool cần xác nhận (FR-047 đến FR-050)

Bổ sung khi lập plan theo yêu cầu của người dùng: làm luôn các tool cần xác nhận sẽ cần sau này, không chỉ có tool thử
`confirm_probe`.

**Decision**: 5 tool, đều `requires_confirmation=True`, chỉ dành cho vai trò `teacher`, `needs_class=True`, và chỉ
chạy được khi người dùng là giáo viên của lớp trong handle. Chi tiết tham số ở [contracts/mcp-tools.md](contracts/mcp-tools.md).

| Tool | Tác dụng | Dùng lại gì | Bảng mới |
|---|---|---|---|
| `save_class_document` | lưu nội dung Markdown thành tài liệu lớp (`.md`) rồi đồng bộ sang kho tri thức Dify | `knowledge.service` (lưu file, `process_document`) | không |
| `set_agent_notes` | thay hoặc thêm vào `policy.notes_for_agents` (≤ 1000 ký tự) | `PolicyModel` | không |
| `install_agent` | cài agent từ Hub vào lớp | tách `_installable()` và phần thân của `install_in_class()` ở `agents/router.py` thành hàm service | không |
| `post_class_announcement` | đăng thông báo tới `students`, `parents` hoặc `all` | — | `class_announcements` |
| `assign_practice` | giao bài luyện (≤ 20 câu, có thể có hạn) cho học sinh của lớp | `quiz_generator` vẫn là nơi soạn câu hỏi; tool chỉ đăng | `assignments` |

Các điểm chung:

- **Xem trước đúng nội dung (FR-048).** Mỗi tool có hàm `preview(context, args)` (không do LLM viết) trả về
  `{summary, impact, audience_count, preview}`. `preview` gồm tiêu đề, 600 ký tự đầu của nội dung, số câu hỏi; hoặc
  tên và mô tả của agent; hoặc ghi chú cũ và ghi chú mới. Thẻ xác nhận hiển thị nguyên các trường này.
- **Kiểm duyệt trước khi xin xác nhận (FR-049).** Mọi trường văn bản sẽ hiển thị cho người khác đều chạy
  `dify_rules.contains_blocked_keyword`. Với thông báo và bài luyện (học sinh đọc) còn chạy thêm `eduagent-review`
  với `role="student"` và `no_direct_answers="false"` (giáo viên được chủ động chia sẻ lời giải). Trúng thì guard trả lỗi tool "Nội dung không phù hợp để chia sẻ: …", không tạo yêu cầu xác
  nhận, và ghi `guard_events` (stage `tool`, category `share_blocked`).
- **Chạy đúng một lần (FR-050).** Khi `reply.decision=approve`, backend khoá dòng `turn_runs` bằng
  `SELECT … FOR UPDATE` (Postgres; SQLite chạy tuần tự), kiểm tra `pending.kind=="confirm"`, ghi
  `confirmations[i].decision`, xoá `pending` **trước** khi chạy tool, rồi commit. Request trùng hoặc gửi lại sẽ thấy
  `pending` rỗng và bỏ qua. `tool_calls` ghi lần chạy với `arguments` đúng như đã xem trước.
- **Gỡ lại được (FR-050).** Tài liệu và agent đã có API xoá hoặc gỡ. Thông báo và bài luyện có thêm API `DELETE` (chỉ
  giáo viên của lớp). Ghi chú sửa lại ở tab Chính sách.
- **Kiểm tra quyền lúc chạy.** Ngoài guard lúc agent gọi tool, backend kiểm tra lại quyền giáo viên ngay trước khi chạy
  tool sau xác nhận, phòng trường hợp quyền đã đổi trong lúc chờ.
- **Manifest mẫu.** Thêm tool vào agent phù hợp trong `seed/agents/`:

| Agent | Tool thêm |
|---|---|
| `tro-ly-lop` | `set_agent_notes`, `install_agent`, `post_class_announcement` |
| `tao-de` | `assign_practice`, `save_class_document` |
| `on-tap-tai-lieu` | `save_class_document` |

  Guard vẫn chặn học sinh và phụ huynh (`roles={"teacher"}`).
- **DSL runner** bật 5 tool này (như các tool thường), cùng Fixed Value `ctx`. `eduagent-runner-raw` (dùng cho kiểm
  định) cũng bật, để agent giáo viên tự viết dùng các tool này vẫn kiểm định được.
- **Kiểm định agent (certify)** không bao giờ có người xác nhận (FR-041), nên các tool này luôn ở trạng thái "chưa thực
  hiện". Pipeline kiểm định ghi nhận lần gọi nhưng không chạy.

**Rationale**: Ba tool đầu dùng bảng và logic có sẵn, nên chi phí thấp và có ngay ở demo. Hai tool sau là các ví dụ
"giao bài, gửi thông báo" mà spec nêu, chỉ cần hai bảng nhỏ và một khu hiển thị trên trang lớp. Ghi điểm, nhắn riêng
và nộp/chấm bài luyện cần thêm cả một miền dữ liệu (sổ điểm, hộp thư, bài nộp), nên để feature sau.

**Alternatives considered**:
- *Chỉ làm `confirm_probe`* (plan ban đầu): không có giá trị khi demo, và người dùng đã yêu cầu bổ sung.
- *Cho tool sửa mọi trường của chính sách lớp*: bị loại. Thiết lập an toàn đổi qua chat sẽ dễ bị lừa qua prompt
  injection từ tài liệu lớp.
- *Giao bài luyện kèm nộp và chấm*: quá lớn cho feature này; bài luyện hiện chỉ mở chat "làm cùng gia sư".
