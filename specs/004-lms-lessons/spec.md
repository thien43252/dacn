# Feature Specification: Buổi học, tài liệu, video, bài tập và bài kiểm tra trong lớp (LMS)

**Feature Branch**: phát triển trực tiếp trên `main`

**Created**: 2026-11-16

**Status**: Draft

**Input**: User description: "giờ tôi muốn hệ thống của tôi có các chức năng như một trang lms thông thường như tạo buổi
học (trong buổi học có thể thêm tài liệu, video, bài tập, tạo bài kiểm tra, quiz, ....)"

## Clarifications

### Session 2026-11-16

- Q: Agent AI có hỗ trợ giáo viên tạo nội dung và chấm bài không? → A: Có (phương án C): gợi ý câu hỏi quiz từ tài liệu
  của buổi học, và gợi ý điểm cùng nhận xét cho câu tự luận và bài tập. Mọi gợi ý chỉ có hiệu lực khi giáo viên duyệt
  (FR-031 – FR-036).

## Bối cảnh

### Hiện trạng trên `main`

- Giáo viên tạo lớp, thêm học sinh bằng mã lớp, phụ huynh liên kết với con. Lớp có các tab: Thành viên, Agent, Tài
  liệu, Tiến độ, Chính sách, Nhật ký.
- Tab "Tài liệu" hiện chỉ là **kho tri thức cho agent**: giáo viên tải tài liệu lên để agent đọc khi trả lời trong lớp.
  Học sinh không duyệt tài liệu theo buổi, không có khái niệm buổi học.
- Không có bài tập, nộp bài, chấm điểm, quiz hay bài kiểm tra. "Tiến độ" chỉ phản ánh việc học sinh hỏi agent.

### Mục tiêu

Biến mỗi lớp thành một khóa học kiểu LMS: giáo viên tổ chức nội dung theo **buổi học**; trong mỗi buổi gắn tài liệu,
video, bài tập và quiz/bài kiểm tra; học sinh học theo buổi, nộp bài, làm bài kiểm tra và xem điểm; phụ huynh theo dõi
kết quả của con. Feature dùng lại lớp, thành viên, liên kết phụ huynh, kho tài liệu, agent và guard hiện có.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Giáo viên tạo buổi học và đăng tài liệu, video (Priority: P1)

Giáo viên vào lớp, tạo buổi học (tiêu đề, mô tả, ngày học, thứ tự), rồi thêm vào buổi các mục nội dung: tài liệu (tệp
tải lên), video (tệp tải lên hoặc đường link video), liên kết ngoài và đoạn văn bản hướng dẫn. Giáo viên sắp xếp lại
thứ tự buổi và thứ tự mục trong buổi, lưu buổi ở dạng nháp hoặc công bố cho học sinh. Học sinh của lớp thấy danh sách
buổi đã công bố, mở buổi để đọc tài liệu và xem video ngay trong trang.

**Why this priority**: Buổi học là khung xương của mọi chức năng LMS còn lại; chỉ riêng phần này đã cho giáo viên một
nơi phát hành bài giảng cho lớp.

**Independent Test**: Đăng nhập giáo viên demo, tạo một buổi với một tệp PDF và một video, công bố; đăng nhập học sinh
cùng lớp thấy buổi, mở được tệp và phát được video; học sinh lớp khác không thấy.

**Acceptance Scenarios**:

1. **Given** giáo viên là chủ lớp, **When** tạo buổi "Buổi 1 - Phân số" và thêm một tệp PDF, một link video, **Then**
   buổi xuất hiện trong danh sách buổi của lớp ở trạng thái nháp với hai mục đúng thứ tự.
2. **Given** buổi đang ở nháp, **When** học sinh của lớp mở danh sách buổi, **Then** học sinh không thấy buổi đó.
3. **Given** giáo viên công bố buổi, **When** học sinh mở buổi, **Then** học sinh xem được tài liệu và phát được video
   mà không phải rời trang.
4. **Given** giáo viên đặt thời điểm mở buổi trong tương lai, **When** chưa tới thời điểm đó, **Then** học sinh thấy
   buổi ở trạng thái "sắp mở" nhưng chưa xem được nội dung.
5. **Given** giáo viên kéo thả đổi thứ tự hai buổi, **When** học sinh tải lại trang, **Then** thứ tự mới được áp dụng.
6. **Given** giáo viên bật "cho agent đọc" trên một tài liệu của buổi, **When** học sinh hỏi agent của lớp về nội dung
   tài liệu, **Then** agent dùng được tài liệu đó như tài liệu của tab Tài liệu hiện có.

---

### User Story 2 - Giáo viên tạo quiz/bài kiểm tra, học sinh làm bài và được chấm tự động (Priority: P1)

Giáo viên thêm vào buổi một quiz hoặc bài kiểm tra gồm các câu hỏi: trắc nghiệm một đáp án, nhiều đáp án, đúng/sai,
điền vào chỗ trống (đáp án ngắn) và tự luận. Giáo viên đặt điểm từng câu, thời gian làm bài, thời gian mở/đóng, số lần
làm tối đa, có trộn câu hỏi/đáp án không, và khi nào học sinh được xem đáp án. Học sinh làm bài trong thời hạn; câu
khách quan được chấm ngay khi nộp; câu tự luận chờ giáo viên chấm.

"Quiz" và "bài kiểm tra" là cùng một loại nội dung; khác nhau ở cấu hình (quiz thường cho làm nhiều lần, xem đáp án
ngay; bài kiểm tra thường giới hạn thời gian, một lần làm, ẩn đáp án tới khi đóng).

**Why this priority**: Kiểm tra đánh giá là chức năng mà người dùng nêu đích danh và là giá trị khác biệt lớn nhất so
với việc chỉ đăng tài liệu.

**Independent Test**: Giáo viên tạo quiz 5 câu (đủ các loại khách quan), học sinh làm và nộp, thấy điểm ngay; giáo
viên thấy bài nộp và điểm trong bảng kết quả quiz.

**Acceptance Scenarios**:

1. **Given** quiz đang mở với giới hạn 15 phút, **When** học sinh bắt đầu làm, **Then** đồng hồ đếm ngược hiện và bài
   tự nộp khi hết giờ với các câu đã trả lời.
2. **Given** học sinh đang làm dở và mất kết nối hoặc tải lại trang, **When** quay lại trong thời gian làm bài, **Then**
   các câu đã chọn còn nguyên và đồng hồ vẫn tính theo thời điểm bắt đầu ban đầu.
3. **Given** bài có câu trắc nghiệm, đúng/sai, điền chỗ trống, **When** học sinh nộp, **Then** các câu đó được chấm ngay
   theo đáp án giáo viên đặt (điền chỗ trống so khớp không phân biệt hoa thường và khoảng trắng thừa, chấp nhận nhiều
   đáp án đúng do giáo viên khai báo).
4. **Given** bài có câu tự luận, **When** học sinh nộp, **Then** điểm tổng hiện "chờ chấm" cho tới khi giáo viên chấm
   xong câu tự luận.
5. **Given** số lần làm tối đa là 1, **When** học sinh đã nộp và thử làm lại, **Then** hệ thống từ chối và hiện kết quả
   lần đã nộp.
6. **Given** bài đặt "ẩn đáp án tới khi đóng bài", **When** học sinh nộp trước giờ đóng, **Then** học sinh chỉ thấy
   điểm (nếu giáo viên cho phép), không thấy đáp án đúng; sau giờ đóng thì thấy.
7. **Given** giáo viên sửa đáp án đúng của một câu sau khi đã có bài nộp, **When** giáo viên xác nhận chấm lại, **Then**
   điểm của mọi bài nộp liên quan được tính lại và lịch sử ghi lại lần chấm lại.

---

### User Story 3 - Bài tập: giao, nộp, chấm và phản hồi (Priority: P2)

Giáo viên thêm bài tập vào buổi: đề bài (văn bản và tệp đính kèm), hạn nộp, điểm tối đa, có cho nộp muộn không. Học sinh
nộp bài bằng văn bản và/hoặc tệp, được nộp lại trước hạn (bản sau thay bản trước, giữ lịch sử). Giáo viên xem danh sách
bài nộp (đã nộp, nộp muộn, chưa nộp), chấm điểm, viết nhận xét và trả bài; học sinh nhận thông báo và thấy điểm, nhận xét.

**Why this priority**: Bài tập là vòng học tập cốt lõi của LMS nhưng có thể chạy sau quiz vì dựa trên chấm tay.

**Independent Test**: Giáo viên giao bài tập có hạn nộp; một học sinh nộp đúng hạn, một học sinh nộp muộn; giáo viên chấm
và trả bài; học sinh thấy điểm và nhận xét.

**Acceptance Scenarios**:

1. **Given** bài tập có hạn nộp và không cho nộp muộn, **When** quá hạn, **Then** học sinh không nộp được và thấy trạng
   thái "quá hạn".
2. **Given** bài tập cho nộp muộn, **When** học sinh nộp sau hạn, **Then** bài được nhận và đánh dấu "nộp muộn" cho giáo
   viên thấy.
3. **Given** học sinh đã nộp, **When** nộp lại trước hạn, **Then** giáo viên thấy bản mới nhất và xem được các bản trước.
4. **Given** giáo viên chấm điểm và nhận xét nhưng chưa trả bài, **When** học sinh mở bài tập, **Then** học sinh chưa
   thấy điểm; sau khi giáo viên bấm trả bài thì thấy.
5. **Given** giáo viên gia hạn riêng cho một học sinh, **When** học sinh đó nộp sau hạn chung nhưng trước hạn riêng,
   **Then** bài không bị đánh dấu nộp muộn.

---

### User Story 4 - Sổ điểm và tiến độ học của lớp (Priority: P2)

Giáo viên có tab sổ điểm: mỗi hàng một học sinh, mỗi cột một bài tập hoặc bài kiểm tra, kèm điểm trung bình và trạng
thái (chưa làm, chờ chấm, đã chấm). Giáo viên xem tỉ lệ học sinh đã xem từng buổi, tỉ lệ nộp bài, và tải sổ điểm về dạng
bảng tính. Học sinh có trang "Việc cần làm" liệt kê bài tập và bài kiểm tra sắp tới hạn của mọi lớp mình học, cùng trang
điểm của mình theo từng lớp.

**Why this priority**: Tổng hợp kết quả giúp giáo viên theo dõi lớp và học sinh không bỏ sót việc, nhưng chỉ có ý nghĩa
khi đã có bài tập và quiz.

**Independent Test**: Với lớp demo có 2 bài đã chấm, giáo viên mở sổ điểm thấy đúng điểm từng học sinh và tải được tệp;
học sinh thấy bài sắp tới hạn trong "Việc cần làm".

**Acceptance Scenarios**:

1. **Given** lớp có bài tập và quiz đã chấm, **When** giáo viên mở sổ điểm, **Then** mỗi ô hiện đúng điểm hoặc trạng
   thái, và điểm trung bình tính theo trọng số giáo viên đặt cho từng bài (mặc định bằng nhau).
2. **Given** học sinh học hai lớp, **When** mở "Việc cần làm", **Then** thấy các bài chưa nộp của cả hai lớp, sắp theo
   hạn gần nhất.
3. **Given** học sinh mở trang điểm, **When** có bài chưa trả, **Then** bài đó không hiện điểm.

---

### User Story 5 - Phụ huynh theo dõi việc học của con (Priority: P3)

Phụ huynh đã liên kết với con xem được danh sách buổi học, bài tập/bài kiểm tra của con (đã nộp, chưa nộp, quá hạn) và
điểm đã trả, ở chế độ chỉ xem. Phụ huynh không làm bài thay, không xem được bài nộp hay điểm của học sinh khác.

**Why this priority**: Hệ thống đã có vai trò phụ huynh; mở rộng sang kết quả học tập là bổ sung giá trị nhưng không
chặn các luồng chính.

**Independent Test**: Đăng nhập phụ huynh demo, thấy bài chưa nộp và điểm đã trả của con; không thấy dữ liệu của học
sinh khác cùng lớp.

**Acceptance Scenarios**:

1. **Given** phụ huynh liên kết với một học sinh, **When** mở trang của con, **Then** thấy việc cần làm và điểm đã trả
   của con.
2. **Given** phụ huynh cố mở bài nộp của học sinh khác qua đường dẫn, **When** gửi yêu cầu, **Then** hệ thống từ chối.

---

### User Story 6 - Agent tôn trọng buổi học và bài kiểm tra (Priority: P2)

Agent của lớp biết nội dung buổi học (tài liệu được bật "cho agent đọc") để giải thích bài cho học sinh. Trong lúc một
bài kiểm tra đang mở với một học sinh, agent của lớp không đưa đáp án hay lời giải trực tiếp cho câu hỏi của bài đó; với
bài tập, agent hướng dẫn gợi ý thay vì làm thay theo chính sách lớp hiện có.

Phía giáo viên, agent đóng vai trợ lý: (1) gợi ý câu hỏi quiz từ tài liệu của buổi học, giáo viên duyệt, sửa hoặc bỏ
từng câu trước khi đưa vào quiz; (2) gợi ý điểm và nhận xét cho câu tự luận và bài tập, giáo viên duyệt hoặc sửa trước
khi trả bài. Gợi ý của AI không bao giờ tới học sinh nếu giáo viên chưa duyệt.

**Why this priority**: Đây là chỗ LMS gặp lõi của dự án (agent, guard). Nếu thiếu, học sinh có thể dùng agent của lớp để
gian lận trong bài kiểm tra.

**Independent Test**: Học sinh đang làm bài kiểm tra, mở chat với agent lớp và dán nguyên văn một câu hỏi của bài;
agent từ chối đưa đáp án và lần chặn được ghi vào nhật ký lớp.

**Acceptance Scenarios**:

1. **Given** học sinh đang trong thời gian làm một bài kiểm tra, **When** hỏi agent lớp đáp án một câu của bài, **Then**
   agent từ chối đưa đáp án, giải thích ngắn gọn lý do, và hệ thống ghi một sự kiện vào nhật ký lớp.
2. **Given** bài kiểm tra đã đóng và đáp án đã công bố, **When** học sinh hỏi agent giải thích câu đó, **Then** agent
   giải thích bình thường.
3. **Given** tài liệu buổi học được bật "cho agent đọc", **When** học sinh hỏi về nội dung, **Then** câu trả lời dẫn
   nguồn tới tài liệu của buổi.
4. **Given** buổi học có tài liệu, **When** giáo viên yêu cầu gợi ý 5 câu trắc nghiệm từ tài liệu, **Then** hệ thống
   trả về các câu nháp kèm đáp án, lời giải thích và đoạn tài liệu làm căn cứ; không câu nào vào quiz cho tới khi giáo
   viên bấm duyệt từng câu hoặc duyệt hàng loạt.
5. **Given** một bài nộp tự luận, **When** giáo viên yêu cầu gợi ý chấm, **Then** hệ thống hiện điểm gợi ý và nhận xét
   gợi ý theo đáp án mẫu/thang chấm của giáo viên, đánh dấu rõ là "gợi ý của AI"; học sinh chỉ thấy điểm và nhận xét
   sau khi giáo viên duyệt và trả bài.
6. **Given** bài nộp chứa nội dung bị guard chặn hoặc tài liệu không đủ để sinh câu hỏi, **When** giáo viên yêu cầu gợi
   ý, **Then** hệ thống báo không tạo được gợi ý và lý do, không chặn việc giáo viên tự chấm hoặc tự soạn.

---

### Edge Cases

- Giáo viên xóa một buổi đã có bài nộp: hệ thống yêu cầu xác nhận, ẩn buổi khỏi học sinh nhưng giữ bài nộp và điểm trong
  sổ điểm (lưu trữ thay vì xóa cứng).
- Giáo viên sửa câu hỏi khi đã có học sinh đang làm bài: thay đổi chỉ áp dụng cho lượt làm bắt đầu sau đó; muốn áp dụng
  cho bài đã nộp thì dùng chức năng chấm lại.
- Học sinh mở bài kiểm tra trên hai tab hoặc hai thiết bị: chỉ có một lượt làm; câu trả lời được đồng bộ theo lần lưu
  sau cùng, đồng hồ không bị đặt lại.
- Hết giờ làm bài đúng lúc học sinh đang nộp: bài được nhận với các câu đã lưu tới thời điểm hết giờ.
- Học sinh tham gia lớp sau khi bài đã giao: thấy bài nếu bài còn mở; bài đã đóng thì hiện "không được giao" và không tính
  vào điểm trung bình trừ khi giáo viên giao lại.
- Học sinh rời lớp: bài nộp và điểm được giữ cho giáo viên, học sinh không còn truy cập lớp.
- Tệp tải lên vượt giới hạn dung lượng hoặc sai định dạng: từ chối với thông báo nêu rõ giới hạn.
- Link video không phát được (bị xóa, chặn nhúng): hiện thông báo và nút mở link ở tab mới.
- Học sinh chưa có đồng ý của phụ huynh (lớp bật yêu cầu đồng ý): vẫn xem buổi học và làm bài, nhưng không chat được
  với agent như quy tắc hiện có.
- Lớp đã lưu trữ: mọi nội dung chỉ còn chế độ chỉ xem; không giao bài mới, không nộp bài.
- Quiz không có câu hỏi nào: không cho công bố.

## Requirements *(mandatory)*

### Functional Requirements

**Buổi học và nội dung**

- **FR-001**: Giáo viên chủ lớp (và giáo viên đồng dạy của lớp) MUST tạo, sửa, sắp xếp lại, lưu trữ buổi học trong lớp;
  mỗi buổi có tiêu đề, mô tả, ngày học (tùy chọn), thứ tự và trạng thái nháp/đã công bố.
- **FR-002**: Giáo viên MUST đặt được thời điểm tự mở buổi; trước thời điểm đó học sinh chỉ thấy tiêu đề và trạng thái
  "sắp mở".
- **FR-003**: Một buổi học MUST chứa được các loại mục: tài liệu (tệp), video (tệp tải lên hoặc link video), liên kết
  ngoài, đoạn văn bản, bài tập, quiz/bài kiểm tra; giáo viên sắp xếp được thứ tự các mục.
- **FR-004**: Học sinh MUST xem được tài liệu thông dụng (PDF, ảnh, văn bản) và phát được video ngay trong trang buổi
  học; định dạng không xem trực tiếp được thì cho tải về.
- **FR-005**: Hệ thống MUST giới hạn dung lượng và định dạng tệp tải lên và báo rõ giới hạn khi từ chối.
- **FR-006**: Tài liệu của buổi MUST có tùy chọn "cho agent đọc"; khi bật, tài liệu được đưa vào kho tri thức của lớp
  theo cơ chế tab Tài liệu hiện có, và tắt thì rút khỏi kho.
- **FR-007**: Hệ thống MUST ghi nhận học sinh đã mở từng mục nội dung (đã xem/chưa xem) để giáo viên theo dõi.

**Quiz và bài kiểm tra**

- **FR-008**: Giáo viên MUST tạo được quiz/bài kiểm tra với các loại câu: trắc nghiệm một đáp án, nhiều đáp án, đúng/sai,
  điền chỗ trống (một hoặc nhiều đáp án chấp nhận), tự luận; mỗi câu có điểm, câu khách quan có lời giải thích tùy chọn.
- **FR-009**: Giáo viên MUST cấu hình: thời gian mở, thời gian đóng, thời lượng làm bài (tùy chọn), số lần làm tối đa,
  cách tính điểm khi nhiều lần làm (cao nhất, lần cuối, trung bình), trộn thứ tự câu hỏi, trộn đáp án, thời điểm cho
  xem điểm và đáp án (ngay khi nộp, sau khi đóng bài, không bao giờ).
- **FR-010**: Câu nhiều đáp án MUST được chấm theo quy tắc giáo viên chọn: đúng hết mới có điểm, hoặc điểm theo tỉ lệ
  (đúng cộng, sai trừ, không âm).
- **FR-011**: Hệ thống MUST lưu câu trả lời của học sinh trong lúc làm bài để không mất khi tải lại trang hoặc mất kết
  nối, và MUST tính thời lượng theo thời điểm bắt đầu phía hệ thống, không theo đồng hồ của trình duyệt.
- **FR-012**: Hệ thống MUST tự nộp bài khi hết thời lượng hoặc tới giờ đóng, và MUST từ chối câu trả lời gửi sau thời
  điểm đó.
- **FR-013**: Câu khách quan MUST được chấm tự động khi nộp; câu tự luận MUST vào hàng chờ chấm của giáo viên; điểm tổng
  chỉ là điểm cuối khi mọi câu đã chấm.
- **FR-014**: Đáp án đúng và lời giải MUST không bao giờ được gửi tới thiết bị học sinh trước thời điểm giáo viên cho
  phép xem.
- **FR-015**: Giáo viên MUST chấm lại được một câu cho mọi bài đã nộp sau khi sửa đáp án; lần chấm lại được ghi lịch sử.
- **FR-016**: Giáo viên MUST xem được thống kê của mỗi quiz: số học sinh đã làm, điểm trung bình, phân bố điểm, tỉ lệ
  đúng từng câu.
- **FR-017**: Giáo viên MUST dùng lại được câu hỏi: sao chép một quiz sang buổi khác hoặc lớp khác của mình.

**Bài tập**

- **FR-018**: Giáo viên MUST tạo bài tập với đề bài (văn bản, tệp đính kèm), hạn nộp, điểm tối đa, cho/không cho nộp muộn.
- **FR-019**: Học sinh MUST nộp bài bằng văn bản và/hoặc tệp, nộp lại được trước hạn; mọi bản nộp được lưu, bản mới nhất
  là bản được chấm.
- **FR-020**: Bài nộp sau hạn MUST được đánh dấu "nộp muộn"; bài không cho nộp muộn MUST bị từ chối sau hạn.
- **FR-021**: Giáo viên MUST gia hạn riêng được cho từng học sinh.
- **FR-022**: Giáo viên MUST chấm điểm, viết nhận xét và trả bài theo từng bài hoặc trả hàng loạt; học sinh chỉ thấy điểm
  và nhận xét sau khi bài được trả.

**Sổ điểm, việc cần làm, thông báo**

- **FR-023**: Hệ thống MUST cung cấp sổ điểm theo lớp (học sinh × bài tập/bài kiểm tra) với trạng thái từng ô, trọng số
  từng bài do giáo viên đặt, và điểm trung bình; giáo viên MUST tải được sổ điểm dạng bảng tính.
- **FR-024**: Học sinh MUST có trang "Việc cần làm" gom bài tập và bài kiểm tra chưa hoàn thành của mọi lớp, sắp theo hạn.
- **FR-025**: Hệ thống MUST thông báo trong ứng dụng cho học sinh khi buổi học được công bố, bài được giao, bài sắp tới
  hạn (24 giờ trước), bài được trả điểm; và cho giáo viên khi có bài nộp chờ chấm.
- **FR-026**: Phụ huynh đã liên kết MUST xem được (chỉ xem) buổi học, việc cần làm, trạng thái nộp và điểm đã trả của
  con mình.

**Quyền và an toàn**

- **FR-027**: Chỉ thành viên của lớp (giáo viên, học sinh) và phụ huynh đã liên kết của học sinh trong lớp MUST truy cập
  được nội dung lớp; học sinh MUST chỉ thấy bài nộp và điểm của chính mình; phụ huynh MUST chỉ thấy dữ liệu của con mình.
- **FR-028**: Trong lúc một học sinh đang có lượt làm bài kiểm tra mở, agent của lớp MUST không đưa đáp án hoặc lời giải
  trực tiếp cho câu hỏi của bài đó, và mỗi lần chặn MUST được ghi vào nhật ký lớp hiện có. Giáo viên MUST tắt được hành
  vi này cho từng quiz (ví dụ quiz luyện tập cho phép hỏi agent).
- **FR-029**: Nội dung văn bản do người dùng nhập (đề bài, câu hỏi, bài nộp, nhận xét) MUST đi qua guard nội dung hiện
  có giống như tin nhắn chat.
- **FR-030**: Mọi thao tác ảnh hưởng tới điểm (chấm, chấm lại, sửa điểm, gia hạn, xóa bài nộp) MUST được ghi nhật ký với
  người thực hiện và thời điểm.
**Trợ lý AI cho giáo viên**

- **FR-031**: Giáo viên MUST yêu cầu được agent gợi ý câu hỏi quiz (chọn loại câu, số câu, độ khó) từ các tài liệu của
  buổi học; mỗi câu gợi ý MUST kèm đáp án, lời giải thích và trích dẫn đoạn tài liệu làm căn cứ.
- **FR-032**: Câu hỏi do AI gợi ý MUST ở trạng thái nháp cho tới khi giáo viên duyệt; giáo viên MUST sửa, duyệt hoặc bỏ
  được từng câu, và câu đã duyệt mang dấu "nguồn: AI gợi ý, giáo viên duyệt".
- **FR-033**: Giáo viên MUST yêu cầu được gợi ý điểm và nhận xét cho câu tự luận và bài tập, dựa trên đáp án mẫu hoặc
  thang chấm (rubric) giáo viên nhập; gợi ý MUST nêu lý do theo từng tiêu chí của thang chấm.
- **FR-034**: Điểm và nhận xét gợi ý MUST không hiện với học sinh và phụ huynh, và MUST không tính vào sổ điểm, cho tới
  khi giáo viên duyệt (giữ nguyên hoặc sửa) và trả bài. Hệ thống MUST lưu cả điểm gợi ý lẫn điểm giáo viên chốt để đo độ
  lệch.
- **FR-035**: Nội dung gửi cho AI khi gợi ý (tài liệu, bài nộp) MUST đi qua guard hiện có, chỉ dùng dữ liệu của chính
  lớp đó, và mỗi lần gợi ý MUST được ghi nhật ký (ai yêu cầu, cho bài nào, kết quả duyệt).
- **FR-036**: Giáo viên MUST tắt được trợ lý AI chấm bài cho từng bài tập/quiz.

### Key Entities *(include if feature involves data)*

- **Buổi học (Lesson)**: thuộc một lớp; tiêu đề, mô tả, ngày học, thứ tự, trạng thái (nháp/công bố/lưu trữ), thời điểm
  tự mở.
- **Mục nội dung (Lesson item)**: thuộc một buổi; loại (tài liệu, video, link, văn bản, bài tập, quiz), thứ tự, trạng
  thái hiển thị; mục tài liệu có cờ "cho agent đọc" liên kết tới tài liệu trong kho tri thức.
- **Tệp đính kèm (Attachment)**: tệp người dùng tải lên cho mục nội dung, đề bài hoặc bài nộp; tên, định dạng, dung lượng,
  người tải.
- **Quiz/Bài kiểm tra (Quiz)**: là một mục nội dung; cấu hình thời gian, số lần làm, cách tính điểm, trộn, chế độ xem
  đáp án, chế độ chặn agent.
- **Câu hỏi (Question)**: thuộc quiz; loại, nội dung, các lựa chọn, đáp án đúng, điểm, lời giải thích, thứ tự.
- **Lượt làm bài (Quiz attempt)**: một học sinh × một quiz × lần thứ n; thời điểm bắt đầu, hạn kết thúc, thời điểm nộp,
  các câu trả lời, điểm từng câu, trạng thái (đang làm, đã nộp, chờ chấm, đã chấm).
- **Bài tập (Assignment)**: là một mục nội dung; đề bài, hạn nộp, điểm tối đa, cho nộp muộn, gia hạn riêng theo học sinh.
- **Bài nộp (Submission)**: một học sinh × một bài tập; các phiên bản nộp (văn bản, tệp, thời điểm), cờ nộp muộn, điểm,
  nhận xét, trạng thái trả bài.
- **Mục sổ điểm (Grade item)**: bài tập hoặc quiz được tính điểm trong lớp, có trọng số; điểm của học sinh suy ra từ lượt
  làm hoặc bài nộp.
- **Lượt xem nội dung (Content view)**: học sinh đã mở mục nội dung nào, lúc nào.
- **Gợi ý AI (AI suggestion)**: loại (câu hỏi quiz hoặc chấm bài), đối tượng (buổi học, bài nộp, lượt làm), nội dung gợi
  ý, căn cứ (đoạn tài liệu, tiêu chí thang chấm), trạng thái (chờ duyệt, đã duyệt, đã sửa, đã bỏ), người duyệt.
- **Thang chấm (Rubric)**: thuộc câu tự luận hoặc bài tập; các tiêu chí, mức điểm, đáp án mẫu.
- **Thông báo (Notification)**: người nhận, loại sự kiện, liên kết tới buổi/bài, đã đọc/chưa đọc.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Giáo viên tạo được một buổi học có 1 tài liệu, 1 video và 1 quiz 5 câu rồi công bố trong dưới 10 phút ở lần
  dùng đầu.
- **SC-002**: Học sinh mở buổi học và bắt đầu xem tài liệu hoặc video trong không quá 3 thao tác từ trang lớp.
- **SC-003**: 100% câu khách quan được chấm và hiện điểm cho học sinh trong vòng 2 giây sau khi nộp (khi cấu hình cho xem
  điểm ngay).
- **SC-004**: Không mất câu trả lời nào đã chọn khi học sinh tải lại trang hoặc mất kết nối trong lúc làm bài (kiểm thử
  với 20 lần ngắt giữa chừng).
- **SC-005**: 0 trường hợp học sinh nhận được đáp án đúng trước thời điểm cho phép, kiểm tra trên mọi loại câu hỏi và mọi
  chế độ xem đáp án.
- **SC-006**: Trên bộ thử gian lận (ít nhất 30 câu hỏi dán nguyên văn hoặc diễn đạt lại từ bài kiểm tra đang mở), agent
  của lớp từ chối đưa đáp án ở ít nhất 95% trường hợp, và 100% lần chặn có trong nhật ký lớp.
- **SC-007**: Sổ điểm của lớp 40 học sinh × 20 bài hiển thị đầy đủ trong dưới 3 giây và khớp 100% với điểm từng bài.
- **SC-008**: 0 trường hợp học sinh hoặc phụ huynh xem được bài nộp hoặc điểm của học sinh khác (kiểm thử truy cập trực
  tiếp bằng đường dẫn với mọi vai trò).
- **SC-009**: Ít nhất 80% câu hỏi AI gợi ý được giáo viên duyệt mà không phải sửa đáp án (đo trên tập tài liệu demo).
- **SC-010**: Trên bộ thử ít nhất 30 bài tự luận đã có điểm giáo viên chấm, điểm AI gợi ý lệch không quá 1 điểm (thang 10)
  ở ít nhất 80% bài.
- **SC-011**: 0 trường hợp điểm hoặc nhận xét do AI gợi ý tới được học sinh hay phụ huynh khi chưa được giáo viên duyệt.

## Assumptions

- "Lớp" hiện có đóng vai trò khóa học; không thêm tầng khóa học/chương riêng ở phiên bản này. Buổi học sắp xếp phẳng
  theo thứ tự trong lớp.
- Giáo viên đồng dạy (thành viên lớp có vai trò giáo viên) có quyền như chủ lớp với nội dung học tập; admin có quyền xem.
- Video hỗ trợ cả tệp tải lên (giới hạn dung lượng, mặc định 200 MB mỗi tệp) và link từ nền tảng video phổ biến; không
  chuyển mã video. Tài liệu khác mặc định giới hạn 25 MB mỗi tệp. Tệp lưu trên máy chạy hệ thống (chạy local, dữ liệu
  demo), không dùng dịch vụ lưu trữ ngoài.
- Thông báo chỉ trong ứng dụng; không gửi email, SMS hay thông báo đẩy.
- Không có lớp học trực tuyến trực tiếp (gọi video), điểm danh, diễn đàn thảo luận theo buổi, ngân hàng câu hỏi dùng
  chung toàn hệ thống, chứng chỉ hoàn thành khóa, hay chống gian lận bằng giám sát trình duyệt/camera. Phạm vi chống gian
  lận là chặn agent của lớp đưa đáp án (FR-028).
- Thang điểm mặc định 10, giáo viên đổi được điểm tối đa từng bài.
- Tab "Tài liệu" hiện có vẫn giữ vai trò kho tri thức cho agent; tài liệu gắn vào buổi học dùng chung kho đó khi bật
  "cho agent đọc" thay vì tạo kho mới.
- Có seed dữ liệu demo (ít nhất một lớp có buổi học, quiz, bài tập, bài nộp mẫu) để demo được ngay, và `dev.ps1` được
  cập nhật nếu feature thêm bước chạy (ví dụ thư mục lưu tệp, migration) theo nguyên tắc III của constitution.
