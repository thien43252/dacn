# Feature Specification: Chuyển lõi agent sang Dify và tích hợp tính năng Dify

**Feature Branch**: `feat/dify-runtime`

**Created**: 2026-11-06

**Status**: Draft

**Input**: User description: "tôi muốn thay đổi lõi của hệ thống từ langgraph sang dify cũng như là tích hợp các tính năng mà dify hỗ trợ vào dự án của tôi (cả backend lẫn frontend); phần guardrail và orchest, routing hiện tại cứ dùng của dify cung cấp"

## Bối cảnh

Hiện nay mỗi lượt chat do nền tảng tự xử lý: tự sàng lọc đầu vào, tự định tuyến tới agent phù hợp, tự gọi mô
hình và tool, rồi tự kiểm duyệt đầu ra. Feature này chuyển toàn bộ lõi đó sang **Dify**. Việc điều phối,
định tuyến và guardrail sẽ dùng các khả năng có sẵn của Dify, không duy trì bản tự viết nữa. Đồng thời, các
tính năng Dify cung cấp sẵn được đưa vào sản phẩm cho người dùng cuối (giáo viên, học sinh, phụ huynh, admin).

Hướng này **thay thế** quyết định trong `docs/PLAN-DIFY.md`, vốn chỉ dùng Dify để chạy agent, còn guard và
router vẫn giữ trong backend. Những phần không thuộc lõi agent vẫn giữ nguyên trong nền tảng: tài khoản, vai
trò, lớp học, thành viên, liên kết phụ huynh, đồng ý của phụ huynh, Hub, cài agent vào lớp và báo cáo phụ huynh.

## Clarifications

### Session 2026-11-06

- Q: Chính sách riêng từng lớp (chủ đề cấm, môn được phép) được áp dụng thế nào khi guardrail chuyển sang
  Dify? → A: Dùng một bộ luật kiểm duyệt chung trong Dify cho mọi lớp; bỏ chủ đề cấm riêng từng lớp.
- Q: Những tính năng có sẵn của Dify nào được đưa lên giao diện chat? → A: Gợi ý câu hỏi tiếp theo và trích
  dẫn nguồn tài liệu. Đánh giá thích/không thích, đính kèm ảnh/file, giọng nói và lời chào mở đầu nằm ngoài
  phạm vi.
- Q: Tài liệu lớp được lưu và tra cứu ở đâu sau khi chuyển sang Dify? → A: Kho tri thức của Dify, mỗi lớp
  một kho; nền tảng đẩy file lên Dify và chỉ gắn kho của lớp hiện tại vào mỗi lượt chat.
- Q: Ngữ cảnh hội thoại do ai giữ khi gửi cho agent trên Dify? → A: Dùng hội thoại của Dify: mỗi cuộc hội
  thoại của nền tảng gắn với một hội thoại trên Dify và Dify tự nhớ ngữ cảnh; nền tảng vẫn lưu bản sao để
  hiển thị, nhật ký và báo cáo.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Chat với agent trong lớp chạy trên Dify (Priority: P1)

Học sinh vào lớp và gửi câu hỏi. Dify tự chọn agent phù hợp (hoặc dùng agent mà học sinh đã chọn hoặc
`@mention`) rồi trả lời. Câu trả lời hiện dần theo thời gian thực. Giao diện cho biết agent nào đang trả lời và
tool nào đang được dùng. Trải nghiệm không được kém hơn hiện nay.

**Why this priority**: Chat là luồng giá trị chính. Chưa chạy được luồng này trên Dify thì các phần khác đều
không có ý nghĩa.

**Independent Test**: Đăng nhập tài khoản học sinh demo, gửi một câu hỏi toán và một câu hỏi tiếng Anh trong
lớp demo. Kiểm tra mỗi câu được trả lời bởi agent đúng môn, câu trả lời hiện dần, và có hiển thị tool khi
agent dùng tool.

**Acceptance Scenarios**:

1. **Given** học sinh trong lớp đã có phụ huynh đồng ý và lớp đã cài agent toán, **When** học sinh hỏi "giải
   phương trình 2x + 3 = 7", **Then** câu trả lời do agent toán đưa ra, hiện dần trên màn hình, và giao diện
   hiển thị tên agent.
2. **Given** học sinh chọn sẵn một agent trên giao diện hoặc gõ `@ten-agent`, **When** gửi câu hỏi, **Then**
   agent được chọn trả lời, không bị định tuyến sang agent khác.
3. **Given** câu hỏi không khớp môn nào, **When** gửi câu hỏi, **Then** trợ lý lớp mặc định trả lời.
4. **Given** học sinh mở lại một cuộc hội thoại cũ, **When** gửi câu hỏi tiếp, **Then** agent trả lời đúng
   theo ngữ cảnh các tin nhắn trước.
5. **Given** học sinh chưa được phụ huynh đồng ý, **When** mở chat, **Then** học sinh không dùng được agent,
   giống như hiện nay.

---

### User Story 2 - Guardrail của Dify bảo vệ học sinh (Priority: P1)

Mọi tin nhắn đi qua kiểm duyệt đầu vào và đầu ra của Dify. Nội dung không phù hợp bị chặn và người dùng nhận
một thông báo thân thiện. Mọi lần chặn đều được ghi lại để giáo viên (theo lớp) và admin xem trong nhật ký.

**Why this priority**: Người dùng là trẻ vị thành niên. Không thể chuyển lõi sang Dify nếu mất lớp bảo vệ.

**Independent Test**: Chạy bộ red-team tiếng Việt có sẵn qua luồng chat mới, đếm tỉ lệ bị chặn và tỉ lệ chặn
nhầm trên bộ câu hỏi hợp lệ. Mở nhật ký của giáo viên để xem các lần chặn.

**Acceptance Scenarios**:

1. **Given** học sinh gửi nội dung vi phạm (bạo lực, tình dục, xin đáp án gian lận…), **When** gửi, **Then**
   tin nhắn không được trả lời bằng nội dung, học sinh thấy thông báo bị chặn, và nhật ký có một bản ghi mới.
2. **Given** agent sinh ra câu trả lời vi phạm, **When** kiểm duyệt đầu ra phát hiện, **Then** học sinh
   không thấy nội dung vi phạm. Nếu nội dung đã hiện một phần thì phần đó bị thay bằng thông báo.
3. **Given** học sinh gửi tin nhắn có dấu hiệu tự làm hại, **When** gửi, **Then** học sinh nhận lời hỗ trợ
   kèm số Tổng đài 111, không phải một lời từ chối khô khan.
4. **Given** học sinh gửi số điện thoại, mật khẩu hoặc địa chỉ trong tin nhắn, **When** gửi, **Then** thông
   tin đó không được lưu hay hiển thị lại nguyên văn ở bất kỳ đâu ngoài máy của học sinh.
5. **Given** một chủ đề nằm trong bộ luật kiểm duyệt chung, **When** học sinh ở bất kỳ lớp nào hỏi về chủ
   đề đó, **Then** câu hỏi bị chặn như nhau ở mọi lớp. Giáo viên không đặt thêm chủ đề cấm riêng cho lớp.

---

### User Story 3 - Agent do giáo viên tạo chạy được trên Dify và vẫn qua kiểm định (Priority: P2)

Giáo viên tạo hoặc sửa agent trong trình tạo agent (tên, môn, hướng dẫn hệ thống, tool, tài liệu). Agent đó
dùng được ngay trong phòng thử và chạy trên Dify. Trước khi lên Hub, agent vẫn phải qua kiểm định tự động.
Học sinh và phụ huynh chỉ dùng được phiên bản đã đạt.

**Why this priority**: Hub và kiểm định là điểm khác biệt của đồ án, nhưng chúng phụ thuộc vào luồng chat ở
User Story 1.

**Independent Test**: Giáo viên demo tạo một agent mới, thử trong phòng thử, gửi kiểm định, xem kết quả, rồi
đăng lên Hub và cài vào lớp.

**Acceptance Scenarios**:

1. **Given** giáo viên lưu một phiên bản agent mới, **When** mở phòng thử, **Then** agent trả lời theo đúng
   hướng dẫn hệ thống và chỉ dùng các tool đã chọn.
2. **Given** giáo viên gửi kiểm định, **When** pipeline chạy xong, **Then** kết quả là đạt / cần xem lại /
   không đạt, kèm báo cáo từng tình huống, như hiện nay.
3. **Given** một phiên bản chưa đạt kiểm định, **When** học sinh tìm agent đó, **Then** học sinh không dùng
   được phiên bản đó.
4. **Given** 7 agent nền tảng có sẵn, **When** hệ thống khởi tạo dữ liệu demo, **Then** cả 7 agent dùng được
   trên Dify mà không phải cấu hình tay từng agent.

---

### User Story 4 - Tính năng mới từ Dify trên giao diện chat (Priority: P2)

Người dùng thấy thêm hai tính năng Dify có sẵn trong giao diện chat của nền tảng: gợi ý câu hỏi tiếp theo
và trích dẫn nguồn tài liệu trong câu trả lời. Đánh giá thích/không thích, đính kèm ảnh/file, giọng nói và
lời chào mở đầu nằm ngoài phạm vi feature này.

**Why this priority**: Đây là giá trị thêm, chỉ làm sau khi chat và guardrail đã ổn.

**Independent Test**: Với mỗi tính năng trong hai tính năng trên, thực hiện một lượt chat trong lớp demo và thấy tính năng
hoạt động trên giao diện.

**Acceptance Scenarios**:

1. **Given** agent trả lời dựa trên tài liệu lớp, **When** câu trả lời hiện ra, **Then** người dùng thấy
   tài liệu và đoạn được trích dẫn.
2. **Given** câu trả lời đã hoàn tất, **When** hiển thị xong, **Then** có 2–3 câu hỏi gợi ý, và nhấn vào
   một câu sẽ gửi nó đi.
3. **Given** câu trả lời bị chặn hoặc bị thu hồi bởi kiểm duyệt, **When** hiển thị thông báo, **Then** không
   có câu hỏi gợi ý hay trích dẫn nào đi kèm.

---

### User Story 5 - Tài liệu lớp được dùng để trả lời (Priority: P3)

Giáo viên tải tài liệu (PDF/DOCX/TXT/MD) lên lớp. Agent có bật tài liệu lớp trả lời dựa trên nội dung đó, và
chỉ thấy tài liệu của đúng lớp đó.

**Why this priority**: Tính năng này đã có. Chỉ thay đổi nơi lưu và tìm kiếm tài liệu nếu chuyển sang kho tri
thức của Dify.

**Independent Test**: Tải một tài liệu lên lớp A, hỏi nội dung của nó ở lớp A (có trả lời đúng) và ở lớp B
(không lộ nội dung).

**Acceptance Scenarios**:

1. **Given** giáo viên tải tài liệu lên lớp A, **When** quá trình xử lý xong, **Then** giao diện báo tài
   liệu sẵn sàng.
2. **Given** tài liệu đã sẵn sàng ở lớp A, **When** học sinh lớp B hỏi về nội dung đó, **Then** agent không
   dùng được tài liệu của lớp A.
3. **Given** giáo viên xóa tài liệu, **When** học sinh hỏi lại, **Then** agent không còn dùng nội dung đó.

---

### User Story 6 - Giám sát, chi phí và đo đạc (Priority: P3)

Admin xem được số lượt, token, chi phí và các lần chặn theo thời gian. Có thể chạy các bộ đo hiện có
(red-team, định tuyến, kiểm định) trên lõi mới để so sánh với lõi cũ cho báo cáo đồ án.

**Why this priority**: Cần cho báo cáo và vận hành, nhưng không chặn người dùng cuối.

**Independent Test**: Chạy ba script đo trên cả lõi cũ và lõi mới, rồi có được bảng so sánh.

**Acceptance Scenarios**:

1. **Given** đã có lượt chat qua lõi mới, **When** admin mở trang chi phí, **Then** thấy token và chi phí
   của các lượt đó.
2. **Given** bộ red-team, bộ định tuyến và bộ agent có nhãn, **When** chạy đo trên lõi mới, **Then** có kết
   quả cùng định dạng với lõi cũ để so sánh.

### Edge Cases

- Dify không chạy hoặc không phản hồi: người dùng thấy thông báo lỗi rõ ràng, không bị treo, và phần câu trả
  lời đã hiện được giữ lại.
- Người dùng đóng tab giữa chừng: lượt đang chạy trên Dify bị dừng, không tiếp tục tốn chi phí.
- Hướng dẫn hệ thống dài tới giới hạn của trình tạo agent (8000 ký tự) và hội thoại dài: lượt chat vẫn chạy
  được.
- Hai học sinh ở hai lớp khác nhau dùng cùng một agent: ngữ cảnh lớp, tài liệu và chính sách không bị lẫn.
- Học sinh hỏi bằng tiếng Việt không dấu hoặc lẫn tiếng Anh: định tuyến và guardrail vẫn hoạt động.
- Agent bị gỡ khỏi lớp hoặc bị thu hồi kiểm định khi hội thoại đang mở: lượt tiếp theo không dùng agent đó.
- Hội thoại tương ứng trên Dify bị mất hoặc không còn hợp lệ (Dify được dựng lại, dữ liệu Dify bị xóa): lượt
  tiếp theo bắt đầu một hội thoại Dify mới, người dùng được báo là agent không còn nhớ ngữ cảnh cũ, và lịch
  sử hiển thị trong nền tảng không bị mất.
- Phụ huynh rút lại đồng ý: lượt tiếp theo của học sinh bị chặn ngay.
- Tool trả lỗi hoặc bị từ chối: agent vẫn trả lời được và giao diện hiển thị trạng thái tool.

## Requirements *(mandatory)*

### Functional Requirements

**Lõi chat**

- **FR-001**: Mỗi lượt chat MUST được điều phối, định tuyến, kiểm duyệt và trả lời bởi Dify. Lõi tự viết hiện
  tại MUST không còn được dùng khi feature hoàn tất.
- **FR-002**: Hệ thống MUST tôn trọng thứ tự ưu tiên chọn agent hiện nay: agent chọn trên giao diện →
  `@mention` → định tuyến tự động → trợ lý lớp mặc định.
- **FR-003**: Định tuyến tự động MUST chỉ chọn trong các agent đã được cài cho lớp hoặc cá nhân người dùng,
  và chỉ trong các môn mà lớp cho phép.
- **FR-004**: Câu trả lời MUST hiện dần trên giao diện. Giao diện MUST cho biết agent nào trả lời và trạng
  thái từng tool (bắt đầu, xong, bị từ chối, lỗi).
- **FR-005**: Bản sao lịch sử hội thoại MUST tiếp tục được lưu trong nền tảng, để giáo viên, admin và báo cáo phụ
  huynh dùng như hiện nay.
- **FR-005a**: Ngữ cảnh hội thoại gửi cho agent MUST do bộ nhớ hội thoại của Dify giữ. Mỗi cuộc hội thoại
  của nền tảng MUST gắn với đúng một hội thoại trên Dify. Mọi nội dung gửi sang Dify MUST đã được ẩn thông
  tin cá nhân (FR-011), để bộ nhớ của Dify không chứa thông tin đó.
- **FR-006**: Người dùng MUST dừng được một câu trả lời đang chạy.

**Guardrail và an toàn**

- **FR-007**: Mọi tin nhắn đầu vào MUST qua kiểm duyệt của Dify trước khi tới mô hình của agent. Mọi câu trả
  lời MUST qua kiểm duyệt đầu ra của Dify; vì câu trả lời hiện dần, phần vi phạm đã hiện được thu hồi theo FR-009.
- **FR-008**: Tin nhắn bị chặn ở đầu vào MUST không được gửi tới mô hình của agent.
- **FR-009**: Khi kiểm duyệt đầu ra phát hiện vi phạm, phần nội dung vi phạm đã hiện MUST được thay bằng
  thông báo.
- **FR-010**: Tin nhắn có dấu hiệu tự làm hại MUST nhận câu trả lời hỗ trợ có Tổng đài 111.
- **FR-011**: Số điện thoại, mật khẩu, địa chỉ trong tin nhắn MUST được ẩn trước khi lưu, gửi tới mô hình
  hoặc gửi tới bất kỳ dịch vụ theo dõi nào.
- **FR-012**: Mọi lần chặn hoặc ẩn thông tin MUST được ghi lại, kèm giai đoạn (đầu vào, tool, đầu ra) và lý
  do, và hiện trong nhật ký của giáo viên (theo lớp) và admin.
- **FR-013**: Kiểm duyệt MUST dùng một bộ luật chung trong Dify, áp dụng như nhau cho mọi lớp. Tính năng
  chủ đề cấm riêng từng lớp MUST được gỡ khỏi giao diện cài đặt lớp. Giới hạn môn được phép của lớp vẫn
  áp dụng qua danh sách agent nền tảng gửi cho Dify mỗi lượt (FR-003).
- **FR-014**: Tool chỉ được dùng khi tool đó có trong cấu hình của agent và người dùng có vai trò phù hợp.
  Mọi lần gọi tool MUST được ghi lại.
- **FR-015**: Kiểm tra đồng ý của phụ huynh, vai trò và quyền truy cập lớp MUST vẫn do nền tảng quyết định
  trước khi bất kỳ nội dung nào được gửi tới Dify.
- **FR-016**: Thông tin nhận dạng gửi tới Dify MUST chỉ là mã định danh, không gồm email hay tên người dùng.

**Agent, Hub và kiểm định**

- **FR-017**: Mỗi phiên bản agent (nền tảng hoặc do giáo viên tạo) MUST chạy được trên Dify mà không cần
  ai cấu hình tay trong giao diện Dify.
- **FR-018**: Phiên bản agent MUST giữ tính bất biến. Sửa agent tạo phiên bản mới, và phiên bản mới phải kiểm
  định lại trước khi tới học sinh hoặc phụ huynh.
- **FR-019**: Pipeline kiểm định MUST chạy các tình huống của mình qua đúng lõi Dify mà người dùng thật sẽ dùng.
  Mỗi tình huống MUST bắt đầu một hội thoại Dify mới để kết quả không phụ thuộc lượt trước.

**Tài liệu lớp**

- **FR-020**: Agent bật tài liệu lớp MUST trả lời được dựa trên tài liệu của đúng lớp đó và MUST không truy
  cập được tài liệu của lớp khác.
- **FR-021**: Tải lên, xử lý lại và xóa tài liệu MUST tiếp tục làm được từ giao diện của nền tảng. Nền tảng
  MUST đồng bộ các thao tác này sang kho tri thức Dify của lớp và hiển thị trạng thái xử lý do Dify báo về.
- **FR-021a**: Mỗi lớp MUST có một kho tri thức riêng trên Dify. Mỗi lượt chat MUST chỉ được tra cứu kho của
  lớp đang chat; lượt chat cá nhân (ngoài lớp) không tra cứu kho nào.

**Tính năng Dify trên giao diện**

- **FR-022**: Giao diện chat MUST hiển thị 2–3 câu hỏi gợi ý tiếp theo sau mỗi câu trả lời hoàn tất (nhấn để
  gửi) và trích dẫn tài liệu/đoạn khi câu trả lời dựa trên tài liệu lớp. Câu hỏi gợi ý MUST qua cùng kiểm
  duyệt đầu ra như câu trả lời.

**Giám sát và đo đạc**

- **FR-023**: Token và chi phí của mỗi lượt MUST được ghi nhận và hiện trên trang chi phí của admin.
- **FR-024**: Các script đo red-team, định tuyến và kiểm định MUST chạy được trên lõi mới và cho kết quả so
  sánh được với lõi cũ.
- **FR-025**: Lõi cũ MUST vẫn bật lại được bằng cấu hình cho tới khi có kết quả so sánh, rồi mới được gỡ bỏ.

**Vận hành**

- **FR-026**: Cấu hình Dify (ứng dụng, workflow, guardrail, định tuyến) MUST được lưu trong repo, đủ để dựng
  lại từ đầu trên máy khác.
- **FR-027**: Bộ test tự động MUST chạy được mà không cần Dify đang chạy.

### Key Entities

- **Phiên bản agent**: cấu hình bất biến của agent (môn, hướng dẫn hệ thống, tool, tài liệu, vai trò mục
  tiêu), gắn với một cấu hình tương ứng trên Dify.
- **Hội thoại**: cuộc trò chuyện của người dùng trong nền tảng, gắn với một hội thoại trên Dify (mã hội
  thoại Dify).
- **Lượt chat**: một tin nhắn và câu trả lời, gồm agent được chọn, lý do chọn, trạng thái (thành công, bị
  chặn, lỗi) và token/chi phí.
- **Sự kiện guardrail**: một lần kiểm duyệt có kết quả chặn hoặc ẩn, gồm giai đoạn, lý do, lớp và người dùng.
- **Lần gọi tool**: tool, tham số đã ẩn thông tin cá nhân, kết quả (thành công, từ chối, lỗi).
- **Chính sách lớp**: môn được phép và các luật dùng của một lớp. Không còn chủ đề cấm riêng (xem FR-013).
- **Tài liệu lớp**: file giáo viên tải lên, trạng thái xử lý, lớp sở hữu, tài liệu tương ứng trong kho tri
  thức Dify của lớp.
- **Kho tri thức lớp**: kho trên Dify gắn 1–1 với một lớp, chứa toàn bộ tài liệu lớp đó.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% luồng trong kịch bản demo (`docs/DEMO.md`) chạy được trên lõi mới, không cần sửa kịch bản.
- **SC-002**: Tỉ lệ chặn trên bộ red-team tiếng Việt không thấp hơn lõi cũ quá 5 điểm phần trăm, và tỉ lệ
  chặn nhầm trên bộ câu hỏi hợp lệ không cao hơn lõi cũ quá 5 điểm phần trăm.
- **SC-003**: Độ chính xác định tuyến trên bộ định tuyến không thấp hơn router từ khóa hiện tại (74%).
- **SC-004**: Chữ đầu tiên của câu trả lời hiện ra trong vòng 3 giây ở 95% lượt chat bình thường khi chạy local.
- **SC-005**: 0 trường hợp số điện thoại, mật khẩu hoặc địa chỉ trong tin nhắn thử nghiệm xuất hiện nguyên
  văn trong dữ liệu lưu trữ, nhật ký Dify hoặc dữ liệu theo dõi.
- **SC-006**: 100% lần chặn trong bộ red-team có bản ghi tương ứng trong nhật ký.
- **SC-007**: 0 trường hợp học sinh lớp B nhận được nội dung từ tài liệu của lớp A trong bộ thử cách ly.
- **SC-008**: Một người mới dựng được toàn bộ hệ thống (gồm Dify) từ README trong vòng 1 giờ.
- **SC-009**: Bảng so sánh lõi cũ và lõi mới (tỉ lệ chặn, chặn nhầm, định tuyến, độ trễ, chi phí mỗi lượt) có
  trong báo cáo đồ án.

## Assumptions

- Dify được tự dựng (self-host) chạy cùng máy demo, với một workspace duy nhất. Máy demo đủ RAM cho Dify.
- Tài khoản, vai trò, lớp, thành viên, đồng ý phụ huynh, Hub, cài đặt agent và báo cáo phụ huynh vẫn thuộc
  nền tảng và không chuyển sang Dify.
- Giao diện người dùng vẫn là giao diện của nền tảng. Người dùng cuối không vào giao diện của Dify.
- Định tuyến chạy trong workflow của Dify (một bước gọi LLM đọc danh sách agent), với danh sách agent do nền
  tảng cung cấp theo từng lượt. Bộ phân loại câu hỏi có sẵn của Dify dùng cho phân loại an toàn (research R2, R3).
- Guardrail dùng khả năng kiểm duyệt nội dung có sẵn của Dify (bộ từ khóa và/hoặc dịch vụ kiểm duyệt).
  Những yêu cầu an toàn Dify không có sẵn (ẩn thông tin cá nhân, trả lời tự làm hại, ghi nhật ký) vẫn MUST
  được đáp ứng; cách đáp ứng sẽ chốt ở bước plan.
- Kho tri thức: tài liệu lớp chuyển sang kho tri thức của Dify, mỗi lớp một kho. Kho tài liệu hiện tại của
  nền tảng không còn dùng cho chat khi feature hoàn tất. Tài liệu đã có của lớp demo được chuyển sang khi
  khởi tạo dữ liệu.
- Khóa API của mô hình được cấu hình trong Dify cho phần agent. Các phần còn lại của nền tảng (báo cáo phụ
  huynh, giám khảo kiểm định) dùng khóa riêng như hiện nay.
- Feature này thay thế phương án lai trong `docs/PLAN-DIFY.md`. Tài liệu đó được thay bằng thư mục
  `specs/001-dify-core-migration/`; việc xóa hay giữ file cũ do chủ dự án quyết (task T080).
- Giấy phép Dify Open Source cho phép dùng trong đồ án một workspace.
