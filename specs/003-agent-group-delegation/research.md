# Research: Tạo agent, nhóm chat, giao việc và hỏi người

Tài liệu này ghi các quyết định kỹ thuật cho plan. Mỗi mục có ba phần: quyết định, lý do, và các phương án đã cân nhắc.
Bối cảnh chung: code trên `main` (FastAPI, SQLAlchemy async, LangGraph, SSE, React 19), chạy một tiến trình backend.
Test chạy trên SQLite trong bộ nhớ, dùng LLM `fake`.

## R1. Nơi chạy giao việc bất đồng bộ (FR-013, FR-015, FR-016)

- **Quyết định**: dùng bảng `handoffs` trong Postgres làm hàng đợi. Một worker `asyncio` chạy trong tiến trình backend,
  được khởi động trong `lifespan`.
  - Worker lấy việc bằng `UPDATE … WHERE status='queued' … RETURNING`. Trên Postgres thêm `FOR UPDATE SKIP LOCKED`.
  - Mỗi việc lấy ra mang `lease_until`. Việc hết hạn lease thì được lấy lại, như cơ chế "lease" của OpenBot.
  - Khi khởi động, worker quét các việc bị dở do tiến trình chết, theo cách `fail_interrupted` đang làm cho kiểm định.
  - Test gọi thẳng `drain()` để chạy hết hàng đợi theo cách đồng bộ.
- **Lý do**:
  - Không thêm service hay container nào, nên `dev.ps1` không đổi phần khởi động (nguyên tắc III).
  - Việc sống sót qua lần reload của uvicorn.
  - Mã `handoffs.id` cho tính lũy đẳng (chỉ ghi câu trả lời một lần).
  - Giống mô hình `work_items` của OpenBot.
- **Phương án đã cân nhắc**:
  - Celery hoặc RQ cùng Redis: thêm service, quá nặng cho đồ án chạy local.
  - `asyncio.create_task` không lưu trạng thái: mất việc khi reload, không thử lại được.
  - Gọi đồng bộ trong lượt chat: trái với FR-013, và lượt chat kéo dài quá lâu.

## R2. Đẩy câu trả lời đến sau khi lượt chat đã đóng (FR-014, FR-020, FR-042)

- **Quyết định**: thêm stream sự kiện theo hội thoại, `GET /api/chat/conversations/{id}/events?after=<seq>` (SSE).
  - Mỗi tin trong hội thoại có `seq` tăng dần.
  - Server phát sự kiện qua một bus trong bộ nhớ (`asyncio.Queue` cho từng người nghe).
  - Khi client kết nối lại, server phát bù từ DB theo `after`.
  - Lượt chat của chính người gửi vẫn đi qua `POST /chat/stream` như hiện nay.
- **Lý do**:
  - Cùng công nghệ SSE và cùng định dạng sự kiện (`chatStream.ts`) đang có.
  - Có phát bù từ DB, nên mất kết nối hay tải lại trang không làm mất tin.
  - Đủ cho mục tiêu "trong vòng 2 giây" khi chạy local (SC-008).
- **Phương án đã cân nhắc**:
  - WebSocket: phải thêm giao thức và phần xác thực riêng.
  - Polling: đơn giản nhưng chậm và tốn tài nguyên.
  - Postgres LISTEN/NOTIFY: chỉ cần khi có nhiều replica, hiện ngoài phạm vi; ghi lại làm hướng mở rộng.

## R3. Agent hỏi dừng chờ rồi làm tiếp (FR-017, FR-029, FR-036)

- **Quyết định**: thêm bảng `agent_runs`, lưu bản chụp hội thoại của mô hình (messages, tool_calls) tại điểm dừng.
  - Lượt chạy dừng khi nó đã gửi yêu cầu giao việc, gọi `ask_person`, hoặc chạm hành động cần duyệt.
  - Khi điều kiện chờ được giải quyết, worker dựng lại `RunContext` theo **người dùng gốc** và đưa kết quả vào làm
    `tool` message. Điều kiện chờ gồm: mọi handoff có kết quả, người nhận trả lời câu hỏi, hoặc thẻ duyệt có câu trả lời.
  - Sau đó worker chạy tiếp vòng lặp công cụ đang có trong `run_agent`, rồi `review`.
  - Kết quả là một tin mới của agent hỏi trong hội thoại gốc. Đây chính là lượt làm tiếp ở FR-017.
- **Lý do**:
  - Dùng lại nguyên vòng lặp công cụ và guard đầu ra hiện có.
  - Không cần bộ checkpointer của LangGraph, vốn cần thêm bảng và bộ tuần tự hoá trạng thái chứa `RunContext`, thứ
    không tuần tự hoá được.
- **Phương án đã cân nhắc**:
  - LangGraph `interrupt()` cùng Postgres checkpointer: hợp với mục đích, nhưng `ChatState` hiện chứa `ctx` (gồm session
    DB và model) nên phải viết lại state.
  - Bắt agent hỏi tự đọc lại hội thoại ở lượt sau: mất yêu cầu có cấu trúc và không có cái gì kích hoạt lượt làm tiếp.

## R4. Biểu diễn công cụ giao việc, hỏi người và trả lời riêng

- **Quyết định**: thêm ba "công cụ nền tảng" trong `app/tools/registry.py`, gắn cờ `meta=True`:
  - `message_agent`: giao việc.
  - `ask_person`: hỏi người.
  - `reply_privately`: chuyển câu hỏi có dữ liệu riêng sang chat riêng, chỉ dùng trong nhóm.

  Đặc điểm chung:
  - Runtime tự xử lý ba công cụ này, không gọi qua MCP server, vì chúng cần ngữ cảnh lượt chạy và DB.
  - Không cần khai báo trong manifest.
  - Tool guard vẫn kiểm tra mọi lời gọi.

  Điều kiện mời công cụ:
  - `message_agent` chỉ được mời khi có ít nhất một agent đích hợp lệ (FR-006, FR-011), giống "granted nobody is
    offered nothing" của OpenBot.
  - `ask_person` luôn được mời (FR-024).
  - `reply_privately` chỉ được mời trong hội thoại nhóm.
- **Lý do**:
  - Cùng một đường guard, nhật ký `tool_calls` và trace với các công cụ khác.
  - Tên agent đích chỉ đi qua tham số; nền tảng tự tra lại, nên mô hình không tự đặt được đích hay tầng (FR-008).
- **Phương án đã cân nhắc**:
  - Cú pháp đặc biệt trong văn bản (`@agent`) cho giao việc trong chat riêng: khó kiểm soát và không có cấu trúc.
    Trong nhóm, `@Tên` do agent viết vẫn được chuyển thành `message_agent` (FR-044).

## R5. Lưu quyền giao việc ở đâu (FR-006)

- **Quyết định**: lưu ở hai chỗ.
  - Thêm trường `handoff_to: list[str]` (slug) vào `AgentManifest`, nên quyền nằm trong phiên bản bất biến và có lịch sử
    phiên bản.
  - Thêm cột `handoff_allow: JSON | null` trên `installations` để giáo viên thu hẹp quyền trong lớp. `null` nghĩa là
    dùng đúng danh sách của manifest; một danh sách nghĩa là lấy giao với danh sách đó.
- **Lý do**:
  - Agent nền tảng cấp quyền ngay trong YAML ở `seed/agents`, và `sync_platform_agents` tự tạo phiên bản mới.
  - Kiểm định cũng đọc được quyền này.
- **Phương án đã cân nhắc**: bảng `agent_grants` riêng. Linh hoạt hơn nhưng tách quyền khỏi phiên bản, nên khó biết
  phiên bản đã được kiểm định có quyền gì.

## R6. Mô hình hội thoại nhiều người

- **Quyết định**: `conversations` có thêm `kind` thuộc `direct`, `group`, `sandbox`. Bảng mới `conversation_members`
  chứa thành viên người hoặc agent, mỗi dòng có `user_id` hoặc `agent_slug`.
  - `direct` có đúng một người và một agent (`direct_agent_slug`), và mỗi người, agent và phạm vi chỉ có một hội thoại
    đang mở.
  - `chat_messages` thêm các cột: `sender_user_id`, `seq`, `handoff_id`, `person_request_id`, `reply_to_agent`,
    `visible_to`.
  - Migration chuyển mọi hội thoại `kind="chat"` cũ thành `direct`. Agent của hội thoại cũ lấy theo agent trả lời gần
    nhất, hoặc `tro-ly-lop` nếu chưa có.
- **Lý do**: danh sách hội thoại kiểu Messenger (FR-049) đọc được bằng một truy vấn duy nhất. Quyền xem kiểm bằng
  thành viên (FR-039, FR-050).
- **Phương án đã cân nhắc**: tách bảng `groups` riêng. Phải nhân đôi phần tin nhắn và stream.

## R7. Luồng của từng agent trong nhóm (FR-042)

- **Quyết định**: không lưu luồng riêng thành bảng. Khi một agent nhận lượt trong nhóm, runtime dựng ngữ cảnh theo thứ
  tự sau:
  1. Tin nhóm mà người gọi được xem (FR-045).
  2. Bỏ nội dung đã ẩn.
  3. Trong đó, tin của các agent khác hiện là `[Tên agent]: …`; tin của chính agent đó hiện là `assistant`.

  Luồng nháp của agent được hỏi chỉ sống trong `agent_runs.transcript` của handoff đó.
- **Lý do**: đạt mục tiêu của `group_bot_threads` (mỗi agent một ngữ cảnh) mà không phải đồng bộ thêm bảng.
- **Phương án đã cân nhắc**: bảng `group_agent_threads`. Chỉ cần nếu sau này mỗi agent có trí nhớ dài hạn riêng.

## R8. Duyệt hành động (FR-032 đến FR-038)

- **Quyết định**: mỗi `PlatformTool` khai báo thêm `action_kind`, nhận một trong các giá trị: `none`, `send`, `share`,
  `post`, `delete`, `settings`, `money`, `change`. Một hàm thuần `decide(action, user, conversation)` trả về `allow`,
  `deny` hoặc `ask`, xét theo thứ tự:
  1. Loại luôn phải hỏi (mọi giá trị trừ `none` và `change`).
  2. Quy tắc trong `approval_rules`, phạm vi `user`, `class`, `admin` hoặc `conversation`. "Deny" xét trước; quy tắc
     chặt nhất thắng; không có quy tắc khớp thì không cho; quy tắc hỏng thì từ chối.
  3. Công tắc `extra_vigilant` của người dùng.

  Ngoài ra:
  - Chế độ cho từng loại và vai trò (`approval_kind_modes`) quyết định thẻ hiện những lựa chọn nào. Khi `ask`, runtime
    tạo một `approval_cards` và dừng lượt chạy (R3).
  - Trong lượt chạy theo giao việc, thẻ được gắn vào hội thoại gốc.
  - Ở chế độ không có người thật (`source in {sandbox, certify}`) thì từ chối ngay.
- **Lý do**: viết thành hàm thuần thì test được bảng chân trị đầy đủ mà không cần LLM. Giống đúng thứ tự quyết định
  trong `approvals.md` của OpenBot.
- **Phương án đã cân nhắc**: để agent tự hỏi trong văn bản. Đó là lời dặn trong prompt, không phải hàng rào (SC-013).

## R9. Người nhận câu hỏi và hộp yêu cầu (FR-025 đến FR-031)

- **Quyết định**:
  - Bảng `person_requests`. Danh sách người nhận hợp lệ do `allowed_recipients(user, room)` tính từ `class_members` và
    `parent_links`.
  - Thêm cột `class_members.subject` (nullable) cho giáo viên.
  - Gửi tới người khác dùng `action_kind="send"`, nên đi qua R8 trước khi rời hội thoại.
  - Hộp yêu cầu: `GET /api/inbox`, kèm số chưa đọc trong `GET /api/auth/me` để hiện huy hiệu.
  - Hết hạn: worker ở R1 quét `expires_at` mỗi chu kỳ.
- **Lý do**: dùng lại quan hệ lớp và liên kết phụ huynh đã có. Không cần email hay đẩy thông báo (nằm ngoài phạm vi).
- **Phương án đã cân nhắc**: dùng bảng thông báo chung. Trạng thái và câu trả lời của câu hỏi đặc thù, nên tách riêng
  rõ ràng hơn.

## R10. Định tuyến trong nhóm và tin không gọi agent (FR-043)

- **Quyết định**: mở rộng `app/runtime/router.py` bằng hàm `route_group`, xét theo thứ tự:
  1. `@agent` thì agent đó nhận.
  2. Tin chỉ gọi `@người` thì không agent nào nhận.
  3. Router LLM được thêm lựa chọn `"none"`, nghĩa là trò chuyện giữa người với người.
  4. Độ tin cậy thấp thì agent mặc định của nhóm nhận.

  Với LLM `fake`, router từ khoá chọn "none" khi không có từ khoá nào khớp với năng lực của agent.
- **Lý do**: giữ nguyên cách chọn agent đã đo trong `eval/run_routing.py`; chỉ thêm nhánh "không ai".
- **Phương án đã cân nhắc**: luôn để agent mặc định trả lời. Sẽ gây ồn trong nhóm có người với người.

## R11. Quyền riêng tư và nhật ký (FR-050, FR-051, FR-057)

- **Quyết định**:
  - Nhật ký lớp của giáo viên (`audit/router.py`) và các truy vấn hoạt động lọc theo thành viên hội thoại. Giáo viên chỉ
    thấy sự kiện của các nhóm mình là thành viên.
  - Hội thoại `direct` của người khác bị loại khỏi nhật ký lớp.
  - Admin thấy sự kiện nhưng `excerpt` bị bỏ với hội thoại riêng tư.
  - Báo cáo học tập giữ số liệu tổng hợp như hiện nay.
- **Lý do**: thực hiện đúng kết quả làm rõ (riêng tư hoàn toàn, không báo giáo viên). Thay đổi hành vi này được ghi
  trong Assumptions của spec.
- **Phương án đã cân nhắc**: ẩn danh rồi vẫn hiện cho giáo viên. Đã bị loại khi làm rõ spec.

## R12. Học sinh, phụ huynh tạo agent (FR-001 đến FR-005)

- **Quyết định**:
  - Đổi dependency `Teacher` trong `agents/router.py` thành `Maker`, gồm teacher, student, parent và admin.
  - `create_agent` và `update_draft` lọc `tools` theo vai trò người tạo bằng `TOOLS[*].roles`.
  - `handoff_to` chỉ nhận agent mà người tạo đang dùng được.
  - Cài agent tự tạo vào lớp là `action_kind="share"`. Agent phải có phiên bản `certified`, và tạo một `person_request`
    loại `install_agent` gửi giáo viên của lớp; giáo viên trả lời "Đồng ý" thì nền tảng mới cài.
  - Học sinh dùng agent tự tạo khi chưa kiểm định chỉ trong không gian cá nhân. Điều kiện là có đồng ý của phụ huynh
    (`student_can_use_agents`).
- **Lý do**: dùng lại trình tạo agent, sandbox và kiểm định hiện có, chỉ mở quyền.
- **Phương án đã cân nhắc**: làm trình tạo riêng, đơn giản hơn cho học sinh. Bị loại vì nhân đôi code.

## R13. Bộ kịch bản kiểm thử tương đương OpenBot (FR-058)

- **Quyết định**: thêm `eval/delegation_scenarios.yaml` và `eval/run_delegation.py`, gồm 5 nhóm ca giống bộ test
  OpenBot, dựng trên agent và dữ liệu demo của trường. Có thêm các ca lách quyền, ca chèn lỗi mạng và ca riêng tư nhóm.
  - Chạy được với `fake` (kiểm tra hàng rào) và với LLM thật (đo SC-007, SC-014).
  - Test pytest dùng lại các ca hàng rào.
- **Lý do**: cùng khuôn với `run_routing.py`, `run_redteam.py` đã có.

## R14. Giao diện kiểu Messenger

- **Quyết định**:
  - Thêm trang `/{role}/chat` có hai cột.
    - Cột trái: danh sách hội thoại (chat riêng với từng agent, các nhóm), ô tìm, nút "Nhóm mới".
    - Cột phải: `ChatThread` mở rộng.
  - Thêm các component: `ConversationList`, `HandoffBar` (thanh "Đã hỏi" mở/đóng, lồng được), `HandoffMessage` (tin
    riêng trong nhóm), `ApprovalCard`, `PersonRequestCard`, `InboxPage`, `NewGroupDialog`.
  - Hook `useConversationEvents` nghe stream R2.
  - Không thêm thư viện; giữ React 19 cùng CSS thuần như hiện nay.
- **Lý do**: dùng lại `ChatThread`, `MessageBody`, `Mascot` và `chatStream.ts`. Đúng yêu cầu "làm giống Messenger".
