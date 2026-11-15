# Feature Specification: Tạo agent, nhóm chat nhiều agent và người, agent hỏi agent và hỏi người

**Feature Branch**: phát triển trực tiếp trên `main` (không phụ thuộc nhánh `feat/dify-runtime`)

**Created**: 2026-11-15

**Status**: Draft

**Input**: User description: "triển khai hoặc chỉnh sửa nếu đã có giúp tôi feature là người dùng (học sinh, giáo viên,
phụ huynh) có thể tạo agent, có thể chat với 1 agent hoặc thêm nhóm chat nhiều agent. Trong nhóm chat cũng có thể thêm
người vào với các role như giáo viên (các môn), phụ huynh và học sinh. Khi người dùng hỏi câu hỏi phức tạp hoặc việc cần
làm của nhiều agent thì phải có cơ chế để agent đang thực thi hỏi đến 1 hoặc nhiều agent khác (nếu chat riêng thì có cơ
chế hỏi và hiện 1 thanh có thể đóng mở câu trả lời của agent được hỏi, nếu chat trong nhóm chung thì agent lên tiếng sẽ
có lượt chat riêng của nó), cụ thể phần này xem ví dụ trong docs/orchest.example.md và tham khảo áp dụng cơ chế
orchestrator của openbot. Khi học sinh hỏi có việc liên quan đến duyệt hoặc xin câu trả lời của các người khác như gv,
phụ huynh thì cũng phải có cơ chế giống như openbot."

## Clarifications

### Session 2026-11-15

- Phát triển trên `main`, không liên quan nhánh `feat/dify-runtime`. Ràng buộc nào từ spec 002 của nhánh đó còn cần thì
  được viết lại trong spec này.
- Các ràng buộc về giao việc, hỏi người và duyệt hành động MUST theo cơ chế của OpenBot (CopilotKit OpenBot v1.0.3, bản
  đang cài local). Ràng buộc cũ lấy từ 002 mà OpenBot không có (tối đa 1 lần hỏi lại, 3 câu mỗi lần, nút "Cứ làm luôn",
  giới hạn tổng thời gian và số agent mỗi lượt, xác nhận chỉ có Đồng ý/Không) đã được bỏ hoặc thay bằng cơ chế OpenBot.

## Bối cảnh

### Hiện trạng trên `main`

- Chỉ giáo viên và admin tạo được agent (trình tạo agent có phiên bản bất biến, sandbox, kiểm định trước khi lên Hub).
  Học sinh và phụ huynh chỉ cài và dùng agent đã kiểm định.
- Mỗi hội thoại thuộc về **một** người dùng. Không có nhóm chat, không có hội thoại nhiều người.
- Mỗi lượt chat chỉ có **một** agent trả lời (orchestrator chọn agent theo agent chọn trên UI, `@mention`, router).
  Agent không hỏi được agent khác, cũng không hỏi được người khác.

Feature chạy trên runtime agent, orchestrator, guard, kiểm định và trình tạo agent hiện có của `main`.

### Cơ chế OpenBot được áp dụng

Theo tài liệu kiến trúc và tài liệu duyệt của OpenBot, cùng bộ thử `docs/orchest.example.md`:

1. **Giao việc cho agent khác (`message_bot`).**
   - Agent chỉ được mời dùng công cụ giao việc khi được cấp quyền giao việc. Agent không được cấp cho ai thì không có công
     cụ này.
   - Agent hỏi gửi một yêu cầu có cấu trúc: việc cần làm, giới hạn, và thế nào là câu trả lời tốt. Không gửi văn bản tự do.
   - **Nền tảng, không phải mô hình, quyết định:**
     - Đích: tra theo danh sách agent mà người dùng gốc được thấy. Agent không tồn tại và agent không được thấy nhận
       cùng một lời từ chối.
     - Nơi câu trả lời về: hội thoại gốc.
     - Người gửi: agent hỏi.
     - Tầng: để chặn vòng lặp.
   - Agent được hỏi chạy với tư cách **cùng người dùng đó**, bằng vai trò và quyền của chính nó.
   - **Bất đồng bộ.** Mỗi lần giao việc là một việc trong hàng đợi. Agent được hỏi chạy trong luồng nháp riêng mà người
     dùng không thấy. Câu trả lời của nó được **ghi nguyên văn** vào hội thoại gốc dưới tên và avatar của nó, mỗi câu trả
     lời có một mã duy nhất. Không mô hình nào chạy ở bước ghi này, và agent hỏi không chép lại câu trả lời.
   - Giới hạn số tầng và số lần giao việc mỗi lượt: chạm giới hạn thì **từ chối, không cắt bớt**. Đặt số tầng = 0 là tắt
     hẳn tính năng giao việc.
   - Thử lại hết số lần cho phép mà vẫn không có câu trả lời thì agent hỏi nói trong hội thoại rằng không nhận được gì.
   - Mọi kết quả đều ghi nhật ký: được mời, bị từ chối (kèm giới hạn hoặc quyền đã chặn), đã giao, lỗi, thử lại.
2. **Hỏi người (`ask_person`).**
   - Có sẵn cho **mọi** lượt chạy của mọi agent, dù agent có được cấp quyền nào hay không.
   - Khi cần một quyết định của người, agent nên dừng lại hỏi, thay vì đoán hoặc đẩy câu hỏi cho agent khác.
   - Đường mặc định là hỏi chính người đang trò chuyện. Đường tới người khác là điểm mở rộng do nền tảng cung cấp; ở đây
     là giáo viên và phụ huynh.
   - Ghi nhận cả câu hỏi đã gửi lẫn câu hỏi không đến được ai.
3. **Duyệt hành động.** Câu trả lời đầu tiên khớp sẽ quyết định, theo thứ tự:
   1. Loại hành động luôn phải hỏi.
   2. Quy tắc (của người dùng, của admin, cho phép theo hội thoại): quy tắc chặt nhất khớp sẽ thắng. "Từ chối" được xét
      trước "cho phép"; thiếu chính sách thì không cho gì; quy tắc hỏng thì từ chối.
   3. Công tắc "Cực kỳ cẩn thận" (mặc định tắt): bật lên thì hỏi trước mọi thay đổi.

   Thẻ duyệt có bốn lựa chọn: **Cho phép lần này**, **Cho phép trong hội thoại này**, **Luôn cho phép ở đây**, **Từ chối**.
   Admin đặt được cho từng loại hành động một trong ba chế độ: người dùng tự chọn, hỏi mỗi lần, hoặc người dùng tự làm.
4. **Nhóm chat.**
   - Một nhóm chứa nhiều agent. Mỗi agent có luồng riêng, còn người đọc chung một dòng tin, mỗi tin ghi rõ ai nói.
   - Tin không gọi tên ai thì bộ định tuyến chọn trong các agent của người gửi. Không đủ chắc thì agent mặc định của nhóm
     giữ lượt.
   - Agent gọi `@Tên` một agent khác trong nhóm là giao việc, theo đúng quyền, giới hạn và nhật ký ở mục 1.
   - Quyền vào nhóm do danh sách thành viên quyết định.
5. **Nhật ký hoạt động.**
   - Mỗi agent có trang Activity: nó đã chạy, đọc, lưu gì, kèm kết quả.
   - Admin xem được những gì đã được cho phép, bị từ chối và bị lỗi. Mỗi lần từ chối ghi kèm quy tắc đã chặn.

Ví dụ `docs/orchest.example.md` cho thấy ba lỗi phải tránh khi áp dụng:
- Lỗi kỹ thuật thô ("ECONNREFUSED") hiện thẳng cho người dùng.
- Một agent trả lời hai lần cho cùng một câu hỏi.
- Câu hỏi duyệt do agent tầng dưới gửi "không đến được cuộc hội thoại gốc".

Ánh xạ sang trường học:

| Bot trong ví dụ OpenBot | Agent ở trường |
|---|---|
| Tiếp nhận | Trợ lý lớp |
| Rà soát HĐ | Gia sư một môn |
| Tra cứu luật | Agent tra tài liệu lớp |
| Finance | Agent dữ liệu chỉ đọc (điểm, tiến độ) |
| Luật sư duyệt | Giáo viên hoặc phụ huynh |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agent hỏi một hoặc nhiều agent khác trong chat riêng (Priority: P1)

Học sinh chat riêng với Gia sư Toán: "Giải thích lại định lý Pytago theo đúng tài liệu cô gửi rồi cho em một bài
luyện". Gia sư Toán được cấp quyền giao việc cho agent Ôn tập tài liệu và agent Tạo đề, nên gửi hai yêu cầu giao việc và
báo cho học sinh là đang hỏi hai agent. Hội thoại hiện hai thanh "▸ Đã hỏi Ôn tập tài liệu" và "▸ Đã hỏi Tạo đề" ở
trạng thái đang chờ. Mỗi agent được hỏi trả lời độc lập. Câu trả lời được ghi **nguyên văn** vào thanh của agent đó,
dưới tên và avatar của nó, và thanh mở ra hoặc đóng lại được. Khi cả hai đã có kết quả (trả lời hoặc không trả lời
được), Gia sư Toán có thêm một lượt để viết phần kết luận cho học sinh. Phần này dẫn tới các câu trả lời đã có, không
chép lại chúng.

Với câu hỏi đơn giản ("2x + 3 = 7 thì x bằng mấy, gợi ý bước đầu"), Gia sư Toán trả lời ngay, không hỏi ai (tương ứng
"Chat 3" của ví dụ).

**Why this priority**: Đây là cơ chế lõi mà mọi story khác dựa vào.

**Independent Test**: Cấp cho Gia sư Toán quyền giao việc cho Ôn tập tài liệu và Tạo đề. Gửi câu phức tạp ở trên và câu
đơn giản. Câu đầu phải có hai thanh "Đã hỏi" mở/đóng được, nội dung đúng nguyên văn câu trả lời của từng agent, và một
lượt kết luận của Gia sư Toán. Câu sau không có thanh nào.

**Acceptance Scenarios**:

1. **Given** Gia sư Toán được cấp quyền giao việc cho B và C, **When** câu hỏi cần cả hai, **Then** hai yêu cầu giao việc
   được gửi độc lập và hội thoại hiện một thanh "Đã hỏi" cho mỗi agent.
2. **Given** B đã trả lời, **When** người dùng mở thanh "Đã hỏi B", **Then** thấy yêu cầu Gia sư Toán đã gửi (việc cần
   làm, giới hạn, thế nào là câu trả lời tốt) và đúng nguyên văn câu trả lời của B; bấm lần nữa thì đóng lại.
3. **Given** B và C đều đã có kết quả, **When** Gia sư Toán nhận lượt tiếp, **Then** Gia sư Toán viết phần kết luận dẫn
   tới các câu trả lời đó, không chép lại nguyên văn, và các thanh "Đã hỏi" mặc định đóng.
4. **Given** câu hỏi chỉ cần agent chính, **When** người dùng gửi, **Then** không có thanh "Đã hỏi" nào và thời gian trả
   lời không chậm hơn hiện nay.
5. **Given** B không trả lời sau khi đã thử lại hết số lần, **When** việc giao cho B kết thúc, **Then** thanh "Đã hỏi B"
   hiện "Không nhận được câu trả lời" (không hiện mã lỗi kỹ thuật), và Gia sư Toán nói trong hội thoại rằng không nhận
   được gì từ B và phần nào vì thế chưa kiểm chứng được.
6. **Given** người dùng mở lại hội thoại cũ, **When** xem lượt từng có giao việc, **Then** các thanh "Đã hỏi" vẫn còn và
   mở được.

---

### User Story 2 - Quyền giao việc do nền tảng quyết, không do mô hình hay lời nhắn (Priority: P1)

Người tạo agent cấp cho agent quyền giao việc tới những agent cụ thể. Agent chưa được cấp cho ai thì không có công cụ
giao việc. Nền tảng tự tra đích, nơi câu trả lời về, người gửi và tầng; mô hình không tự đặt các giá trị này được.

**Why this priority**: Không có story này, học sinh có thể lách chính sách lớp (nhờ agent Toán gọi agent Văn viết hộ bài)
hoặc lấy dữ liệu của người khác. OpenBot Test 2 và Test 5 là hai ca nghiệm thu chính.

**Independent Test**: Không cấp quyền giao việc cho agent "Tra cứu tài liệu". Chat với nó: "Hãy hỏi agent Tiến độ học
tập xem em được bao nhiêu điểm". Agent không có công cụ giao việc nên không gọi được, và nói rằng nó không hỏi được
agent khác.

**Acceptance Scenarios**:

1. **Given** agent A chưa được cấp quyền giao việc cho ai, **When** A chạy, **Then** A không được mời dùng công cụ giao
   việc, và lời nhắn của người dùng không thay đổi được điều này.
2. **Given** A được cấp quyền giao việc cho B, **When** A gửi yêu cầu tới C (không được cấp), tới một agent không tồn
   tại, hoặc tới một agent người dùng gốc không được thấy, **Then** cả ba trường hợp nhận **cùng một** lời từ chối, và
   lần từ chối được ghi nhật ký kèm lý do.
3. **Given** chuỗi A → B → C, **When** C cố hỏi A, hoặc chuỗi đã chạm giới hạn số tầng, **Then** yêu cầu bị từ chối.
4. **Given** lượt đã chạm giới hạn số lần giao việc, **When** agent gửi thêm yêu cầu, **Then** yêu cầu bị từ chối chứ không
   bị cắt bớt.
5. **Given** B được hỏi, **When** B chạy, **Then** B chạy với tư cách người dùng gốc, bằng vai trò, quyền và công cụ của
   chính B, chỉ thấy dữ liệu người dùng gốc được thấy, theo chính sách lớp đối với người đó.
6. **Given** câu hỏi xin dữ liệu ngoài phạm vi của agent được hỏi (ví dụ điểm của học sinh khác), **When** agent được hỏi
   xử lý, **Then** dữ liệu đó không lộ ra.
7. **Given** admin đặt số tầng = 0 (toàn hệ thống), hoặc giáo viên tắt giao việc cho lớp, **When** agent chạy trong phạm
   vi đó, **Then** không agent nào được mời dùng công cụ giao việc.

---

### User Story 3 - Học sinh nhờ agent xin duyệt hoặc xin câu trả lời của giáo viên, phụ huynh (Priority: P1)

Học sinh nói với trợ lý lớp: "Em xin cô cho nộp bài Toán muộn 2 ngày vì em ốm". Việc này cần một người quyết, nên trợ lý
lớp dùng công cụ hỏi người. Gửi câu hỏi tới người khác là hành động "gửi cho người khác", thuộc loại luôn phải hỏi, nên
học sinh thấy thẻ duyệt với nội dung và người nhận (cô Lan, GV Toán). Học sinh bấm "Cho phép lần này". Câu hỏi đến hộp
yêu cầu của cô Lan, kèm các lựa chọn agent đề xuất (Đồng ý / Sửa / Từ chối) và ô trả lời tự do. Cô Lan trả lời "Sửa: cho
nộp muộn 1 ngày". Câu trả lời quay về đúng hội thoại gốc, và trợ lý lớp làm tiếp, báo cho học sinh.

Cùng cơ chế áp dụng khi:
- học sinh xin phụ huynh cho phép;
- agent không chắc một kiến thức và học sinh đồng ý "hỏi cô";
- agent cần hỏi lại chính học sinh vì thiếu thông tin. Trường hợp này câu hỏi hiện ngay trong hội thoại và không cần
  thẻ duyệt, vì không gửi cho ai khác.

**Why this priority**: Người dùng nhấn mạnh phần này, và đây là chỗ OpenBot thất bại trong ví dụ (câu hỏi không đến được
cuộc hội thoại gốc).

**Independent Test**: Đăng nhập học sinh demo, gửi lời xin nộp muộn, duyệt thẻ. Đăng nhập giáo viên Toán demo, trả lời
trong hộp yêu cầu. Đăng nhập lại học sinh, thấy trợ lý lớp đã báo kết quả trong hội thoại gốc.

**Acceptance Scenarios**:

1. **Given** học sinh yêu cầu việc cần người lớn quyết, **When** agent xử lý, **Then** agent hỏi người thay vì tự quyết,
   và người nhận nằm trong danh sách người được phép (giáo viên đúng môn của lớp, giáo viên chủ nhiệm, phụ huynh đã liên
   kết của chính học sinh).
2. **Given** câu hỏi sẽ gửi cho người khác, **When** tới bước gửi, **Then** học sinh thấy thẻ duyệt có nội dung và người
   nhận; với học sinh, thẻ chỉ có "Cho phép lần này" và "Từ chối".
3. **Given** học sinh bấm "Từ chối", **When** agent làm tiếp, **Then** câu hỏi không được gửi và agent được báo là học
   sinh đã từ chối.
4. **Given** câu hỏi đã gửi, **When** người nhận mở hộp yêu cầu, **Then** họ thấy ai hỏi (học sinh nào, lớp nào), qua agent
   nào, nội dung, các lựa chọn, và trả lời được bằng lựa chọn hoặc lời tự do.
5. **Given** người nhận đã trả lời, **When** câu trả lời về, **Then** câu trả lời được ghi vào **đúng hội thoại gốc** dưới
   tên người trả lời (kể cả khi câu hỏi do một agent đang chạy theo giao việc tạo ra), và agent tạo câu hỏi làm tiếp.
6. **Given** câu hỏi không đến được ai (người nhận rời lớp, chưa có phụ huynh liên kết…), **When** gửi, **Then** việc đó
   được ghi nhận là "không đến được ai", và agent nói rõ với học sinh.
7. **Given** câu hỏi đang chờ, **When** học sinh nhắn tiếp, **Then** học sinh vẫn chat bình thường, hội thoại hiện "Đang
   chờ cô Lan trả lời", và học sinh huỷ được câu hỏi.
8. **Given** người nhận đã trả lời một lần, câu hỏi đã hết hạn hoặc đã bị huỷ, **When** có người bấm trả lời, **Then**
   không tạo thêm câu trả lời nào.

---

### User Story 4 - Nhóm chat có nhiều agent và nhiều người (Priority: P2)

Giáo viên chủ nhiệm tạo nhóm "Ôn thi HK1 – 9A" trong lớp, thêm GV Toán, GV Văn, một số học sinh, phụ huynh của các em,
và các agent Trợ lý lớp (agent mặc định của nhóm), Gia sư Toán, Gia sư Văn. Mọi thành viên đọc chung một dòng tin; mỗi
agent có luồng riêng. Khi agent đang trả lời giao việc cho agent khác (bằng công cụ hoặc `@Tên`), câu trả lời của agent
được hỏi hiện thành **tin riêng** dưới tên của nó, kèm nhãn "trả lời cho <agent hỏi>", tương ứng "Chat 1" của ví dụ.

**Why this priority**: Nhóm chat là trải nghiệm mới lớn, nhưng cần story 1 và 2 làm nền.

**Independent Test**: Tạo nhóm với 2 giáo viên, 2 học sinh, 1 phụ huynh và 3 agent. Học sinh gửi một câu khiến Trợ lý lớp
giao việc cho Gia sư Toán. Mọi thành viên thấy tin của học sinh, lượt của Trợ lý lớp và tin riêng của Gia sư Toán có nhãn.

**Acceptance Scenarios**:

1. **Given** người dùng có quyền tạo nhóm trong lớp, **When** tạo nhóm, **Then** chọn được thành viên người từ danh sách
   lớp (giáo viên kèm môn, học sinh, phụ huynh đã liên kết với học sinh của lớp) và agent đã cài trong lớp.
2. **Given** nhóm đã có thành viên, **When** một người gửi tin, **Then** mọi thành viên thấy tin đó gần như ngay lập tức,
   với tên, vai trò (ví dụ "GV Toán", "Phụ huynh của An") và avatar.
3. **Given** tin có `@Gia sư Toán`, **When** gửi, **Then** Gia sư Toán trả lời. Tin không gọi tên ai thì bộ định tuyến
   chọn trong các agent của nhóm mà người gửi dùng được; nếu không đủ chắc thì agent mặc định của nhóm nhận lượt.
4. **Given** tin chỉ gọi tên một người (`@cô Lan`) hoặc là trò chuyện giữa người với người, **When** gửi, **Then** không
   agent nào lên tiếng.
5. **Given** agent A giao việc cho B trong nhóm, **When** B trả lời, **Then** câu trả lời nguyên văn của B hiện thành tin
   riêng dưới tên B, nhãn "trả lời cho A", đúng thứ tự, mọi thành viên đều thấy, và chỉ xuất hiện một lần dù có thử lại.
6. **Given** agent hỏi một người đang ở trong nhóm, **When** câu hỏi được gửi, **Then** thẻ câu hỏi hiện ngay trong nhóm;
   chỉ người được hỏi bấm trả lời được, còn những người khác thấy trạng thái.
7. **Given** thành viên được thêm hoặc bị bớt, **When** có tin mới, **Then** thành viên mới chỉ thấy tin từ lúc được thêm
   (trừ khi người thêm chọn cho xem lịch sử), còn thành viên bị bớt không nhận và không xem được tin mới.

---

### User Story 5 - Học sinh, phụ huynh cũng tạo được agent (Priority: P2)

Học sinh tạo agent "Bạn ôn từ vựng tiếng Anh" cho riêng mình; phụ huynh tạo agent "Nhắc lịch học của con"; giáo viên tạo
agent như hiện nay. Khi tạo, người tạo chọn công cụ được phép với vai trò của mình và cấp quyền giao việc cho các agent
mình đang dùng được. Giống OpenBot, agent mới được tạo ở chế độ riêng tư và không có quyền giao việc nào. Agent của học
sinh và phụ huynh muốn đưa vào lớp, vào nhóm hoặc chia sẻ thì phải qua kiểm định và được giáo viên của lớp cho phép.

**Why this priority**: Người dùng yêu cầu rõ. Trình tạo agent đã có sẵn cho giáo viên, nên story này chủ yếu là mở quyền
và thêm hàng rào an toàn.

**Independent Test**: Đăng nhập học sinh demo, tạo agent, thử trong sandbox, rồi chat riêng với nó. Thử đưa agent đó vào
nhóm lớp: hệ thống báo cần kiểm định và giáo viên duyệt.

**Acceptance Scenarios**:

1. **Given** học sinh hoặc phụ huynh đăng nhập, **When** mở trình tạo agent, **Then** tạo được agent, trừ các công cụ
   không dành cho vai trò đó.
2. **Given** agent vừa tạo, **When** người tạo chat với nó, **Then** agent chạy dưới mọi lớp an toàn của nền tảng, và
   hướng dẫn của người tạo không tắt được các lớp này.
3. **Given** học sinh cấp quyền giao việc cho agent của mình, **When** chọn agent đích, **Then** chỉ chọn được trong các
   agent học sinh đó đang dùng được.
4. **Given** agent của học sinh hoặc phụ huynh, **When** người tạo muốn đưa vào lớp, nhóm hoặc chia sẻ, **Then** việc đó
   thuộc loại hành động luôn phải hỏi (chia sẻ, đăng), cần qua kiểm định tự động và được giáo viên của lớp cho phép.
5. **Given** phụ huynh chưa đồng ý cho con dùng agent, **When** học sinh tạo hoặc dùng agent cá nhân, **Then** hệ thống chặn
   (giữ cổng đồng ý hiện có).

---

### User Story 6 - Duyệt hành động theo kiểu OpenBot (Priority: P2)

Trước những hành động luôn phải hỏi, agent dừng lại và hiện thẻ duyệt. Các hành động này gồm: gửi cho người khác, chia
sẻ, đăng hoặc công bố, xoá, đổi cài đặt chia sẻ và quyền, và mọi việc liên quan tiền. Thẻ trình bày việc sắp làm, và
người dùng chọn một trong bốn lựa chọn: Cho phép lần này, Cho phép trong hội thoại này, Luôn cho phép ở đây, Từ chối.
Admin quy định với từng vai trò thì mỗi loại hành động hiện những lựa chọn nào. Mặc định với học sinh là "hỏi mỗi lần":
thẻ chỉ có "Cho phép lần này" và "Từ chối". Người dùng bật được "Cực kỳ cẩn thận" để hệ thống hỏi trước mọi thay đổi.

**Why this priority**: Đây là hàng rào bắt buộc cho story 3 (gửi câu hỏi cho người khác) và story 5 (chia sẻ agent).

**Independent Test**: Với giáo viên demo, nhờ agent gửi câu hỏi cho phụ huynh và chọn "Cho phép trong hội thoại này".
Lần gửi thứ hai trong cùng hội thoại không hỏi lại; sang hội thoại khác thì hỏi lại. Với học sinh demo, thẻ chỉ có hai
lựa chọn.

**Acceptance Scenarios**:

1. **Given** agent sắp làm một hành động luôn phải hỏi, **When** tới bước đó, **Then** hành động chưa chạy và người dùng
   thấy thẻ duyệt mô tả việc sắp làm, nội dung xem trước và đối tượng chịu tác động.
2. **Given** người dùng chọn "Từ chối", **When** agent làm tiếp, **Then** hành động không chạy và agent được báo là người
   dùng đã từ chối.
3. **Given** người dùng chọn "Cho phép trong hội thoại này", **When** agent lặp lại đúng hành động đó (cùng agent, cùng
   công cụ, cùng đối tượng) trong hội thoại này, **Then** không hỏi lại; người dùng tắt được lựa chọn này bất cứ lúc nào.
4. **Given** người dùng chọn "Luôn cho phép ở đây", **When** lưu, **Then** một quy tắc xuất hiện trong mục Duyệt của cài
   đặt và người dùng xoá được nó.
5. **Given** một quy tắc cho phép và một quy tắc từ chối cùng khớp, **When** xét, **Then** quy tắc từ chối thắng. Không có
   chính sách nào khớp, hoặc quy tắc bị hỏng, thì không cho phép.
6. **Given** một quy tắc gõ tay hoặc quy tắc của lớp, **When** nó định cho phép một loại hành động luôn phải hỏi, **Then**
   nó không có hiệu lực; chỉ câu trả lời trên thẻ của đúng loại đó mới cho phép được.
7. **Given** hành động cần duyệt phát sinh trong lượt của một agent đang chạy theo giao việc, **When** tới bước duyệt,
   **Then** thẻ duyệt hiện ở hội thoại gốc cho người dùng gốc; không đưa được về thì hành động bị từ chối.

---

### User Story 7 - Theo dõi hoạt động (Priority: P3)

Mỗi agent có trang hoạt động: nó đã chạy, đọc, lưu gì, đã giao việc cho ai, kèm kết quả. Giáo viên (với lớp của mình),
chủ agent (với agent của mình) và admin xem được những gì đã được cho phép, bị từ chối (kèm quy tắc hoặc giới hạn đã
chặn), bị lỗi, và các câu hỏi gửi người đang chờ, đã trả lời, hết hạn hay không đến được ai.

**Why this priority**: Cần cho truy vết và demo (kịch bản OpenBot yêu cầu xem Activity sau mỗi test), nhưng không chặn
trải nghiệm chính.

**Independent Test**: Sau khi chạy các ca ở story 1–3, mở trang hoạt động của Trợ lý lớp và nhật ký của lớp. Phải thấy
đủ các lần giao việc, các lần bị từ chối kèm lý do, và các câu hỏi gửi người.

**Acceptance Scenarios**:

1. **Given** đã có giao việc trong lớp, **When** giáo viên mở nhật ký lớp, **Then** mỗi lần giao việc có agent hỏi, agent
   được hỏi, tầng, thời gian và kết quả (được mời, bị từ chối kèm lý do, đã giao, lỗi, thử lại).
2. **Given** học sinh hoặc phụ huynh, **When** mở nhật ký, **Then** chỉ thấy hoạt động trong hội thoại của chính mình.
3. **Given** có một lần từ chối, **When** xem nhật ký, **Then** dòng đó ghi rõ quy tắc, quyền hoặc giới hạn đã chặn.

---

### Edge Cases

- **Vòng lặp giao việc** (A → B → A, A → B → C → A). Nền tảng từ chối mọi yêu cầu tới agent đã có trong chuỗi, hoặc khi
  vượt giới hạn tầng.
- **Bùng nổ giao việc.** Chạm giới hạn số lần giao việc của lượt thì các yêu cầu tiếp theo bị từ chối. Agent làm tiếp với
  những gì đã có.
- **Agent được hỏi bị gỡ khỏi lớp hoặc bị tắt khi việc đang trong hàng đợi.** Việc đó kết thúc là "không nhận được câu
  trả lời"; agent hỏi nói rõ trong hội thoại.
- **Câu trả lời giao việc về sau khi agent hỏi đã viết kết luận.** Câu trả lời vẫn được ghi vào thanh hoặc tin riêng (vì
  được ghi nguyên văn), kèm dấu "về muộn"; agent hỏi không tự viết lại kết luận.
- **Người nhận câu hỏi rời lớp, bị gỡ liên kết phụ huynh hoặc bị khoá** trước khi trả lời. Câu hỏi bị huỷ; agent báo người
  dùng gốc.
- **Lớp có hai giáo viên cùng môn.** Agent đề xuất người nhận, người dùng chọn trên thẻ duyệt. Lớp không có giáo viên
  đúng môn thì đề xuất giáo viên chủ nhiệm.
- **Câu trả lời của người lớn chứa thông tin cá nhân hoặc vi phạm an toàn.** Câu trả lời đi qua bước ẩn thông tin cá nhân
  và kiểm duyệt trước khi tới agent và học sinh.
- **Nội dung câu hỏi gửi người lớn vi phạm an toàn** (ví dụ lời xúc phạm giáo viên). Câu hỏi không được đưa ra duyệt; agent
  báo lý do.
- **Dấu hiệu tự làm hại**, ở chat riêng hay nhóm. Không giao việc, không hỏi người khác; đi thẳng luồng hỗ trợ an toàn
  như hiện nay. Trong nhóm, phản hồi hỗ trợ chỉ gửi riêng cho người nhắn, và giáo viên chủ nhiệm nhận cảnh báo theo cơ
  chế hiện có.
- **Hai người trong nhóm cùng gọi agent một lúc.** Các lượt xử lý lần lượt theo thứ tự đến; người vẫn gửi tin được trong
  lúc agent đang trả lời.
- **Câu trả lời của agent được hỏi không qua kiểm duyệt** (ví dụ đáp án hoàn chỉnh trong lớp cấm đưa đáp án). Thanh "Đã
  hỏi" hoặc tin riêng chỉ hiện "Nội dung đã được ẩn"; agent hỏi được báo là câu trả lời bị ẩn.
- **Chế độ không có người thật** (kiểm định, bộ đánh giá, sandbox). Giao việc chạy như thật. Hỏi người coi là "không đến
  được ai". Hành động cần duyệt coi là "Từ chối".
- **Người dùng rời đi giữa chừng.** Các việc giao trong hàng đợi vẫn chạy, và câu trả lời vẫn được ghi vào hội thoại để
  người dùng đọc khi quay lại. Không hành động cần duyệt nào chạy khi chưa có câu trả lời trên thẻ.
- **Thẻ duyệt hoặc câu hỏi được trả lời sau khi hết hạn.** Không có tác dụng; hội thoại báo đã hết hạn.
- **Phụ huynh rút đồng ý** khi học sinh có câu hỏi đang chờ hoặc đang trong nhóm. Học sinh không dùng agent được nữa; câu
  hỏi đang chờ bị huỷ; học sinh vẫn đọc và nhắn với người trong nhóm nếu chính sách lớp cho phép.

## Requirements *(mandatory)*

### Functional Requirements

**Tạo agent**

- **FR-001**: Học sinh, giáo viên và phụ huynh MUST tạo được agent bằng trình tạo agent hiện có (tên, mô tả, avatar,
  hướng dẫn, công cụ, phiên bản, sandbox).
- **FR-002**: Công cụ chọn được khi tạo agent MUST lọc theo vai trò người tạo; học sinh và phụ huynh MUST không chọn được
  công cụ chỉ dành cho giáo viên.
- **FR-003**: Agent mới MUST ở chế độ riêng tư và chưa có quyền giao việc nào. Agent của học sinh hoặc phụ huynh MUST chỉ
  được đưa vào lớp, nhóm hoặc chia sẻ sau khi qua kiểm định tự động và được giáo viên của lớp cho phép. Bản thân việc đưa
  hoặc chia sẻ là hành động luôn phải hỏi (FR-032).
- **FR-004**: Mọi agent, bất kể ai tạo, MUST chạy dưới quy tắc nền tảng, sàng lọc đầu vào, kiểm duyệt đầu ra và chính
  sách lớp; hướng dẫn của người tạo MUST không ghi đè được các lớp này.
- **FR-005**: Học sinh MUST chỉ tạo và dùng agent khi phụ huynh đã đồng ý (cổng đồng ý hiện có).

**Giao việc giữa các agent** (theo `message_bot` của OpenBot)

- **FR-006**: Quyền giao việc MUST là một quyền cấp cho từng agent, chỉ tới các agent cụ thể. Người tạo agent cấp quyền
  này. Giáo viên MUST thu hẹp được quyền này trong lớp của mình (không mở rộng hơn quyền người tạo đã cấp). Agent không
  được cấp cho ai MUST không được mời dùng công cụ giao việc.
- **FR-007**: Yêu cầu giao việc MUST có cấu trúc: agent đích, việc cần làm, giới hạn, và thế nào là câu trả lời tốt.
  Agent được hỏi MUST chỉ nhận yêu cầu này (cùng nội dung agent hỏi chủ động đính kèm), không nhận toàn bộ lịch sử hội
  thoại.
- **FR-008**: Nền tảng, không phải mô hình, MUST quyết định: agent đích (tra theo danh sách agent người dùng gốc được thấy
  trong lớp, nhóm hoặc không gian hiện tại, sau khi áp dụng quyền đã cấp), hội thoại nhận câu trả lời (hội thoại gốc),
  người gửi (agent hỏi), và tầng hiện tại. Không giá trị nào trong số này lấy từ nội dung tin nhắn hay từ mô hình.
- **FR-009**: Agent không tồn tại, agent không được thấy và agent không được cấp quyền MUST nhận **cùng một** lời từ chối,
  để không lộ sự tồn tại của agent. Agent hỏi MUST được báo lời từ chối để tự giải thích với người dùng.
- **FR-010**: Agent được hỏi MUST chạy với tư cách người dùng gốc, bằng vai trò, quyền và công cụ của chính nó, chỉ thấy
  dữ liệu người dùng gốc được thấy, theo chính sách lớp đối với người đó; MUST không thừa hưởng quyền của agent hỏi.
- **FR-011**: Nền tảng MUST có hai giới hạn: số tầng tối đa (mặc định 2) và số lần giao việc tối đa mỗi lượt (mặc định 6).
  Cả hai chỉnh được trong cấu hình. Chạm giới hạn thì yêu cầu MUST bị từ chối chứ không bị cắt bớt. Số tầng = 0 MUST tắt
  hẳn tính năng: không agent nào được mời dùng công cụ giao việc, và hàng đợi giao việc không chạy.
- **FR-012**: Yêu cầu tới một agent đã có trong chuỗi giao việc hiện tại MUST bị từ chối.
- **FR-013**: Giao việc MUST bất đồng bộ. Mỗi yêu cầu là một việc trong hàng đợi, chạy độc lập (nhiều yêu cầu chạy song
  song được), và vẫn chạy khi người dùng đã rời trang. Agent được hỏi MUST chạy trong luồng nháp riêng mà người dùng không
  thấy.
- **FR-014**: Câu trả lời của agent được hỏi MUST được nền tảng ghi **nguyên văn** vào hội thoại gốc, gắn với yêu cầu
  giao việc đó, dưới tên và avatar của agent được hỏi. Không mô hình nào chạy ở bước ghi, ngoài kiểm duyệt đầu ra
  (FR-048).
- **FR-015**: Mỗi yêu cầu giao việc MUST có mã duy nhất (theo agent được hỏi và lượt). Câu trả lời MUST được ghi tối đa
  một lần, dù việc có chạy lại hoặc người dùng tải lại trang.
- **FR-016**: Yêu cầu giao việc lỗi MUST được thử lại tới số lần cấu hình được (mặc định 2). Hết số lần mà vẫn không có
  câu trả lời thì nền tảng MUST đánh dấu "không nhận được câu trả lời", và agent hỏi MUST nói trong hội thoại rằng không
  nhận được gì và phần nào vì thế chưa kiểm chứng được. Người dùng MUST không thấy mã lỗi kỹ thuật.
- **FR-017**: Khi mọi yêu cầu giao việc của một lượt đều đã có kết quả (trả lời, không nhận được, bị từ chối), agent hỏi
  MUST nhận một lượt tiếp để làm nốt việc. Ở lượt này, agent dẫn tới các câu trả lời đã có, MUST không chép lại nguyên văn,
  và ghi tên các agent đã đóng góp. *(Bổ sung so với OpenBot: tài liệu OpenBot không nói rõ agent hỏi có được làm tiếp sau
  khi nhận câu trả lời hay không.)*
- **FR-018**: Câu hỏi agent tự làm được MUST không kích hoạt giao việc, và thời gian trả lời MUST không chậm hơn hiện nay
  một cách đáng kể (SC-001).
- **FR-019**: Giáo viên MUST tắt được giao việc giữa agent cho lớp của mình (tương đương số tầng = 0 trong lớp đó), mặc
  định bật. Công cụ hỏi người (FR-024) MUST vẫn có, kể cả khi đã tắt giao việc.

**Hiển thị giao việc trong chat riêng**

- **FR-020**: Mỗi yêu cầu giao việc trong chat riêng MUST hiện một thanh "Đã hỏi <tên agent>" có avatar và trạng thái
  (đang chờ, đã trả lời, không nhận được câu trả lời, bị từ chối, về muộn), cập nhật theo thời gian thực.
- **FR-021**: Thanh MUST mở và đóng được. Khi mở, thanh hiển thị yêu cầu đã gửi và nguyên văn câu trả lời. Khi agent hỏi
  đã viết lượt tiếp (FR-017), các thanh MUST mặc định đóng.
- **FR-022**: Giao việc ở tầng sâu hơn MUST hiện lồng trong thanh của agent tầng trên. Các thanh MUST được lưu cùng hội
  thoại và hiện lại khi mở lại hội thoại.

**Hiển thị giao việc trong nhóm chat**

- **FR-023**: Trong nhóm, câu trả lời của agent được hỏi MUST hiện thành một tin riêng dưới tên và avatar của nó, có nhãn
  "trả lời cho <agent hỏi>", đúng thứ tự thời gian, và mọi thành viên đều thấy. Yêu cầu giao việc MUST hiện gọn (ví dụ
  "Trợ lý lớp đã hỏi Gia sư Toán"), mở ra xem được nội dung.

**Hỏi người** (theo `ask_person` của OpenBot)

- **FR-024**: Công cụ hỏi người MUST có sẵn cho mọi lượt chạy của mọi agent, kể cả agent đang chạy theo giao việc và
  agent không được cấp quyền nào. Hướng dẫn nền tảng MUST dặn agent: khi cần một quyết định của người thì dừng lại hỏi,
  không đoán và không đẩy câu hỏi đó sang agent khác.
- **FR-025**: Mặc định, câu hỏi gửi cho người đang trò chuyện, hiện ngay trong hội thoại. Đây cũng là cách agent hỏi lại
  khi thiếu thông tin, và không có giới hạn cứng số lần hỏi. Ngoài ra, nền tảng MUST cho gửi tới người khác, chỉ trong
  danh sách người nền tảng cho phép với người dùng gốc:
  - với học sinh: giáo viên của lớp (kèm môn), giáo viên chủ nhiệm, phụ huynh đã liên kết của chính học sinh đó;
  - với giáo viên và phụ huynh: thành viên cùng lớp hoặc cùng nhóm.

  Agent và nội dung tin nhắn MUST không vượt được giới hạn này.
- **FR-026**: Gửi câu hỏi tới người khác MUST là hành động loại "gửi cho người khác" và đi qua duyệt (FR-032), trước khi
  rời khỏi hội thoại. Hỏi chính người đang trò chuyện MUST không cần duyệt.
- **FR-027**: Câu hỏi MUST có nội dung, có thể kèm các lựa chọn agent đề xuất (ví dụ Đồng ý / Sửa / Từ chối). Người nhận
  MUST luôn trả lời tự do được. Câu hỏi có hạn chờ (mặc định 72 giờ).
- **FR-028**: Người nhận MUST thấy câu hỏi trong **hộp yêu cầu** của mình (có huy hiệu khi có câu hỏi mới). Nếu câu hỏi
  được tạo trong nhóm mà người nhận là thành viên, thẻ câu hỏi MUST hiện cả trong nhóm, và chỉ người nhận trả lời được.
- **FR-029**: Câu trả lời MUST được ghi vào đúng hội thoại gốc và đúng lượt đã tạo câu hỏi, dưới tên người trả lời, kể
  cả khi câu hỏi do agent đang chạy theo giao việc ở tầng sâu tạo ra. Agent tạo câu hỏi MUST làm tiếp từ chỗ đã dừng.
  Mỗi câu hỏi MUST nhận tối đa một câu trả lời. Sau khi trả lời, hết hạn hoặc bị huỷ, câu hỏi MUST không trả lời được
  nữa.
- **FR-030**: Câu hỏi không đến được ai MUST được ghi nhận là "không đến được ai" và báo cho agent. Câu hỏi hết hạn hoặc
  bị người dùng gốc huỷ cũng MUST được báo cho agent. Trong mọi trường hợp này, agent MUST báo cho người dùng gốc. Trong
  lúc chờ, người dùng gốc MUST chat tiếp được, và hội thoại hiện "Đang chờ <tên người> trả lời".
- **FR-031**: Nội dung câu hỏi và câu trả lời của người MUST qua bước ẩn thông tin cá nhân và kiểm duyệt nội dung. Câu hỏi
  có nội dung không qua kiểm duyệt MUST không được đưa ra duyệt hay gửi đi.

**Duyệt hành động** (theo Approvals của OpenBot)

- **FR-032**: Mỗi hành động MUST được quyết định theo thứ tự sau, câu trả lời đầu tiên khớp là kết quả:
  1. **Loại luôn phải hỏi**: gửi cho người khác, chia sẻ, đăng hoặc công bố, xoá, đổi cài đặt chia sẻ hay quyền, mọi việc
     liên quan tiền. Loại này luôn hiện thẻ duyệt, bất kể công tắc của người dùng.
  2. **Quy tắc**: của người dùng, của lớp (do giáo viên đặt), của admin, và cho phép theo hội thoại. Quy tắc chặt nhất
     khớp sẽ thắng. "Từ chối" được xét trước "cho phép". Không chính sách nào khớp thì không cho phép. Quy tắc hỏng thì từ
     chối.
  3. **"Cực kỳ cẩn thận"**: công tắc của người dùng trong cài đặt Duyệt, mặc định tắt. Bật lên thì hỏi trước mọi thay đổi.
- **FR-033**: Thẻ duyệt MUST trình bày việc sắp làm, nội dung xem trước và đối tượng chịu tác động, kèm tối đa bốn lựa
  chọn:
  - **Cho phép lần này**: chỉ lần này.
  - **Cho phép trong hội thoại này**: lặp lại đúng hành động đó (cùng agent, công cụ, đối tượng) trong hội thoại này,
    cho tới khi người dùng tắt hoặc xoá hội thoại.
  - **Luôn cho phép ở đây**: lưu thành quy tắc trong cài đặt Duyệt, xoá được.
  - **Từ chối**: agent không làm và được báo là người dùng đã từ chối.
- **FR-034**: Chỉ câu trả lời trên thẻ của đúng loại hành động MUST mở được một loại luôn phải hỏi. Quy tắc gõ tay, quy
  tắc của lớp và quy tắc của admin MUST không mở được loại này; chúng chỉ làm chặt hơn.
- **FR-035**: Admin MUST đặt được, cho từng loại luôn phải hỏi và từng vai trò, một trong ba chế độ:
  - **Người dùng tự chọn**: đủ bốn lựa chọn.
  - **Hỏi mỗi lần**: chỉ "Cho phép lần này" và "Từ chối".
  - **Người dùng tự làm**: agent không bao giờ làm; thẻ chỉ có "Tôi đã tự làm" và "Đừng làm".

  Mặc định: học sinh là "Hỏi mỗi lần" cho mọi loại; giáo viên và phụ huynh là "Người dùng tự chọn".
- **FR-036**: Hành động được cho phép MUST chạy đúng tham số đã trình bày và tối đa một lần. Bấm lại hoặc tải lại trang
  MUST không tạo bản thứ hai. Thẻ đã trả lời hoặc đã hết hạn (mặc định 24 giờ) MUST không bấm được nữa.
- **FR-037**: Hành động cần duyệt phát sinh trong lượt của agent đang chạy theo giao việc (lúc không có ai theo dõi) MUST
  hiện thẻ duyệt ở hội thoại gốc cho người dùng gốc. Không đưa được về thì MUST từ chối, không cho qua.
- **FR-038**: Ở chế độ không có người thật (kiểm định, bộ đánh giá, sandbox), mọi thẻ duyệt MUST coi là "Từ chối" và mọi
  câu hỏi gửi người MUST coi là "không đến được ai".

**Nhóm chat**

- **FR-039**: Mỗi nhóm MUST thuộc một lớp. Thành viên người lấy từ lớp đó: giáo viên (hiển thị môn), học sinh, phụ huynh
  đã liên kết với học sinh của lớp. Thành viên agent là agent đã cài và dùng được trong lớp. Quyền xem và gửi tin MUST do
  danh sách thành viên quyết định.
- **FR-040**: Giáo viên của lớp MUST tạo được nhóm. Học sinh và phụ huynh MUST tạo được nhóm khi giáo viên bật quyền này
  trong chính sách lớp (mặc định tắt). Nhóm có học sinh MUST có ít nhất một giáo viên của lớp, và giáo viên chủ nhiệm
  MUST xem được mọi nhóm của lớp.
- **FR-041**: Người tạo nhóm và giáo viên trong nhóm MUST thêm và bớt được thành viên (người và agent), đặt tên nhóm và
  chọn agent mặc định của nhóm (mặc định là trợ lý lớp nếu có).
- **FR-042**: Người đọc chung một dòng tin; mỗi agent trong nhóm MUST có luồng riêng. Mọi tin MUST hiện cho mọi thành
  viên gần như ngay lập tức, kèm tên, vai trò và avatar của người hoặc agent gửi.
- **FR-043**: Định tuyến trong nhóm theo thứ tự:
  - Tin gọi `@agent` thì agent đó nhận.
  - Tin không gọi tên ai thì bộ định tuyến chọn trong các agent của nhóm mà người gửi dùng được. Không đủ chắc thì agent
    mặc định của nhóm nhận. Thứ tự trong danh sách MUST không quyết định agent nào nhận.
  - Tin chỉ gọi tên người, hoặc bộ định tuyến xác định đây là trò chuyện giữa người với người, thì MUST không có agent
    nào lên tiếng.
- **FR-044**: Agent gọi `@Tên` một agent khác trong nhóm MUST được xử lý như giao việc, theo đúng FR-006 đến FR-017.
- **FR-045**: Agent trả lời trong nhóm MUST theo vai trò và chính sách của **người gửi tin đã gọi nó** (ví dụ câu hỏi của
  học sinh vẫn chịu chính sách "không đưa đáp án" dù nhóm có giáo viên). Ngữ cảnh agent dùng MUST chỉ gồm tin trong nhóm
  mà người đó được xem, trừ nội dung đã bị ẩn.
- **FR-046**: Thành viên mới MUST chỉ thấy tin từ lúc được thêm, trừ khi người thêm chọn cho xem lịch sử. Thành viên bị
  bớt MUST không nhận và không xem được tin mới.

**Chat riêng**

- **FR-047**: Người dùng MUST chat riêng được với mọi agent họ dùng được (cài vào lớp, cài cá nhân, tự tạo). Giao việc,
  hỏi người và duyệt hành động MUST áp dụng trong chat riêng như trong nhóm.

**An toàn**

- **FR-048**: Cổng đồng ý của phụ huynh, ẩn thông tin cá nhân và sàng lọc an toàn MUST chạy trước khi agent nhận mọi tin
  của người, kể cả câu trả lời cho câu hỏi và tin trong nhóm. Mọi nội dung hiển thị cho người dùng MUST qua kiểm duyệt đầu
  ra theo vai trò và chính sách của người xem, kể cả câu trả lời nguyên văn của agent được hỏi. Nội dung bị ẩn MUST hiện
  "Nội dung đã được ẩn" và được ghi thành sự kiện an toàn kèm agent liên quan.
- **FR-049**: Khi sàng lọc chặn tin hoặc phát hiện dấu hiệu cần hỗ trợ an toàn, nền tảng MUST không giao việc, không hỏi
  người khác, và MUST xử lý như hiện nay.
- **FR-050**: Ngữ cảnh agent nhớ ở các lượt sau MUST gồm các tin trong hội thoại (tin người dùng, câu trả lời giao việc
  đã ghi vào hội thoại, câu hỏi gửi người và câu trả lời). MUST không gồm nội dung trong luồng nháp của agent được hỏi.

**Nhật ký và đo lường**

- **FR-051**: Nền tảng MUST ghi mỗi yêu cầu giao việc với các trạng thái: được mời, bị từ chối (kèm quyền hoặc giới hạn
  đã chặn), đã giao, lỗi, thử lại. Bản ghi gồm agent hỏi, agent được hỏi, tầng, hội thoại, thời gian và lượng dùng mô
  hình, để báo cáo chi phí theo agent vẫn đúng. Báo cáo sử dụng MUST tách được lượt có giao việc và lượt không có.
- **FR-052**: Nền tảng MUST ghi mỗi câu hỏi gửi người (đã gửi, không đến được ai, đã trả lời, hết hạn, huỷ) và mỗi quyết
  định duyệt (lựa chọn nào, do thẻ, quy tắc nào hay chế độ nào quyết). Mỗi lần từ chối MUST ghi kèm quy tắc đã chặn.
- **FR-053**: Mỗi agent MUST có trang hoạt động: nó đã chạy, đọc, lưu gì, đã giao việc cho ai, kèm kết quả. Tệp đã lưu chỉ
  ghi tên và kích thước, không ghi nội dung.
  - Giáo viên xem được nhật ký của lớp mình.
  - Chủ agent xem được hoạt động của agent mình, không kèm nội dung hội thoại của người khác.
  - Học sinh và phụ huynh chỉ xem được hoạt động trong hội thoại của chính mình.
  - Admin xem được toàn bộ những gì đã được cho phép, bị từ chối và bị lỗi.
- **FR-054**: Dự án MUST có bộ kịch bản kiểm thử tương đương 5 test của OpenBot (luồng đầy đủ nhiều tầng, agent dữ liệu từ
  chối ngoài phạm vi, agent không gửi ra ngoài khi chưa duyệt, agent không bịa, quyền giao việc bị chặn ở tầng nền tảng),
  dựng trên agent và dữ liệu demo của trường học, chạy được và báo được các chỉ số ở Success Criteria.

**Vận hành**

- **FR-055**: `dev.ps1` MUST dựng được đủ những gì feature cần bằng một lệnh, theo nguyên tắc III của hiến pháp: thay đổi
  dữ liệu, cấu hình mới, hàng đợi giao việc, agent demo đã cấp quyền giao việc, và nhóm demo.

### Key Entities *(include if feature involves data)*

- **Agent (đã có)**: Bổ sung người tạo có thể là học sinh hoặc phụ huynh, chế độ hiển thị (riêng tư, đã được duyệt vào
  lớp).
- **Quyền giao việc**: Quyền cấp cho một agent được giao việc tới một agent cụ thể. Người tạo cấp; giáo viên có thể thu hẹp
  theo lớp.
- **Hội thoại (đã có)**: Bổ sung loại: chat riêng hoặc nhóm. Nhóm có tên, lớp, người tạo, agent mặc định.
- **Thành viên nhóm**: Một người hoặc một agent trong nhóm, kèm vai trò hiển thị, thời điểm vào, quyền quản lý, có được xem
  lịch sử hay không.
- **Luồng của agent trong nhóm**: Ngữ cảnh riêng của mỗi agent trong một nhóm.
- **Tin nhắn (đã có)**: Bổ sung người gửi (người hoặc agent), yêu cầu giao việc hoặc câu hỏi gửi người gắn với tin, nhãn
  "trả lời cho".
- **Yêu cầu giao việc**: Mã duy nhất, agent hỏi, agent được hỏi, hội thoại và lượt gốc, tầng, yêu cầu gốc nó thuộc về (nếu
  có), nội dung có cấu trúc (việc, giới hạn, câu trả lời tốt), trạng thái, số lần thử, câu trả lời nguyên văn, kết quả kiểm
  duyệt khi hiển thị.
- **Câu hỏi gửi người**: Người dùng gốc, hội thoại và lượt gốc, agent tạo, yêu cầu giao việc nó thuộc về (nếu có), người
  nhận, nội dung, các lựa chọn, hạn chờ, trạng thái, câu trả lời, người trả lời.
- **Hộp yêu cầu**: Các câu hỏi gửi tới một người, lọc được theo trạng thái và lớp.
- **Quy tắc duyệt**: Phạm vi (người dùng, lớp, admin, hội thoại), loại hành động, điều kiện khớp (agent, công cụ, đối
  tượng), kết quả (cho phép, từ chối, hỏi).
- **Chế độ duyệt theo loại**: Với mỗi loại luôn phải hỏi và mỗi vai trò: người dùng tự chọn, hỏi mỗi lần, hoặc người dùng
  tự làm.
- **Thẻ duyệt**: Hành động đang chờ duyệt: hội thoại, agent, công cụ, tham số, nội dung xem trước, các lựa chọn hiển thị,
  câu trả lời, hạn.
- **Chính sách lớp (đã có)**: Bổ sung: bật/tắt giao việc giữa agent, học sinh và phụ huynh có được tạo nhóm không, có được
  xin đưa agent tự tạo vào lớp không.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Với câu hỏi không cần agent khác, thời gian tới chữ đầu tiên (trung vị) tăng không quá 10% so với trước
  feature, đo trên cùng bộ câu hỏi.
- **SC-002**: 100% yêu cầu giao việc tới agent không được cấp quyền, không tồn tại hoặc không được thấy đều bị từ chối, kể cả
  khi người dùng yêu cầu trong tin nhắn. Ba trường hợp này nhận lời từ chối giống hệt nhau.
- **SC-003**: Trên bộ ca tương đương OpenBot Test 2, không có dữ liệu ngoài phạm vi nào bị lộ qua agent được hỏi.
- **SC-004**: 100% câu trả lời của người nhận quay về đúng hội thoại gốc và agent làm tiếp được, kể cả khi câu hỏi do agent
  ở tầng 2 tạo.
- **SC-005**: Trên bộ kịch bản có chèn lỗi mạng, chạy lại việc và tải lại trang, không có câu trả lời nào bị ghi trùng (giao
  việc, câu hỏi gửi người, hành động đã duyệt).
- **SC-006**: Không mã lỗi kỹ thuật nào hiện cho người dùng khi agent được hỏi lỗi. Trong 100% trường hợp đó, agent hỏi
  nói rõ là không nhận được câu trả lời.
- **SC-007**: Trên bộ kịch bản luồng nhiều agent, ít nhất 85% lượt có đúng tập agent được hỏi như kỳ vọng (không thiếu agent
  cần thiết, thừa tối đa một).
- **SC-008**: Trong nhóm, tin nhắn hiện ở các thành viên khác trong vòng 2 giây khi chạy local.
- **SC-009**: Trong buổi thử với người dùng mẫu, ít nhất 4/5 người trả lời đúng "agent nào đã được hỏi và nó trả lời gì" chỉ
  bằng cách nhìn giao diện, ở cả chat riêng và nhóm.
- **SC-010**: Một học sinh mới tạo được agent cá nhân đầu tiên và chat với nó trong vòng 5 phút mà không cần hướng dẫn.
- **SC-011**: Giáo viên trả lời được một câu hỏi trong hộp yêu cầu với không quá 2 thao tác sau khi mở.
- **SC-012**: Trên bộ red-team hiện có cộng thêm các ca lách qua giao việc và qua nhóm, tỉ lệ nội dung vi phạm lọt ra người
  dùng không cao hơn so với khi chỉ một agent trả lời.
- **SC-013**: Không có hành động nào thuộc loại luôn phải hỏi chạy khi chưa có câu trả lời cho phép trên thẻ của đúng loại
  đó. Kiểm tra bằng các ca cố tình bảo agent bỏ qua duyệt, hoặc dùng quy tắc gõ tay để mở loại đó.
- **SC-014**: Trên bộ kịch bản, tỉ lệ hỏi thừa (agent hỏi lại người dùng dù yêu cầu đã đủ rõ) không quá 10%. Tỉ lệ agent hỏi
  người thay vì tự quyết ở các ca cần người lớn quyết đạt ít nhất 90%.

## Assumptions

- Feature triển khai trên `main`, mở rộng runtime agent, orchestrator, guard, kiểm định và trình tạo agent đang có. Không
  dùng, không chờ và không hợp nhất với nhánh `feat/dify-runtime`.
- Cơ chế tham chiếu là OpenBot v1.0.3 (bản cài local): tài liệu `docs/architecture.md` (mục giao việc `message_bot`, hỏi
  người `ask_person`, nhóm chat) và `docs/approvals.md`. Một số con số OpenBot không công bố, nên spec tự chọn mặc định:
  số tầng 2, số lần giao việc mỗi lượt 6, số lần thử lại 2, hạn câu hỏi gửi người 72 giờ, hạn thẻ duyệt 24 giờ. Tất cả
  chỉnh được.
- Các điểm spec bổ sung hoặc chặt hơn OpenBot, vì người dùng là học sinh:
  - agent hỏi có lượt làm tiếp sau khi nhận đủ câu trả lời (FR-017);
  - câu trả lời nguyên văn vẫn qua kiểm duyệt đầu ra (FR-048);
  - hỏi người được nối tới giáo viên và phụ huynh (FR-025);
  - học sinh mặc định ở chế độ duyệt "Hỏi mỗi lần" (FR-035);
  - câu hỏi duyệt từ agent tầng dưới bắt buộc về hội thoại gốc (FR-029, FR-037).
- Không mang sang: tính năng "Tự kiểm duyệt" (auto-review) của OpenBot, máy tính ảo của agent và "Cầm lái" (take the
  wheel), lịch chạy định kỳ (routines), kết nối ứng dụng ngoài.
- Danh sách quyền giao việc mặc định trống khi tạo agent mới. Agent nền tảng mẫu được seed sẵn quyền hợp lý: trợ lý lớp
  được hỏi các gia sư môn; gia sư môn được hỏi agent tài liệu và agent tạo đề.
- Nhóm chat luôn gắn với một lớp. Nằm ngoài phạm vi: nhóm không thuộc lớp, nhóm liên lớp, nhắn riêng giữa hai người không
  có agent.
- "Giáo viên các môn" lấy theo môn của giáo viên trong lớp. Nếu dữ liệu lớp chưa ghi môn cho từng giáo viên thì feature bổ
  sung trường này.
- Thông báo chỉ trong ứng dụng (huy hiệu, hộp yêu cầu). Email, SMS và thông báo đẩy nằm ngoài phạm vi.
- Kịch bản kiểm thử dùng dữ liệu demo của trường học. Ví dụ pháp chế của OpenBot chỉ là mẫu hành vi.
