# Feature Specification: Xử lý yêu cầu nhiều bước với nhiều agent phối hợp

**Feature Branch**: `002-multi-agent-orchestration` (chưa tạo nhánh; hiện đang ở `feat/dify-runtime`)

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "tôi thấy các đề xuất của bạn ổn rồi, tạo spec hoàn thiện theo đề xuất của bạn luôn giúp tôi"
(đề xuất đã thống nhất trong hội thoại: hệ thống phải linh hoạt; khi việc cần đến agent B thì B phải đóng góp dù
không được gọi; biết tự hỏi lại người dùng khi thiếu thông tin và xin xác nhận khi cần; xử lý theo quá trình phân
tích → làm việc → kết quả; nhiều agent cùng làm nhưng người dùng chỉ đọc một kết quả cuối ngắn gọn; mỗi lượt tối
đa một lần dừng để hỏi, mỗi lần tối đa 3 câu; xác nhận hành động không tính vào giới hạn này.)

## Bối cảnh

Sau feature 001, mỗi lượt chat đi theo một đường cố định: sàng lọc an toàn và chọn **một** agent, agent đó trả
lời, rồi kiểm duyệt đầu ra. Cách này có ba hạn chế:

1. **Mỗi lượt chỉ một agent.** Cài thêm agent vào lớp chỉ có nghĩa là thêm một cái tên để người dùng `@mention`.
   Một yêu cầu cần chuyên môn của hai agent (ví dụ tìm lý thuyết trong tài liệu lớp rồi gợi ý cách giải) chỉ được
   một agent xử lý.
2. **Không biết hỏi lại.** Yêu cầu mơ hồ ("làm đề ôn cho em") được trả lời ngay theo phỏng đoán của agent, không
   hỏi thêm, cũng không nói rõ đã giả định gì.
3. **Không có quá trình.** Yêu cầu được đưa thẳng cho mô hình, không có bước phân tích, lập kế hoạch hay tổng hợp.

Feature này đổi mỗi lượt chat thành một **quá trình xử lý**: phân tích yêu cầu, hỏi lại nếu thật sự cần, giao
việc cho các agent phù hợp, rồi tổng hợp một kết quả cuối ngắn gọn. Quá trình làm việc được hiển thị gọn để người
dùng biết hệ thống đã làm gì, nhưng không phải đọc lại toàn bộ.

Yêu cầu đơn giản (phần lớn câu hỏi hằng ngày) vẫn đi đường nhanh như hiện nay, không bị chậm thêm.

Các phần sau giữ nguyên như feature 001: cổng đồng ý của phụ huynh, ẩn thông tin cá nhân, sàng lọc an toàn đầu
vào, kiểm duyệt đầu ra, chính sách lớp, quyền dùng công cụ theo agent và vai trò, trích dẫn nguồn, gợi ý câu hỏi
tiếp theo, nhật ký và báo cáo sử dụng.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Hệ thống hỏi lại khi yêu cầu thiếu thông tin quan trọng (Priority: P1)

Học sinh gửi một yêu cầu thiếu thông tin làm thay đổi đáng kể kết quả, ví dụ "làm cho em đề ôn tập". Thay vì đoán,
hệ thống hỏi lại **trong một lần duy nhất**, gom tối đa 3 câu hỏi, mỗi câu có sẵn các lựa chọn để bấm. Học sinh
trả lời (bấm lựa chọn hoặc gõ tự do) hoặc bấm "Cứ làm luôn". Hệ thống làm tiếp từ chỗ đã dừng và nêu rõ các giả
định cho những gì không hỏi.

Với yêu cầu đã đủ rõ, hệ thống không hỏi gì thêm.

**Why this priority**: Đây là thay đổi dễ thấy nhất về "hệ thống biết suy nghĩ trước khi trả lời". Story này
không cần nhiều agent nên làm và demo được độc lập, kể cả trong lớp chỉ cài một agent.

**Independent Test**: Trong lớp demo, gửi "làm đề ôn tập cho em" và "giải giúp em bước đầu của phương trình
2x + 3 = 7". Câu đầu phải nhận được một lần hỏi lại (≤ 3 câu, có lựa chọn); câu sau phải được trả lời ngay. Trả
lời câu hỏi lại và kiểm tra kết quả dùng đúng thông tin vừa trả lời.

**Acceptance Scenarios**:

1. **Given** học sinh gửi yêu cầu thiếu thông tin làm thay đổi kết quả, **When** hệ thống phân tích, **Then** hệ
   thống dừng lại hỏi đúng một lần, gồm 1–3 câu hỏi, câu nào có thể thì kèm lựa chọn, và có nút "Cứ làm luôn".
2. **Given** hệ thống đang chờ trả lời câu hỏi lại, **When** học sinh bấm lựa chọn hoặc gõ câu trả lời, **Then**
   hệ thống làm tiếp yêu cầu ban đầu, không bắt học sinh nhắc lại yêu cầu, và kết quả phản ánh thông tin vừa
   cung cấp.
3. **Given** hệ thống đang chờ trả lời, **When** học sinh bấm "Cứ làm luôn", **Then** hệ thống làm tiếp với các
   giả định hợp lý và ghi rõ các giả định đó trong kết quả.
4. **Given** hệ thống đang chờ trả lời, **When** học sinh gửi một yêu cầu không liên quan, **Then** câu hỏi đang
   chờ bị huỷ và yêu cầu mới được xử lý như bình thường.
5. **Given** yêu cầu thiếu một chi tiết nhưng chi tiết đó ít ảnh hưởng tới kết quả, **When** hệ thống xử lý,
   **Then** hệ thống không hỏi mà tự giả định và nêu giả định trong kết quả.
6. **Given** lượt này đã hỏi lại một lần và câu trả lời của người dùng làm nảy sinh câu hỏi mới, **When** hệ thống
   làm tiếp, **Then** hệ thống không hỏi lần thứ hai mà tự giả định và nêu giả định.

---

### User Story 2 - Nhiều agent cùng đóng góp, người dùng chỉ đọc một kết quả ngắn gọn (Priority: P1)

Một yêu cầu cần chuyên môn của nhiều agent có trong lớp. Hệ thống tự phân tích, chia yêu cầu thành các phần việc
và giao cho các agent phù hợp, **kể cả agent người dùng không gọi tên**. Các agent làm phần việc của mình; agent
chịu trách nhiệm chính tổng hợp lại thành **một** câu trả lời cuối ngắn gọn, đi thẳng vào điều người dùng cần.
Người dùng không phải đọc các bản nháp trung gian.

Ví dụ: học sinh hỏi "giải thích lại định lý Pytago theo đúng tài liệu cô gửi rồi cho em một bài luyện". Agent
Ôn tập tài liệu tìm phần lý thuyết trong tài liệu lớp, agent Tạo đề soạn bài luyện, Gia sư Toán là agent chính và
viết câu trả lời cuối có trích nguồn tài liệu.

**Why this priority**: Đây là lý do của feature: thêm agent vào lớp phải làm cả lớp mạnh lên, chứ không chỉ thêm
một lựa chọn để gọi.

**Independent Test**: Trong lớp demo đã cài đủ agent mẫu, gửi các yêu cầu trong bộ đánh giá "nhiều agent". Kiểm
tra đúng các agent cần thiết tham gia, có một câu trả lời cuối ngắn gọn, và giao diện cho biết những agent nào đã
đóng góp.

**Acceptance Scenarios**:

1. **Given** yêu cầu cần chuyên môn của hai agent trong lớp, **When** người dùng gửi mà không `@mention` ai,
   **Then** cả hai agent đều được giao việc và phần đóng góp của cả hai có mặt trong kết quả cuối.
2. **Given** người dùng `@mention` agent A cho một yêu cầu mà agent B cũng góp được một phần, **When** hệ thống
   xử lý, **Then** A là agent chính trả lời và B vẫn được giao phần việc của mình.
3. **Given** nhiều agent đã làm xong phần việc, **When** hệ thống trả kết quả, **Then** người dùng chỉ thấy một
   câu trả lời cuối do agent chính viết, không thấy nguyên văn bản nháp trung gian, và kết quả ghi tên các agent
   đã đóng góp.
4. **Given** yêu cầu đơn giản chỉ cần một agent, **When** người dùng gửi, **Then** hệ thống trả lời như hiện nay,
   không đi qua quá trình nhiều bước và không chậm hơn.
5. **Given** một phần việc gặp lỗi hoặc quá thời gian, **When** các phần khác đã xong, **Then** kết quả cuối vẫn
   được trả về từ các phần đã xong và nói rõ phần nào chưa làm được.
6. **Given** lớp chỉ cài một agent, **When** người dùng gửi yêu cầu phức tạp, **Then** hệ thống vẫn phân tích và
   có thể hỏi lại, nhưng mọi phần việc do agent đó làm.

---

### User Story 3 - Xem quá trình làm việc ở dạng gọn (Priority: P2)

Trong lúc hệ thống xử lý một yêu cầu phức tạp, người dùng thấy một khung "đang làm việc" cập nhật theo thời gian
thực: phân tích yêu cầu, từng phần việc với tên và avatar của agent đang làm, trạng thái (đang làm, xong, lỗi).
Khi có kết quả cuối, khung này tự thu gọn thành một dòng tóm tắt (ví dụ "Đã làm việc · 3 agent · 12 giây"), mở ra
được khi muốn xem lại.

**Why this priority**: Quá trình nhiều bước mất nhiều thời gian hơn. Không có khung này, người dùng chỉ thấy màn
hình đứng yên. Khung này cũng là cách thể hiện "cả đội agent" khi demo. Story phụ thuộc story 2 nên xếp P2.

**Independent Test**: Gửi một yêu cầu trong bộ "nhiều agent", quan sát khung tiến trình cập nhật trong lúc chạy,
thu gọn khi xong, và mở lại được. Tải lại trang, mở lại hội thoại và kiểm tra khung tóm tắt vẫn còn.

**Acceptance Scenarios**:

1. **Given** hệ thống đang xử lý yêu cầu nhiều bước, **When** một phần việc bắt đầu hoặc kết thúc, **Then** khung
   tiến trình cập nhật ngay, hiển thị tên agent và mô tả ngắn của phần việc đó.
2. **Given** kết quả cuối đã xong, **When** người dùng nhìn câu trả lời, **Then** khung tiến trình đã thu gọn
   thành một dòng tóm tắt, và kết quả cuối là phần nổi bật nhất.
3. **Given** người dùng là học sinh hoặc phụ huynh, **When** mở khung tiến trình, **Then** chỉ thấy tiêu đề và
   trạng thái của từng phần việc, không thấy bản nháp trung gian.
4. **Given** người dùng là giáo viên trong hội thoại của chính mình, **When** mở một phần việc, **Then** thấy được
   ghi chú làm việc của agent cho phần đó.
5. **Given** yêu cầu đi đường nhanh (một agent), **When** trả lời, **Then** không hiển thị khung tiến trình.
6. **Given** người dùng mở lại một hội thoại cũ, **When** xem một câu trả lời từng đi qua nhiều bước, **Then** dòng
   tóm tắt quá trình vẫn hiển thị và mở ra được.

---

### User Story 4 - Xin xác nhận trước những việc quan trọng (Priority: P2)

Trước khi thực hiện một hành động có tác dụng ra ngoài cuộc trò chuyện (ví dụ giao bài cho cả lớp, gửi thông báo
cho phụ huynh, ghi điểm), hoặc khi agent sắp làm một việc lớn dựa trên một cách hiểu có thể sai, hệ thống trình
bày ngắn gọn việc sắp làm và chờ người dùng bấm "Đồng ý" hoặc "Không". Với hành động có tác dụng ra ngoài, việc
xác nhận là **bắt buộc**, do nền tảng ép buộc chứ không do agent tự quyết, và không tính vào giới hạn hỏi lại.

**Why this priority**: Hiện chưa có công cụ nào có tác dụng ra ngoài (các công cụ hiện tại chỉ đọc hoặc tạo nội
dung trong cuộc trò chuyện). Cơ chế này cần có trước khi thêm những công cụ đó, và đã dùng được ngay cho việc xác
nhận cách hiểu của agent. Vì vậy xếp P2.

**Independent Test**: Đánh dấu một công cụ thử nghiệm là "cần xác nhận", cho agent gọi công cụ đó. Kiểm tra công
cụ không chạy khi chưa có xác nhận, chạy sau khi bấm "Đồng ý", và không chạy khi bấm "Không".

**Acceptance Scenarios**:

1. **Given** agent muốn dùng một công cụ được đánh dấu "cần xác nhận", **When** tới bước đó, **Then** hệ thống
   dừng lại, trình bày việc sắp làm, và công cụ chưa chạy.
2. **Given** hệ thống đang chờ xác nhận, **When** người dùng bấm "Đồng ý", **Then** công cụ chạy với đúng tham số
   đã trình bày và hệ thống làm tiếp.
3. **Given** hệ thống đang chờ xác nhận, **When** người dùng bấm "Không" hoặc gửi yêu cầu khác, **Then** công cụ
   không chạy và kết quả cuối nói rõ việc đó chưa được thực hiện.
4. **Given** lượt này đã dùng hết lần hỏi lại, **When** cần xác nhận một hành động có tác dụng ra ngoài, **Then**
   hệ thống vẫn dừng lại xin xác nhận.
5. **Given** người dùng xác nhận quá muộn (sau thời hạn chờ), **When** bấm "Đồng ý", **Then** hành động không chạy
   và hệ thống báo yêu cầu đã hết hạn.

---

### User Story 5 - Agent tự nhờ agent khác khi gặp việc ngoài chuyên môn (Priority: P3)

Trong lúc làm, agent phát hiện một việc mà bước phân tích ban đầu không thấy trước: việc ngoài chuyên môn của
mình, việc agent khác làm tốt hơn, hoặc thông tin chỉ người dùng mới biết. Agent báo lại cho hệ thống. Hệ thống
giao việc đó cho agent phù hợp (hoặc hỏi người dùng nếu lượt này chưa hỏi lần nào), rồi cho agent ban đầu làm
tiếp với kết quả mới.

**Why this priority**: Làm hệ thống linh hoạt hơn khi kế hoạch ban đầu chưa đủ, nhưng phần lớn giá trị đã có từ
story 1 và 2. Story này phức tạp và rủi ro hơn nên làm sau.

**Independent Test**: Dùng một yêu cầu mà chỉ khi đọc tài liệu lớp mới thấy cần agent khác. Kiểm tra agent ban
đầu báo lại, agent thứ hai được giao việc, và kết quả cuối có phần đóng góp của cả hai.

**Acceptance Scenarios**:

1. **Given** agent đang làm gặp việc ngoài chuyên môn mà một agent khác trong lớp làm được, **When** agent báo cần
   hỗ trợ, **Then** hệ thống giao việc cho agent phù hợp và agent ban đầu nhận được kết quả để làm tiếp.
2. **Given** agent báo cần hỗ trợ nhưng không agent nào trong lớp làm được việc đó, **When** hệ thống xử lý,
   **Then** kết quả cuối nói rõ phần đó nằm ngoài khả năng của các agent trong lớp.
3. **Given** agent báo cần thông tin từ người dùng và lượt này chưa hỏi lần nào, **When** hệ thống xử lý,
   **Then** hệ thống dừng lại hỏi người dùng theo đúng quy tắc ở story 1.
4. **Given** agent báo cần thông tin nhưng lượt này đã hỏi rồi, **When** hệ thống xử lý, **Then** agent làm tiếp
   với giả định hợp lý và nêu giả định.
5. **Given** agent B được nhờ lại muốn nhờ ngược agent A hoặc nhờ tiếp agent khác, **When** hệ thống xử lý,
   **Then** yêu cầu nhờ tiếp bị từ chối và B phải tự hoàn thành phần việc của mình.

---

### Edge Cases

- **Câu trả lời cho câu hỏi lại vi phạm an toàn.** Câu trả lời này là tin nhắn mới của người dùng: nó đi qua cổng
  đồng ý, bước ẩn thông tin cá nhân và sàng lọc an toàn như mọi tin nhắn khác. Nếu bị chặn thì yêu cầu đang chờ
  cũng bị huỷ.
- **Phụ huynh rút lại đồng ý trong lúc hệ thống đang chờ học sinh trả lời.** Khi học sinh trả lời, cổng đồng ý
  chặn lại như bình thường và yêu cầu đang chờ bị huỷ.
- **Một agent trong kế hoạch bị gỡ khỏi lớp trong lúc chờ người dùng trả lời.** Khi làm tiếp, hệ thống lập lại kế
  hoạch chỉ với các agent còn dùng được.
- **Người dùng bỏ đi giữa chừng (đóng trang, mất mạng).** Mọi phần việc đang chạy dừng lại. Không có hành động có
  tác dụng ra ngoài nào chạy sau khi người dùng đã rời đi.
- **Người dùng quay lại trả lời sau thời hạn chờ.** Yêu cầu đang chờ đã hết hạn. Tin nhắn được xử lý như một yêu
  cầu mới, và hệ thống cho người dùng biết.
- **Vượt giới hạn số phần việc, số agent hoặc thời gian.** Hệ thống dừng giao thêm việc và tổng hợp từ những gì đã
  có, nói rõ phần nào chưa làm.
- **Tất cả phần việc đều lỗi.** Người dùng nhận thông báo lỗi thân thiện như khi một lượt chat thường bị lỗi;
  không có kết quả nửa vời.
- **Bước phân tích lỗi hoặc trả về kế hoạch không hợp lệ.** Hệ thống quay về đường nhanh (một agent) thay vì báo
  lỗi.
- **Kế hoạch giao việc cho agent không có trong lớp hoặc không dành cho vai trò này.** Phần việc đó được giao lại
  cho agent chính hoặc bỏ qua; không agent ngoài danh sách nào được chạy.
- **Lách chính sách lớp qua phối hợp.** Ví dụ học sinh nhờ Gia sư Toán, Gia sư Toán lại nhờ agent Chấm văn viết
  hộ cả bài văn. Mỗi phần việc đều theo chính sách lớp, và kết quả cuối vẫn đi qua kiểm duyệt đầu ra.
- **Sàng lọc phát hiện dấu hiệu tự làm hại.** Không lập kế hoạch nhiều bước và không hỏi lại. Hệ thống đi thẳng
  luồng hỗ trợ an toàn như hiện nay.
- **Chế độ không có người thật** (chứng nhận agent, bộ đánh giá, sandbox thử agent). Không có ai để trả lời: mọi
  câu hỏi lại được xử lý như "Cứ làm luôn" và mọi xác nhận được coi là "Không".
- **Người dùng gửi tin nhắn mới trong lúc lượt trước vẫn đang chạy.** Giữ hành vi hiện tại của giao diện (không
  cho gửi khi đang có câu trả lời chạy), không chạy hai quá trình song song trong cùng hội thoại.

## Requirements *(mandatory)*

### Functional Requirements

**Phân tích và chọn đường xử lý**

- **FR-001**: Hệ thống MUST phân tích mọi yêu cầu đã qua sàng lọc an toàn để quyết định đi **đường nhanh** (một
  agent trả lời như hiện nay) hay **đường đầy đủ** (phân tích, có thể hỏi lại, nhiều phần việc, tổng hợp).
- **FR-002**: Đường nhanh MUST giữ nguyên trải nghiệm hiện tại: không hiển thị khung tiến trình và không thêm bước
  làm chậm thời gian tới chữ đầu tiên (xem SC-001).
- **FR-003**: Ở đường đầy đủ, hệ thống MUST xác định: mục tiêu của yêu cầu, agent chính chịu trách nhiệm kết quả
  cuối, thông tin còn thiếu (nếu có), các hành động cần xác nhận (nếu có), và danh sách phần việc kèm agent làm
  và thứ tự phụ thuộc giữa chúng.
- **FR-004**: Việc chọn agent cho các phần việc MUST dựa trên mô tả và năng lực đã khai báo của **toàn bộ** agent
  dùng được trong lớp với vai trò hiện tại, không chỉ agent được người dùng chọn hay `@mention`.
- **FR-005**: Khi người dùng chọn hoặc `@mention` một agent, agent đó MUST là agent chính; các agent khác vẫn có
  thể được giao phần việc phụ.
- **FR-006**: Nếu bước phân tích lỗi hoặc trả về kết quả không dùng được, hệ thống MUST quay về đường nhanh.

**Hỏi lại người dùng**

- **FR-007**: Hệ thống MUST chỉ hỏi lại khi thiếu thông tin làm thay đổi đáng kể kết quả. Với thông tin thiếu
  nhưng ít ảnh hưởng, hệ thống MUST tự giả định và nêu rõ giả định trong kết quả cuối.
- **FR-008**: Mỗi lượt MUST có tối đa **1 lần** dừng để hỏi lại, mỗi lần tối đa **3 câu hỏi**. Hai giới hạn này
  MUST chỉnh được trong cấu hình mà không phải sửa logic.
- **FR-009**: Mỗi câu hỏi lại SHOULD kèm các lựa chọn để bấm khi có thể; người dùng MUST luôn gõ trả lời tự do
  được.
- **FR-010**: Mỗi lần hỏi lại MUST có lựa chọn "Cứ làm luôn" để bỏ qua phần hỏi và để hệ thống tự giả định.
- **FR-011**: Khi người dùng trả lời, hệ thống MUST làm tiếp yêu cầu ban đầu từ chỗ đã dừng, giữ nguyên các phần
  việc đã xong, không bắt người dùng nhắc lại yêu cầu.
- **FR-012**: Khi người dùng gửi tin nhắn không phải là câu trả lời cho câu hỏi đang chờ, hệ thống MUST huỷ yêu
  cầu đang chờ và xử lý tin nhắn mới như bình thường.
- **FR-013**: Yêu cầu đang chờ trả lời MUST hết hạn sau một khoảng thời gian cấu hình được (mặc định 24 giờ).

**Xác nhận hành động**

- **FR-014**: Công cụ MUST khai báo được thuộc tính "cần xác nhận". Nền tảng MUST không chạy một công cụ có thuộc
  tính này khi người dùng chưa xác nhận rõ ràng cho đúng lần gọi đó, bất kể agent hay nội dung hội thoại nói gì.
- **FR-015**: Yêu cầu xác nhận MUST trình bày ngắn gọn việc sắp làm (công cụ, tác động, đối tượng chịu tác động)
  và có hai lựa chọn "Đồng ý" và "Không".
- **FR-016**: Xác nhận cho hành động có tác dụng ra ngoài MUST không tính vào giới hạn hỏi lại ở FR-008.
- **FR-017**: Agent MAY xin xác nhận cách hiểu của mình trước một việc lớn; loại xác nhận này tính như một lần
  hỏi lại (theo FR-008).
- **FR-018**: Hành động được xác nhận MUST chạy với đúng tham số đã trình bày cho người dùng. Hành động bị từ chối,
  hết hạn hoặc bị huỷ MUST không chạy, và kết quả cuối MUST nói rõ việc đó chưa được thực hiện.

**Thực hiện các phần việc**

- **FR-019**: Các phần việc không phụ thuộc nhau SHOULD chạy đồng thời; phần việc phụ thuộc MUST chỉ chạy sau khi
  các phần nó cần đã xong và MUST nhận được kết quả của các phần đó.
- **FR-020**: Mỗi phần việc MUST chạy với vai trò, hướng dẫn, công cụ và quyền của **chính agent làm phần việc
  đó**, và MUST tuân theo quy tắc nền tảng và chính sách của lớp hiện tại.
- **FR-021**: Mỗi phần việc MUST chỉ nhận thông tin cần cho phần việc đó (yêu cầu, mô tả phần việc, kết quả các
  phần liên quan), và MUST không làm lẫn ngữ cảnh hội thoại chính của người dùng.
- **FR-022**: Kết quả của mỗi phần việc MUST là ghi chú làm việc gửi cho agent chính, không phải câu trả lời gửi
  thẳng cho người dùng.
- **FR-023**: Trong lúc làm, agent MUST báo được ba loại tín hiệu: cần agent khác hỗ trợ một việc, cần thông tin
  từ người dùng, cần xác nhận một hành động. Hệ thống MUST xử lý các tín hiệu này theo FR-008 và FR-014 đến
  FR-018, rồi cho agent làm tiếp.
- **FR-024**: Agent được nhờ MUST không được nhờ tiếp agent khác (độ sâu nhờ tối đa là 1).
- **FR-025**: Mỗi lượt MUST có giới hạn cấu hình được về số phần việc (mặc định 5), số agent tham gia (mặc định 3),
  số lần lập lại kế hoạch (mặc định 1) và tổng thời gian xử lý. Khi chạm giới hạn, hệ thống MUST dừng giao thêm
  việc và chuyển sang tổng hợp.
- **FR-026**: Khi một phần việc lỗi hoặc quá thời gian, hệ thống MUST tiếp tục với các phần còn lại và kết quả
  cuối MUST nói rõ phần nào chưa làm được.

**Tổng hợp kết quả cuối**

- **FR-027**: Ở đường đầy đủ, agent chính MUST viết **một** kết quả cuối từ các ghi chú làm việc. Đây là phần duy
  nhất hiện dần ra cho người dùng.
- **FR-028**: Kết quả cuối MUST ngắn gọn, trả lời thẳng mục tiêu của yêu cầu, nêu các giả định đã dùng (nếu có),
  và MUST không chép nguyên văn các ghi chú làm việc.
- **FR-029**: Kết quả cuối MUST giữ trích dẫn nguồn tài liệu từ các phần việc có dùng tài liệu lớp, và MUST ghi tên
  các agent đã đóng góp.
- **FR-030**: Kết quả cuối MUST đi qua kiểm duyệt đầu ra như câu trả lời hiện nay. Gợi ý câu hỏi tiếp theo chỉ
  hiển thị cho kết quả không bị chặn.
- **FR-031**: Ngữ cảnh hội thoại để agent nhớ ở các lượt sau MUST gồm yêu cầu của người dùng, các câu hỏi lại và
  câu trả lời của người dùng, và kết quả cuối; không gồm ghi chú làm việc trung gian.

**Hiển thị quá trình**

- **FR-032**: Ở đường đầy đủ, giao diện MUST hiển thị khung tiến trình cập nhật theo thời gian thực: bước phân
  tích, từng phần việc với tên, avatar của agent và trạng thái (chờ, đang làm, xong, lỗi, bỏ qua).
- **FR-033**: Khi có kết quả cuối, khung tiến trình MUST thu gọn thành một dòng tóm tắt (số agent, thời gian) và
  MUST mở lại được.
- **FR-034**: Học sinh và phụ huynh MUST chỉ thấy tiêu đề và trạng thái của phần việc, không thấy ghi chú làm việc.
  Giáo viên MAY xem ghi chú làm việc trong hội thoại của chính mình.
- **FR-035**: Quá trình làm việc của một câu trả lời MUST được lưu cùng câu trả lời, để khi mở lại hội thoại vẫn
  xem được dòng tóm tắt và danh sách phần việc.
- **FR-036**: Câu hỏi lại và yêu cầu xác nhận MUST hiển thị như một tin nhắn của hệ thống trong hội thoại, kèm các
  lựa chọn bấm được; sau khi người dùng trả lời, các lựa chọn MUST không bấm lại được.

**An toàn, quyền và độ bền**

- **FR-037**: Cổng đồng ý của phụ huynh, bước ẩn thông tin cá nhân và sàng lọc an toàn MUST chạy trước bước phân
  tích ở mọi tin nhắn, kể cả tin nhắn trả lời câu hỏi lại hoặc xác nhận.
- **FR-038**: Khi sàng lọc chặn tin nhắn hoặc phát hiện dấu hiệu cần hỗ trợ an toàn, hệ thống MUST không lập kế
  hoạch nhiều bước, không hỏi lại, và MUST xử lý như hiện nay.
- **FR-039**: Chỉ các agent dùng được trong lớp với vai trò hiện tại MUST được giao việc. Mọi chỉ định agent khác
  (từ kế hoạch, từ tín hiệu của agent, từ nội dung người dùng) MUST bị bỏ qua.
- **FR-040**: Khi người dùng rời đi giữa chừng, mọi phần việc đang chạy MUST dừng lại, và MUST không có hành động
  có tác dụng ra ngoài nào chạy sau đó.
- **FR-041**: Ở chế độ không có người thật (chứng nhận agent, bộ đánh giá, sandbox), hệ thống MUST coi mọi câu hỏi
  lại là "Cứ làm luôn" và mọi xác nhận là "Không".

**Ghi nhận và đo lường**

- **FR-042**: Hệ thống MUST ghi nhận cho mỗi lượt: đường xử lý đã chọn, kế hoạch, từng phần việc (agent, trạng
  thái, thời gian), các lần hỏi lại và xác nhận cùng kết quả, và lượng sử dụng mô hình theo từng agent và từng
  bước, để báo cáo sử dụng và truy vết hiện có tiếp tục đúng.
- **FR-043**: Sự kiện an toàn (chặn, hỗ trợ an toàn, kiểm duyệt đầu ra) MUST tiếp tục được ghi như hiện nay và
  MUST ghi được agent của phần việc liên quan.
- **FR-044**: Dự án MUST có bộ đánh giá cho việc phân tích, gồm các ca: yêu cầu đơn giản (kỳ vọng đường nhanh),
  yêu cầu nhiều agent (kỳ vọng tập agent tham gia), yêu cầu mơ hồ (kỳ vọng hỏi lại), yêu cầu rõ ràng (kỳ vọng
  không hỏi lại). Bộ đánh giá MUST chạy được và báo được các chỉ số ở mục Success Criteria.

**Vận hành**

- **FR-045**: Cách chạy local chính thức của dự án MUST dựng được đầy đủ những gì feature cần (các thành phần trên
  nền tảng agent, cấu hình mới, thay đổi dữ liệu) bằng một lệnh, đúng như nguyên tắc III của hiến pháp.

### Key Entities *(include if feature involves data)*

- **Lượt xử lý (Run)**: Quá trình xử lý một yêu cầu, có thể kéo dài qua nhiều tin nhắn khi phải hỏi lại. Thuộc về
  một hội thoại. Có đường xử lý (nhanh hay đầy đủ), trạng thái (đang chạy, chờ người dùng, xong, lỗi, đã huỷ, hết
  hạn), thời điểm hết hạn khi đang chờ, số lần đã hỏi lại và số lần đã lập lại kế hoạch. Mỗi hội thoại có tối đa
  một lượt xử lý đang chờ người dùng.
- **Kế hoạch**: Kết quả phân tích của một lượt xử lý: mục tiêu, agent chính, thông tin còn thiếu, hành động cần
  xác nhận, danh sách phần việc. Có thể có phiên bản mới khi lập lại kế hoạch.
- **Phần việc (Step)**: Một việc giao cho một agent trong kế hoạch: agent làm, mô tả, các phần việc phụ thuộc,
  trạng thái, thời gian, ghi chú làm việc, các tín hiệu agent đã báo, nguồn tài liệu đã dùng.
- **Yêu cầu chờ người dùng**: Một lần hỏi lại (1–3 câu hỏi, mỗi câu có thể có lựa chọn) hoặc một yêu cầu xác nhận
  (hành động, tham số, tác động). Lưu cả câu trả lời của người dùng, hoặc ghi nhận "Cứ làm luôn", từ chối, hết
  hạn.
- **Agent (đã có)**: Bổ sung vai trò trong một lượt: agent chính hoặc agent đóng góp. Năng lực đã khai báo của agent
  là căn cứ để giao việc.
- **Công cụ (đã có)**: Bổ sung thuộc tính "cần xác nhận".
- **Tin nhắn trả lời (đã có)**: Gắn với lượt xử lý tạo ra nó. Lưu agent chính, các agent đóng góp và tóm tắt quá
  trình để hiển thị lại.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Với yêu cầu đơn giản, thời gian tới khi chữ đầu tiên hiện ra (trung vị) tăng không quá 10% so với
  trước feature, đo trên cùng bộ câu hỏi.
- **SC-002**: Trên bộ đánh giá, ít nhất 90% yêu cầu đơn giản đi đường nhanh, và ít nhất 85% yêu cầu nhiều agent
  có đúng tập agent tham gia như kỳ vọng (không thiếu agent cần thiết, thừa tối đa một agent).
- **SC-003**: Tỉ lệ hỏi thừa (hỏi lại với yêu cầu đã đủ rõ) không quá 10%; tỉ lệ hỏi đúng lúc (hỏi lại với yêu
  cầu thật sự mơ hồ) đạt ít nhất 80%.
- **SC-004**: 100% lượt tuân thủ giới hạn: tối đa 1 lần hỏi lại, tối đa 3 câu mỗi lần, và các giới hạn về số phần
  việc và số agent.
- **SC-005**: 0 hành động có tác dụng ra ngoài chạy mà không có xác nhận rõ ràng của người dùng, kiểm tra bằng các
  ca thử cố tình yêu cầu agent bỏ qua xác nhận.
- **SC-006**: Với yêu cầu đi đường đầy đủ, 90% lượt có kết quả cuối trong vòng 45 giây (không tính thời gian chờ
  người dùng trả lời), và khung tiến trình có cập nhật đầu tiên trong vòng 3 giây.
- **SC-007**: Kết quả cuối ở đường đầy đủ dài không quá 300 từ trong ít nhất 90% lượt, trừ khi người dùng yêu cầu
  chi tiết hoặc yêu cầu bản thân là tạo nội dung dài (ví dụ đề ôn tập).
- **SC-008**: Trên bộ red-team hiện có cộng thêm các ca lách chính sách qua phối hợp, tỉ lệ nội dung vi phạm lọt ra
  kết quả cuối không cao hơn so với khi chỉ một agent trả lời.
- **SC-009**: Trong buổi thử với người dùng mẫu, ít nhất 4/5 người trả lời đúng câu hỏi "những agent nào đã giúp
  trả lời câu này?" chỉ bằng cách nhìn giao diện.
- **SC-010**: 100% yêu cầu đang chờ người dùng có thể làm tiếp sau khi tải lại trang hoặc mở lại hội thoại (trong
  thời hạn chờ).

## Assumptions

- Nền tảng agent vẫn là Dify như feature 001; feature này không đưa lại engine chạy agent trong backend. Nền tảng
  giữ vai trò điều phối quá trình (trạng thái, kế hoạch, giới hạn, xác nhận); mọi lời gọi mô hình, agent, công cụ
  và kiểm duyệt vẫn chạy trên Dify.
- Phần lớn câu hỏi hằng ngày chỉ cần một agent, nên đường nhanh là mặc định. Chỉ yêu cầu phức tạp mới đi đường đầy
  đủ.
- Các giới hạn mặc định (1 lần hỏi lại mỗi lượt, 3 câu mỗi lần, 5 phần việc, 3 agent, 1 lần lập lại kế hoạch,
  chờ người dùng 24 giờ) là điểm khởi đầu và sẽ được chỉnh theo kết quả đánh giá.
- Phối hợp nhiều agent được bật cho mọi lớp; chưa có tuỳ chọn bật tắt theo lớp trong phạm vi này.
- Hiện chưa có công cụ nào có tác dụng ra ngoài cuộc trò chuyện. Cơ chế xác nhận được xây và kiểm thử bằng công cụ
  thử nghiệm; các công cụ thật (giao bài, gửi thông báo) là feature sau.
- Không gian cá nhân (không thuộc lớp) cũng dùng quá trình mới, với các agent dùng được trong không gian đó.
- Giao diện vẫn chỉ cho gửi một tin nhắn khi không có câu trả lời nào đang chạy, như hiện nay.
- Năng lực khai báo trong manifest của các agent mẫu đủ tốt để chia việc; nếu bộ đánh giá cho thấy chưa đủ, manifest
  mẫu sẽ được viết lại trong phạm vi feature này.
- Ngoài phạm vi: việc chạy nền và trả kết quả sau (ví dụ chấm cả bộ bài), chuyển yêu cầu lên giáo viên là người
  thật, các agent tự góp ý sau khi câu trả lời đã xong (khi không có trong kế hoạch), và đánh giá thích/không thích
  câu trả lời.
