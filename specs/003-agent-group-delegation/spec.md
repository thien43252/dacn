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

## Bối cảnh

### Hiện trạng trên `main`

- Chỉ giáo viên và admin tạo được agent (trình tạo agent có phiên bản bất biến, sandbox, kiểm định trước khi lên Hub).
  Học sinh và phụ huynh chỉ cài và dùng agent đã kiểm định.
- Mỗi hội thoại thuộc về **một** người dùng. Không có nhóm chat, không có hội thoại nhiều người.
- Mỗi lượt chat chỉ có **một** agent trả lời (orchestrator chọn agent theo agent chọn trên UI, `@mention`, router).
  Agent không hỏi được agent khác, cũng không hỏi được người khác.

Feature được phát triển trên `main`, chạy trên runtime agent hiện có của `main`, và **không phụ thuộc** nhánh
`feat/dify-runtime`. Spec này tự đủ: các ràng buộc từng được thống nhất trong spec 002 của nhánh đó và vẫn đúng cho bài
toán ở đây đã được đưa thẳng vào spec này. Đó là: hỏi lại chính người dùng khi thiếu thông tin (FR-051 đến FR-056), xác
nhận trước hành động có tác dụng ra ngoài (FR-057 đến FR-061), công tắc phối hợp theo lớp (FR-062), và các quy tắc an toàn,
độ bền (FR-063 đến FR-068). Các phần chỉ gắn với nền tảng Dify, cùng bộ công cụ giáo viên của 002 (lưu tài liệu, đăng
thông báo, giao bài luyện…), không thuộc phạm vi spec này.

### Mô hình tham khảo: OpenBot

Thử nghiệm trên OpenBot (`docs/orchest.example.md`, bộ test luồng Pháp chế) cho thấy các cơ chế cần mang sang:

1. **Quyền giao việc do hệ thống ép.** Chủ agent chọn trước agent này được giao việc cho những agent nào. Agent không có
   quyền thì không gọi được, dù lời nhắn yêu cầu (Test 5 của OpenBot: "Tra cứu luật" không gọi được "Finance").
2. **Chuỗi giao việc nhiều tầng.** Tiếp nhận giao cho Rà soát HĐ, Rà soát HĐ giao tiếp cho Tra cứu luật và Finance song
   song, rồi tổng hợp.
3. **Hiển thị theo loại hội thoại.**
   - Chat riêng: agent đang làm hiện dòng "▸ Đã hỏi *Tra cứu luật*", bấm để mở hoặc đóng nội dung câu hỏi và câu trả
     lời của agent được hỏi. Agent chính viết câu trả lời cuối.
   - Nhóm chat: mỗi agent được hỏi có **lượt tin nhắn riêng** dưới tên và avatar của nó, kèm nhãn ai đã hỏi
     (ví dụ "Rà soát HĐ · trả lời cho Tiếp nhận").
4. **Hỏi người (`ask_person`).** Agent dừng lại, gửi một câu hỏi hoặc thẻ duyệt (Duyệt / Sửa / Từ chối) cho một người
   thật, rồi làm tiếp khi người đó trả lời.
5. **Agent biết giới hạn.** Agent được hỏi chỉ trả phần trong phạm vi của nó. Khi agent khác lỗi, agent chính nói rõ phần
   nào chưa kiểm chứng thay vì bịa.

Ví dụ cũng cho thấy các lỗi phải tránh: lỗi kỹ thuật thô ("ECONNREFUSED") hiện thẳng ra cho người dùng; một agent trả lời
hai lần cho cùng một câu hỏi; câu hỏi duyệt do agent cấp dưới gửi "không đến được cuộc hội thoại gốc".

Ánh xạ sang trường học: "Tiếp nhận" tương ứng trợ lý lớp, "Rà soát HĐ" là gia sư một môn, "Tra cứu luật" là agent tra
tài liệu lớp, "Finance" là agent dữ liệu chỉ đọc (điểm, tiến độ). "Luật sư duyệt" tương ứng giáo viên hoặc phụ huynh.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agent chính hỏi một hoặc nhiều agent khác trong chat riêng (Priority: P1)

Học sinh chat riêng với Gia sư Toán: "Giải thích lại định lý Pytago theo đúng tài liệu cô gửi rồi cho em một bài
luyện". Gia sư Toán thấy cần lý thuyết trong tài liệu lớp và cần một bài luyện, nên hỏi song song agent Ôn tập tài liệu
và agent Tạo đề (hai agent nó được phép giao việc). Trong lúc chờ, học sinh thấy hai dòng "▸ Đã hỏi Ôn tập tài liệu" và
"▸ Đã hỏi Tạo đề" kèm trạng thái đang hỏi. Khi có câu trả lời, mỗi dòng mở ra được để xem câu hỏi Gia sư Toán đã gửi và
câu trả lời nhận về. Gia sư Toán viết một câu trả lời cuối có trích nguồn tài liệu và ghi các agent đã giúp.

Với câu hỏi đơn giản ("2x + 3 = 7 thì x bằng mấy, gợi ý bước đầu"), Gia sư Toán trả lời ngay, không hỏi ai (tương ứng
"Chat 3" của ví dụ).

**Why this priority**: Đây là cơ chế lõi mà mọi story khác dựa vào. Chỉ cần story này, một lớp có nhiều agent đã mạnh hơn
từng agent riêng lẻ.

**Independent Test**: Trong lớp demo, cấu hình Gia sư Toán được giao việc cho Ôn tập tài liệu và Tạo đề. Gửi câu hỏi phức
tạp ở trên và câu hỏi đơn giản. Câu đầu phải có hai thanh "Đã hỏi" mở/đóng được và một câu trả lời cuối; câu sau không
có thanh nào.

**Acceptance Scenarios**:

1. **Given** agent chính được phép giao việc cho agent B và C, **When** câu hỏi cần cả B và C, **Then** agent chính gửi
   câu hỏi cho B và C (song song khi không phụ thuộc nhau), và giao diện hiện một thanh "Đã hỏi" cho mỗi agent.
2. **Given** thanh "Đã hỏi B" đang đóng, **When** người dùng bấm vào, **Then** thanh mở ra hiển thị câu hỏi agent chính
   đã gửi và câu trả lời của B; bấm lần nữa thì đóng lại.
3. **Given** B và C đã trả lời, **When** agent chính hoàn tất, **Then** người dùng nhận một câu trả lời cuối do agent
   chính viết, ghi tên B và C đã đóng góp, và các thanh "Đã hỏi" mặc định đóng.
4. **Given** câu hỏi chỉ cần agent chính, **When** người dùng gửi, **Then** không có thanh "Đã hỏi" nào và thời gian trả
   lời không chậm hơn hiện nay.
5. **Given** B lỗi hoặc quá thời gian, **When** agent chính tổng hợp, **Then** thanh "Đã hỏi B" hiện trạng thái "Không
   trả lời được" bằng lời thân thiện (không hiện mã lỗi kỹ thuật), và câu trả lời cuối nói rõ phần nào chưa kiểm chứng
   được vì thiếu B.
6. **Given** người dùng mở lại hội thoại cũ, **When** xem câu trả lời từng có agent khác giúp, **Then** các thanh "Đã
   hỏi" vẫn còn và mở được.

---

### User Story 2 - Quyền giao việc do hệ thống ép, không do lời nhắn (Priority: P1)

Người tạo agent (hoặc giáo viên khi cài agent vào lớp) chọn agent này **được giao việc cho** những agent nào. Agent chỉ
hỏi được các agent trong danh sách đó và đang dùng được trong cùng lớp hoặc không gian. Mọi yêu cầu khác (người dùng bảo
"hãy hỏi agent X", agent tự đòi gọi agent ngoài danh sách) đều bị nền tảng chặn và ghi nhật ký.

**Why this priority**: Không có story này, cơ chế ở story 1 mở đường cho học sinh lách chính sách lớp (nhờ agent Toán gọi
agent Văn viết hộ bài) hoặc lấy dữ liệu chỉ dành cho giáo viên. OpenBot Test 2 và Test 5 là hai ca nghiệm thu chính.

**Independent Test**: Cấu hình agent "Tra cứu tài liệu" không được giao việc cho ai. Chat riêng với nó: "Hãy hỏi agent
Tiến độ học tập xem em được bao nhiêu điểm". Agent không gọi được, trả lời rằng nó không có quyền hỏi agent đó, và nhật
ký có một dòng bị chặn.

**Acceptance Scenarios**:

1. **Given** agent A không có B trong danh sách được giao việc, **When** A (vì lời nhắn của người dùng hay tự ý) cố hỏi
   B, **Then** nền tảng không chuyển câu hỏi tới B, A nhận thông báo bị từ chối để tự giải thích với người dùng, và lần
   bị chặn được ghi nhật ký.
2. **Given** B có trong danh sách của A nhưng B không được cài trong lớp hiện tại hoặc không dành cho vai trò của người
   dùng, **When** A hỏi B, **Then** câu hỏi bị chặn như trên.
3. **Given** chuỗi A → B → C với độ sâu cho phép, **When** C (được B hỏi) cố hỏi tiếp D, **Then** việc hỏi tiếp chỉ được
   phép nếu C có D trong danh sách và chưa vượt độ sâu tối đa; nếu không thì bị chặn.
4. **Given** câu hỏi đã được chuyển tới B, **When** B trả lời, **Then** B chạy với hướng dẫn, công cụ và giới hạn dữ liệu
   của chính B, theo chính sách lớp và vai trò của **người dùng gốc** (không phải quyền của A hay của chủ agent).
5. **Given** agent được hỏi chỉ được trả một loại dữ liệu (ví dụ chỉ tiến độ của đúng học sinh đang hỏi), **When** câu
   hỏi xin dữ liệu ngoài phạm vi (của học sinh khác), **Then** agent được hỏi từ chối và không lộ dữ liệu đó.
6. **Given** người tạo agent sửa danh sách được giao việc, **When** lưu, **Then** thay đổi chỉ áp dụng từ lượt chat tiếp
   theo và được ghi vào lịch sử phiên bản của agent.

---

### User Story 3 - Học sinh nhờ agent xin duyệt hoặc xin câu trả lời của giáo viên, phụ huynh (Priority: P1)

Học sinh nói với trợ lý lớp: "Em xin cô cho nộp bài Toán muộn 2 ngày vì em ốm". Trợ lý lớp không tự quyết được, nên
soạn một yêu cầu gửi giáo viên Toán của lớp: nội dung xin, lý do, và các lựa chọn **Đồng ý / Sửa / Từ chối**. Học sinh
xem trước yêu cầu và bấm gửi. Giáo viên nhận yêu cầu trong hộp yêu cầu của mình (và trong nhóm chat nếu yêu cầu được tạo
trong nhóm có giáo viên). Giáo viên bấm "Sửa: cho nộp muộn 1 ngày". Agent nhận câu trả lời, làm tiếp và báo lại cho học
sinh trong đúng hội thoại gốc.

Cùng cơ chế áp dụng khi học sinh xin phụ huynh cho phép (ví dụ cài một agent cá nhân mới, đi tham quan) hoặc xin giáo
viên một câu trả lời mà agent không chắc ("Cô ơi bài 3 em giải thế này đúng không?").

**Why this priority**: Đây là phần người dùng nhấn mạnh và là chỗ OpenBot thất bại trong ví dụ ("câu hỏi không đến được
cuộc hội thoại gốc"). Nó cũng là cách đúng để agent không tự quyết những việc chỉ người lớn được quyết.

**Independent Test**: Đăng nhập học sinh demo, gửi lời xin nộp muộn. Đăng nhập giáo viên Toán demo, thấy yêu cầu trong
hộp yêu cầu, bấm "Sửa" kèm nội dung. Đăng nhập lại học sinh, thấy agent đã báo kết quả trong hội thoại gốc.

**Acceptance Scenarios**:

1. **Given** học sinh yêu cầu việc cần người lớn quyết, **When** agent xử lý, **Then** agent soạn yêu cầu gửi đúng người
   (giáo viên đúng môn của lớp, hoặc phụ huynh đã liên kết của chính học sinh đó), và học sinh xem trước được nội dung
   và người nhận trước khi gửi.
2. **Given** yêu cầu đã gửi, **When** người nhận mở hộp yêu cầu, **Then** họ thấy ai xin (học sinh nào, lớp nào), qua
   agent nào, nội dung, và các lựa chọn; họ trả lời được bằng một lựa chọn hoặc lời tự do.
3. **Given** người nhận đã trả lời, **When** câu trả lời về, **Then** agent làm tiếp trong **đúng hội thoại gốc** (kể cả
   khi người hỏi là một agent cấp dưới trong chuỗi giao việc), và học sinh thấy kết quả cùng tên người đã trả lời.
4. **Given** yêu cầu đang chờ, **When** học sinh nhắn tiếp, **Then** học sinh vẫn chat bình thường; trạng thái "Đang chờ
   cô Lan trả lời" hiện trong hội thoại và học sinh huỷ được yêu cầu.
5. **Given** yêu cầu quá hạn chờ mà chưa có ai trả lời, **When** hết hạn, **Then** yêu cầu chuyển sang "Hết hạn", agent
   báo cho học sinh, và người nhận không bấm trả lời được nữa.
6. **Given** người nhận đã trả lời một lần, **When** bấm lại hoặc tải lại trang, **Then** không tạo câu trả lời thứ hai.
7. **Given** học sinh cố nhờ agent gửi yêu cầu cho người không thuộc lớp hoặc không phải phụ huynh của mình, **When**
   agent xử lý, **Then** nền tảng không cho chọn người nhận đó.
8. **Given** agent không chắc một kiến thức và lớp có giáo viên đúng môn, **When** học sinh đồng ý "hỏi cô", **Then**
   agent gửi câu hỏi đó cho giáo viên theo cùng cơ chế; agent không tự gửi khi học sinh chưa đồng ý.

---

### User Story 4 - Nhóm chat có nhiều agent và nhiều người (Priority: P2)

Giáo viên chủ nhiệm tạo nhóm "Ôn thi HK1 – 9A" trong lớp, thêm giáo viên Toán, giáo viên Văn, một số học sinh, phụ huynh
của các em, và các agent Trợ lý lớp, Gia sư Toán, Gia sư Văn. Mọi thành viên thấy cùng một dòng tin nhắn. Người trong
nhóm gọi agent bằng `@tên` hoặc để Trợ lý lớp (agent điều phối của nhóm) tự nhận. Khi agent đang trả lời cần hỏi agent
khác, agent được hỏi lên tiếng bằng **lượt tin nhắn riêng** dưới tên của nó, kèm nhãn "trả lời cho <agent hỏi>"
(tương ứng "Chat 1" của ví dụ: Tiếp nhận → Rà soát HĐ → Tra cứu luật, Finance, mỗi agent một lượt).

**Why this priority**: Nhóm chat là trải nghiệm mới lớn, nhưng cần story 1 và 2 làm nền. Không có nhóm, cơ chế agent hỏi
agent vẫn dùng được trong chat riêng.

**Independent Test**: Tạo nhóm với 2 giáo viên, 2 học sinh, 1 phụ huynh và 3 agent. Học sinh gửi một câu cần Trợ lý lớp
hỏi Gia sư Toán. Mọi thành viên đều thấy tin của học sinh, lượt của Trợ lý lớp, và lượt riêng của Gia sư Toán có nhãn ai
hỏi.

**Acceptance Scenarios**:

1. **Given** người dùng có quyền tạo nhóm trong lớp, **When** tạo nhóm, **Then** chọn được thành viên người từ danh sách
   lớp (giáo viên kèm môn, học sinh, phụ huynh đã liên kết với học sinh của lớp) và agent đã cài trong lớp.
2. **Given** nhóm đã có thành viên, **When** một người gửi tin, **Then** mọi thành viên thấy tin đó gần như ngay lập tức,
   với tên, vai trò (ví dụ "GV Toán", "Phụ huynh của An") và avatar.
3. **Given** tin có `@Gia sư Toán`, **When** gửi, **Then** Gia sư Toán trả lời; tin không gọi agent nào thì agent điều
   phối của nhóm quyết định có trả lời hay không (tin trò chuyện giữa người với người không bắt agent phải lên tiếng).
4. **Given** agent A đang trả lời trong nhóm và hỏi agent B, **When** B trả lời, **Then** câu trả lời của B hiện thành một
   tin riêng dưới tên B, có nhãn "trả lời cho A", nằm đúng thứ tự trong dòng tin; A sau đó có lượt tổng hợp của mình.
5. **Given** B đã trả lời một câu hỏi của A, **When** có sự cố mạng hoặc tải lại, **Then** câu trả lời đó không xuất hiện
   hai lần.
6. **Given** agent cần hỏi một người đang ở trong nhóm (ví dụ giáo viên Toán), **When** gửi yêu cầu, **Then** thẻ yêu cầu
   hiện ngay trong nhóm, chỉ người được hỏi bấm trả lời được, những người khác thấy trạng thái.
7. **Given** người quản lý nhóm, **When** thêm hoặc bớt thành viên, **Then** thành viên mới chỉ thấy tin từ lúc được thêm
   (trừ khi người quản lý chọn cho xem lịch sử), thành viên bị bớt không xem được tin mới.

---

### User Story 5 - Học sinh, phụ huynh cũng tạo được agent (Priority: P2)

Học sinh tạo agent "Bạn ôn từ vựng tiếng Anh" cho riêng mình: đặt tên, mô tả, hướng dẫn, chọn công cụ trong danh sách cho
phép với học sinh. Phụ huynh tạo agent "Nhắc lịch học của con". Giáo viên tạo agent như hiện nay và chọn được agent của
mình được giao việc cho agent nào. Agent học sinh và phụ huynh tạo dùng được ngay trong không gian cá nhân của người tạo,
nhưng muốn đưa vào lớp, nhóm hoặc chia sẻ thì phải qua kiểm định và được giáo viên của lớp cho phép.

**Why this priority**: Người dùng yêu cầu rõ, nhưng phần lớn giá trị của feature đến từ phối hợp (story 1–4). Trình tạo
agent đã có sẵn cho giáo viên nên story này chủ yếu là mở quyền và thêm hàng rào an toàn.

**Independent Test**: Đăng nhập học sinh demo, tạo agent, thử trong sandbox, chat riêng với nó. Thử thêm agent đó vào nhóm
lớp: hệ thống báo cần kiểm định và giáo viên duyệt.

**Acceptance Scenarios**:

1. **Given** học sinh hoặc phụ huynh đăng nhập, **When** mở trình tạo agent, **Then** tạo được agent với các trường như
   giáo viên, trừ các công cụ không dành cho vai trò đó.
2. **Given** agent vừa tạo, **When** người tạo chat riêng với nó, **Then** agent chạy với mọi lớp an toàn của nền tảng
   (sàng lọc đầu vào, kiểm duyệt đầu ra, quy tắc nền tảng) mà hướng dẫn của người tạo không tắt được.
3. **Given** học sinh tạo agent, **When** học sinh muốn agent đó hỏi agent khác, **Then** chỉ chọn được trong các agent
   học sinh đó đang dùng được.
4. **Given** agent do học sinh hoặc phụ huynh tạo, **When** người tạo muốn đưa vào lớp, nhóm hoặc chia sẻ, **Then** agent
   phải qua kiểm định tự động và giáo viên của lớp phải cho phép.
5. **Given** học sinh dưới sự đồng ý của phụ huynh, **When** phụ huynh chưa đồng ý cho con dùng agent, **Then** học sinh
   cũng không tạo hay dùng được agent cá nhân (giữ cổng đồng ý hiện có).

---

### User Story 6 - Theo dõi hoạt động phối hợp (Priority: P3)

Giáo viên (với lớp của mình), chủ agent (với agent của mình) và admin xem được nhật ký hoạt động: ai đã hỏi ai, lúc nào,
lần nào bị chặn vì thiếu quyền, yêu cầu gửi người nào đang chờ, đã trả lời hay hết hạn (tương ứng trang Activity của
OpenBot).

**Why this priority**: Cần cho truy vết và demo, nhưng không chặn trải nghiệm chính.

**Independent Test**: Sau khi chạy các ca ở story 1–3, mở nhật ký của lớp và thấy đủ các lần giao việc, lần bị chặn và
yêu cầu gửi người.

**Acceptance Scenarios**:

1. **Given** đã có lượt giao việc trong lớp, **When** giáo viên mở nhật ký lớp, **Then** thấy mỗi lần giao việc: agent
   hỏi, agent được hỏi, hội thoại, thời gian, kết quả (đã trả lời, lỗi, bị chặn).
2. **Given** học sinh hoặc phụ huynh, **When** mở nhật ký, **Then** chỉ thấy hoạt động trong hội thoại của chính mình.

---

### User Story 7 - Agent hỏi lại người dùng và xin xác nhận trước việc quan trọng (Priority: P2)

Học sinh gửi "làm cho em đề ôn tập". Thay vì đoán, agent chính hỏi lại **một lần**, tối đa 3 câu, có sẵn lựa chọn để bấm
(môn nào, bao nhiêu câu, mức độ) và nút "Cứ làm luôn". Học sinh trả lời, agent làm tiếp (có thể hỏi các agent khác) mà
không bắt học sinh nhắc lại yêu cầu. Trước khi làm một việc có tác dụng ra ngoài cuộc trò chuyện (ví dụ gửi yêu cầu cho
giáo viên ở story 3), nền tảng luôn dừng lại cho người dùng xem trước và bấm "Đồng ý" hoặc "Không".

**Why this priority**: Câu hỏi phức tạp thường thiếu thông tin. Hỏi agent khác khi chưa rõ yêu cầu chỉ làm tốn thời gian.
Xác nhận là hàng rào bắt buộc cho story 3. Story này dùng chung cơ chế "dừng chờ người" với story 3 nên xếp P2.

**Independent Test**: Gửi "làm đề ôn tập cho em" và "giải giúp em bước đầu của 2x + 3 = 7". Câu đầu nhận đúng một lần hỏi
lại (≤ 3 câu, có lựa chọn); câu sau được trả lời ngay. Gửi một lời xin nộp muộn: yêu cầu chỉ tới giáo viên sau khi học sinh
bấm "Đồng ý".

**Acceptance Scenarios**:

1. **Given** yêu cầu thiếu thông tin làm thay đổi đáng kể kết quả, **When** agent phân tích, **Then** agent hỏi lại đúng
   một lần, gồm 1–3 câu hỏi, câu nào có thể thì kèm lựa chọn, và có nút "Cứ làm luôn".
2. **Given** đang chờ người dùng trả lời câu hỏi lại, **When** người dùng trả lời hoặc bấm "Cứ làm luôn", **Then** agent làm
   tiếp yêu cầu ban đầu; nếu bấm "Cứ làm luôn" thì kết quả ghi rõ các giả định.
3. **Given** đang chờ trả lời, **When** người dùng gửi một yêu cầu không liên quan, **Then** câu hỏi đang chờ bị huỷ và yêu
   cầu mới được xử lý bình thường.
4. **Given** lượt này đã hỏi lại một lần, **When** phát sinh câu hỏi mới (kể cả do agent được hỏi đề nghị), **Then** không
   hỏi lần thứ hai mà tự giả định và nêu giả định.
5. **Given** agent sắp làm một việc được đánh dấu "cần xác nhận", **When** tới bước đó, **Then** nền tảng dừng lại, trình
   bày việc sắp làm và đối tượng chịu tác động, và việc đó chưa chạy cho tới khi người dùng bấm "Đồng ý".
6. **Given** người dùng bấm "Không", hoặc xác nhận đã quá hạn, **When** agent làm tiếp, **Then** việc đó không chạy và câu
   trả lời cuối nói rõ việc đó chưa được thực hiện.

---

### Edge Cases

- **Vòng lặp giao việc.** A hỏi B, B hỏi lại A (hoặc A → B → C → A). Nền tảng chặn mọi lần hỏi tới một agent đã có mặt
  trong chuỗi hiện tại.
- **Bùng nổ giao việc.** Agent hỏi quá nhiều agent hoặc quá nhiều lần. Chạm giới hạn của lượt thì nền tảng dừng giao
  thêm, agent phải tổng hợp từ những gì đã có.
- **Agent được hỏi bị gỡ khỏi lớp hoặc bị tắt** trong lúc đang chờ. Câu hỏi đó kết thúc ở trạng thái "Không trả lời
  được"; agent chính tổng hợp phần còn lại.
- **Người nhận yêu cầu rời lớp, bị gỡ liên kết phụ huynh hoặc bị khoá tài khoản** trước khi trả lời. Yêu cầu bị huỷ, agent
  báo cho người gửi.
- **Lớp có hai giáo viên cùng môn.** Agent đề xuất người nhận, học sinh chọn khi xem trước. Nếu lớp không có giáo viên
  đúng môn thì đề xuất giáo viên chủ nhiệm.
- **Học sinh chưa có phụ huynh liên kết** mà xin phép phụ huynh. Agent báo không có người nhận và gợi ý hỏi giáo viên.
- **Câu trả lời của người lớn chứa thông tin cá nhân hoặc vi phạm an toàn.** Câu trả lời đi qua bước ẩn thông tin cá nhân
  và kiểm duyệt như mọi tin nhắn trước khi tới agent và học sinh.
- **Nội dung yêu cầu gửi người lớn vi phạm an toàn** (ví dụ học sinh nhờ agent viết lời xúc phạm giáo viên). Yêu cầu không
  được gửi; agent báo lý do.
- **Dấu hiệu tự làm hại trong tin nhắn**, ở chat riêng hay nhóm. Không giao việc cho agent nào; đi thẳng luồng hỗ trợ an
  toàn như hiện nay. Trong nhóm, phản hồi hỗ trợ chỉ gửi riêng cho người nhắn, và giáo viên chủ nhiệm nhận cảnh báo theo
  cơ chế hiện có.
- **Hai người trong nhóm cùng gọi agent một lúc.** Các lượt được xử lý lần lượt theo thứ tự đến; tin của người không bị
  chặn gửi trong lúc agent đang trả lời.
- **Agent được hỏi trả lời sau khi agent chính đã viết câu trả lời cuối** (do chạm giới hạn thời gian). Câu trả lời muộn
  được lưu vào thanh "Đã hỏi" hoặc nhật ký nhưng không mở lại lượt.
- **Kết quả cuối bị kiểm duyệt đầu ra chặn.** Nội dung trong các thanh "Đã hỏi" của lượt đó cũng bị ẩn, để không lấy được
  nội dung bị chặn qua đường vòng.
- **Câu trả lời của agent được hỏi không qua kiểm duyệt** (ví dụ chứa đáp án hoàn chỉnh trong lớp cấm đưa đáp án). Thanh
  "Đã hỏi" hoặc lượt riêng trong nhóm chỉ hiện "Nội dung đã được ẩn"; agent chính vẫn nhận nội dung để tổng hợp theo
  đúng chính sách.
- **Chế độ không có người thật** (kiểm định agent, bộ đánh giá, sandbox). Yêu cầu gửi người được coi là "Hết hạn" ngay;
  giao việc cho agent vẫn chạy như thật.
- **Câu trả lời cho câu hỏi lại hoặc xác nhận vi phạm an toàn.** Câu trả lời là tin nhắn mới: đi qua cổng đồng ý, ẩn thông
  tin cá nhân và sàng lọc như mọi tin khác. Bị chặn thì yêu cầu đang chờ cũng bị huỷ.
- **Người dùng rời đi giữa chừng** (đóng trang, mất mạng). Các lần giao việc đang chạy dừng lại; không hành động có tác
  dụng ra ngoài nào chạy sau khi người dùng đã rời đi. Yêu cầu gửi người đã gửi trước đó vẫn chờ bình thường.
- **Giáo viên tắt chế độ phối hợp của lớp** khi có lượt đang chờ. Lượt đang chờ hỏi lại bị huỷ, tin tiếp theo đi đường một
  agent; yêu cầu gửi người đã gửi vẫn giữ.
- **Bước phân tích lỗi hoặc trả về kết quả không dùng được.** Quay về đường một agent trả lời như hiện nay thay vì báo lỗi.
- **Người dùng gửi tin mới khi lượt trước còn chạy** trong chat riêng. Giữ hành vi hiện tại (không cho gửi khi đang có câu
  trả lời chạy).
- **Phụ huynh rút đồng ý** khi học sinh đang có yêu cầu chờ hoặc đang trong nhóm. Học sinh không dùng agent được nữa; yêu
  cầu đang chờ bị huỷ; học sinh vẫn đọc và nhắn với người trong nhóm nếu chính sách lớp cho phép.

## Requirements *(mandatory)*

### Functional Requirements

**Tạo agent**

- **FR-001**: Học sinh, giáo viên và phụ huynh MUST tạo được agent bằng trình tạo agent hiện có (tên, mô tả, avatar,
  hướng dẫn, công cụ, phiên bản, sandbox thử).
- **FR-002**: Danh sách công cụ chọn được khi tạo agent MUST lọc theo vai trò của người tạo; vai trò học sinh và phụ
  huynh MUST không chọn được công cụ chỉ dành cho giáo viên.
- **FR-003**: Agent do học sinh hoặc phụ huynh tạo MUST dùng được ngay trong không gian cá nhân của chính người tạo, và
  MUST chỉ được đưa vào lớp, nhóm hoặc chia sẻ cho người khác sau khi qua kiểm định tự động và được giáo viên của lớp đó
  cho phép.
- **FR-004**: Mọi agent, bất kể ai tạo, MUST chạy dưới quy tắc nền tảng, sàng lọc đầu vào, kiểm duyệt đầu ra và chính
  sách lớp; hướng dẫn của người tạo MUST không ghi đè được các lớp này.
- **FR-005**: Học sinh MUST chỉ tạo và dùng agent cá nhân khi phụ huynh đã đồng ý (theo cổng đồng ý hiện có).

**Quyền giao việc giữa các agent**

- **FR-006**: Mỗi agent MUST có danh sách "được giao việc cho" do người tạo agent đặt; giáo viên MUST thu hẹp được danh
  sách này trong phạm vi lớp của mình (không mở rộng quá danh sách của người tạo).
- **FR-007**: Nền tảng MUST chỉ chuyển câu hỏi từ agent A tới agent B khi đồng thời: B nằm trong danh sách của A (sau khi
  áp dụng thu hẹp của lớp), B đang dùng được trong lớp hoặc không gian của hội thoại, B dành cho vai trò của người dùng
  gốc, và B chưa có mặt trong chuỗi giao việc hiện tại.
- **FR-008**: Lần giao việc bị chặn MUST trả cho agent hỏi một thông báo từ chối có lý do để agent giải thích với người
  dùng, và MUST được ghi nhật ký.
- **FR-009**: Yêu cầu giao việc tới agent cụ thể nằm trong nội dung tin nhắn của người dùng MUST không vượt được FR-007.
- **FR-010**: Agent được hỏi MUST chạy với hướng dẫn, công cụ và giới hạn dữ liệu của chính nó, theo chính sách lớp và vai
  trò của **người dùng gốc**; MUST không thừa hưởng quyền của agent hỏi.
- **FR-011**: Agent được hỏi MUST chỉ nhận thông tin cần cho câu hỏi (câu hỏi của agent hỏi, phần nội dung người dùng mà
  agent hỏi chuyển kèm), không nhận toàn bộ lịch sử hội thoại.

**Thực hiện giao việc**

- **FR-012**: Agent MUST hỏi được một hoặc nhiều agent trong một lượt; các câu hỏi không phụ thuộc nhau SHOULD chạy song
  song.
- **FR-013**: Chuỗi giao việc MUST có độ sâu tối đa cấu hình được (mặc định 2: người dùng → agent chính → agent được hỏi
  → agent được hỏi tiếp). Mỗi lượt MUST có giới hạn cấu hình được về tổng số lần giao việc (mặc định 6), số agent tham gia
  (mặc định 4) và tổng thời gian (mặc định 120 giây). Chạm giới hạn thì nền tảng dừng giao thêm và agent chính tổng hợp
  từ những gì đã có.
- **FR-014**: Mỗi câu hỏi tới một agent MUST nhận tối đa một câu trả lời; gửi lại do lỗi mạng hoặc tải lại trang MUST
  không tạo câu trả lời thứ hai.
- **FR-015**: Khi agent được hỏi lỗi hoặc quá thời gian, nền tảng MUST báo cho agent hỏi bằng trạng thái "không trả lời
  được" kèm lý do thân thiện, MUST không hiện mã lỗi kỹ thuật cho người dùng, và agent hỏi MUST nói rõ phần nào chưa kiểm
  chứng được trong câu trả lời cuối.
- **FR-016**: Agent chính MUST viết câu trả lời cuối của lượt, ghi tên các agent đã đóng góp và giữ trích dẫn nguồn từ
  câu trả lời của các agent đó.
- **FR-017**: Câu hỏi đơn giản agent tự làm được MUST không kích hoạt giao việc, và thời gian trả lời MUST không chậm hơn
  hiện nay một cách đáng kể (xem SC-001).

**Hiển thị trong chat riêng**

- **FR-018**: Mỗi lần agent hỏi agent khác trong chat riêng MUST hiện một thanh "Đã hỏi <tên agent>" có avatar và trạng
  thái (đang hỏi, đã trả lời, không trả lời được, bị chặn), cập nhật theo thời gian thực.
- **FR-019**: Thanh "Đã hỏi" MUST mở và đóng được; khi mở hiển thị câu hỏi đã gửi và câu trả lời nhận về. Khi có câu trả
  lời cuối, các thanh MUST mặc định đóng.
- **FR-020**: Lần hỏi tiếp ở tầng sâu hơn (agent được hỏi hỏi tiếp agent khác) MUST hiện lồng bên trong thanh của agent
  tầng trên.
- **FR-021**: Các thanh "Đã hỏi" MUST được lưu cùng câu trả lời và hiển thị lại khi mở lại hội thoại.

**Hiển thị trong nhóm chat**

- **FR-022**: Trong nhóm, câu trả lời của mỗi agent được hỏi MUST hiện thành một tin riêng dưới tên và avatar của agent
  đó, có nhãn "trả lời cho <agent hỏi>", đúng thứ tự thời gian trong dòng tin, và mọi thành viên đều thấy.
- **FR-023**: Câu hỏi agent hỏi gửi cho agent được hỏi MUST hiển thị gọn trong nhóm (ví dụ "Gia sư Toán đã hỏi Ôn tập tài
  liệu", mở ra xem được nội dung), để thành viên hiểu vì sao agent kia lên tiếng.

**Hỏi người (xin duyệt, xin câu trả lời)**

- **FR-024**: Agent MUST tạo được yêu cầu gửi một người thật, gồm: người nhận, nội dung, loại yêu cầu (xin duyệt với các
  lựa chọn Đồng ý / Sửa / Từ chối, hoặc xin câu trả lời tự do, hoặc chọn một trong các lựa chọn agent đưa ra), và hạn chờ.
- **FR-025**: Người nhận MUST chỉ thuộc nhóm người nền tảng cho phép với người dùng gốc: giáo viên của lớp (có môn), giáo
  viên chủ nhiệm, phụ huynh đã liên kết của chính học sinh đó; với người dùng là giáo viên hoặc phụ huynh thì là thành
  viên cùng lớp hoặc cùng nhóm. Agent và nội dung tin nhắn MUST không vượt được giới hạn này.
- **FR-026**: Khi người dùng gốc là học sinh, yêu cầu MUST được học sinh xem trước (nội dung, người nhận) và bấm gửi;
  agent MUST không tự gửi yêu cầu khi học sinh chưa đồng ý.
- **FR-027**: Nội dung yêu cầu MUST qua kiểm duyệt nội dung và bước ẩn thông tin cá nhân trước khi gửi; nội dung không qua
  MUST không được gửi và agent được báo lý do.
- **FR-028**: Người nhận MUST thấy yêu cầu trong **hộp yêu cầu** của mình, có thông báo khi có yêu cầu mới; nếu yêu cầu tạo
  trong nhóm mà người nhận là thành viên, thẻ yêu cầu MUST hiện cả trong nhóm và chỉ người nhận bấm trả lời được.
- **FR-029**: Câu trả lời của người nhận MUST quay về đúng lượt và đúng hội thoại gốc đã tạo yêu cầu, kể cả khi yêu cầu do
  một agent ở tầng sâu trong chuỗi giao việc tạo ra; agent MUST làm tiếp từ chỗ đã dừng và báo kết quả cho người dùng gốc.
- **FR-030**: Mỗi yêu cầu MUST nhận tối đa một câu trả lời; sau khi trả lời, hết hạn hoặc bị huỷ, các lựa chọn MUST không
  bấm được nữa.
- **FR-031**: Yêu cầu đang chờ MUST hết hạn sau thời gian cấu hình được (mặc định 72 giờ); người dùng gốc MUST huỷ được yêu
  cầu đang chờ; khi hết hạn hoặc bị huỷ, agent MUST báo cho người dùng gốc.
- **FR-032**: Trong lúc chờ người trả lời, người dùng gốc MUST chat tiếp bình thường, và hội thoại MUST hiện trạng thái
  "Đang chờ <tên người> trả lời".
- **FR-033**: Câu trả lời của người nhận MUST đi qua bước ẩn thông tin cá nhân và kiểm duyệt như mọi tin nhắn của người.
- **FR-034**: Yêu cầu gửi người MUST không tự thực hiện hành động nào có tác dụng ra ngoài; nếu sau khi được duyệt cần chạy
  công cụ có tác dụng ra ngoài thì vẫn theo cơ chế xác nhận hành động (FR-057 đến FR-061).

**Nhóm chat**

- **FR-035**: Mỗi nhóm chat MUST thuộc một lớp. Thành viên người MUST lấy từ lớp đó: giáo viên (hiển thị môn), học sinh,
  phụ huynh đã liên kết với học sinh của lớp. Thành viên agent MUST là agent đã cài và dùng được trong lớp.
- **FR-036**: Giáo viên của lớp MUST tạo được nhóm. Học sinh và phụ huynh MUST tạo được nhóm khi giáo viên bật quyền này
  trong chính sách lớp (mặc định tắt).
- **FR-037**: Mọi nhóm có học sinh MUST có ít nhất một giáo viên của lớp là thành viên, và giáo viên chủ nhiệm MUST xem
  được mọi nhóm của lớp.
- **FR-038**: Người tạo nhóm và giáo viên trong nhóm MUST thêm, bớt thành viên (người và agent), đặt tên nhóm và chọn
  agent điều phối của nhóm (mặc định là trợ lý lớp nếu có).
- **FR-039**: Tin nhắn trong nhóm MUST hiện cho mọi thành viên gần như ngay lập tức, kèm tên, vai trò và avatar người gửi.
- **FR-040**: Trong nhóm, agent MUST trả lời khi được `@mention`; tin không gọi agent nào MUST do agent điều phối quyết
  định có trả lời hay không, và tin trò chuyện giữa người với người MUST không bắt agent phải lên tiếng.
- **FR-041**: Agent trả lời trong nhóm MUST theo vai trò và chính sách của **người gửi tin gọi nó** (ví dụ câu hỏi của học
  sinh vẫn bị chính sách "không đưa đáp án" áp dụng dù nhóm có giáo viên).
- **FR-042**: Tin nhắn của học sinh trong nhóm MUST qua cổng đồng ý của phụ huynh, ẩn thông tin cá nhân và sàng lọc an toàn
  như chat riêng; tin nhắn của mọi thành viên MUST qua kiểm duyệt nội dung.
- **FR-043**: Thành viên mới MUST chỉ thấy tin từ lúc được thêm, trừ khi người thêm chọn cho xem lịch sử; thành viên bị bớt
  MUST không nhận và không xem được tin mới.
- **FR-044**: Ngữ cảnh agent dùng ở các lượt sau trong nhóm MUST gồm tin nhắn của nhóm mà người gọi agent được xem, không
  gồm nội dung đã bị ẩn.

**Chat riêng**

- **FR-045**: Người dùng MUST chat riêng được với một agent bất kỳ họ dùng được (cài vào lớp, cài cá nhân, hoặc agent tự
  tạo), như hiện nay, và cơ chế hỏi agent khác (FR-012 đến FR-021) và hỏi người (FR-024 đến FR-034) MUST áp dụng trong
  chat riêng.

**Nhật ký và đo lường**

- **FR-046**: Nền tảng MUST ghi cho mỗi lần giao việc: agent hỏi, agent được hỏi, tầng trong chuỗi, hội thoại, thời gian,
  trạng thái (đã trả lời, lỗi, quá giờ, bị chặn và lý do) và lượng sử dụng mô hình, để báo cáo chi phí hiện có tiếp tục
  đúng theo từng agent.
- **FR-047**: Nền tảng MUST ghi cho mỗi yêu cầu gửi người: người gửi gốc, agent tạo, người nhận, nội dung, các mốc thời gian,
  kết quả (đã trả lời, hết hạn, huỷ) và câu trả lời.
- **FR-048**: Giáo viên MUST xem được nhật ký của lớp mình; chủ agent MUST xem được nhật ký giao việc của agent mình (không
  kèm nội dung hội thoại của người khác); học sinh và phụ huynh MUST chỉ xem được nhật ký của hội thoại của chính mình.
- **FR-049**: Dự án MUST có bộ kịch bản kiểm thử tương đương bộ test OpenBot (luồng đầy đủ nhiều tầng, agent dữ liệu từ chối
  ngoài phạm vi, agent không gửi ra ngoài, agent không bịa, quyền giao việc bị chặn ở tầng hệ thống) dựng trên agent và dữ
  liệu demo của trường học, chạy được và báo được các chỉ số ở Success Criteria.

**Hỏi lại người dùng** (ràng buộc mang từ spec 002)

- **FR-051**: Agent chính MUST chỉ hỏi lại người dùng khi thiếu thông tin làm thay đổi đáng kể kết quả; thông tin thiếu
  nhưng ít ảnh hưởng thì MUST tự giả định và nêu giả định trong câu trả lời cuối.
- **FR-052**: Mỗi lượt MUST có tối đa **1 lần** hỏi lại người dùng, mỗi lần tối đa **3 câu hỏi**, tính chung cho cả chuỗi
  giao việc (agent được hỏi muốn hỏi người dùng thì báo lên agent chính, không tự hỏi). Hai giới hạn MUST chỉnh được trong
  cấu hình.
- **FR-053**: Mỗi câu hỏi lại SHOULD kèm lựa chọn để bấm; người dùng MUST luôn gõ trả lời tự do được; mỗi lần hỏi lại MUST có
  lựa chọn "Cứ làm luôn".
- **FR-054**: Khi người dùng trả lời, agent MUST làm tiếp yêu cầu ban đầu từ chỗ đã dừng, giữ các câu trả lời của agent
  được hỏi đã có, không bắt người dùng nhắc lại.
- **FR-055**: Tin nhắn không phải câu trả lời cho câu hỏi đang chờ MUST huỷ lượt đang chờ và được xử lý như tin mới.
- **FR-056**: Lượt đang chờ người dùng trả lời MUST hết hạn sau thời gian cấu hình được (mặc định 24 giờ) và MUST làm tiếp
  được sau khi tải lại trang hoặc mở lại hội thoại trong thời hạn đó.

**Xác nhận hành động** (ràng buộc mang từ spec 002)

- **FR-057**: Công cụ và hành động MUST khai báo được thuộc tính "cần xác nhận". Nền tảng MUST không chạy hành động có thuộc
  tính này khi người dùng chưa xác nhận rõ ràng cho đúng lần đó, bất kể agent hay nội dung hội thoại nói gì. Việc gửi yêu
  cầu cho người khác (FR-024, FR-026) thuộc loại này.
- **FR-058**: Yêu cầu xác nhận MUST trình bày ngắn gọn việc sắp làm, nội dung xem trước và đối tượng chịu tác động, với hai
  lựa chọn "Đồng ý" và "Không".
- **FR-059**: Xác nhận hành động MUST không tính vào giới hạn hỏi lại ở FR-052.
- **FR-060**: Hành động được xác nhận MUST chạy đúng tham số đã trình bày và chạy tối đa một lần (bấm lại, tải lại không tạo
  bản thứ hai). Hành động bị từ chối, hết hạn hoặc bị huỷ MUST không chạy, và câu trả lời cuối MUST nói rõ.
- **FR-061**: Câu hỏi lại, yêu cầu xác nhận và thẻ yêu cầu gửi người MUST hiển thị như tin nhắn của hệ thống trong hội
  thoại, kèm lựa chọn bấm được; sau khi đã trả lời, các lựa chọn MUST không bấm lại được.

**Chế độ phối hợp theo lớp** (ràng buộc mang từ spec 002)

- **FR-062**: Giáo viên MUST bật/tắt được chế độ phối hợp (agent hỏi agent khác và hỏi lại người dùng) cho lớp của mình
  trong chính sách lớp, mặc định **bật**. Khi tắt, mọi tin trong lớp đi đường một agent; xác nhận hành động (FR-057) và
  quyền gửi yêu cầu cho giáo viên, phụ huynh vẫn áp dụng. Không gian cá nhân luôn bật.

**An toàn và độ bền** (ràng buộc mang từ spec 002)

- **FR-063**: Cổng đồng ý của phụ huynh, ẩn thông tin cá nhân và sàng lọc an toàn MUST chạy trước bước phân tích ở mọi tin
  nhắn, kể cả tin trả lời câu hỏi lại, xác nhận, hoặc câu trả lời của giáo viên, phụ huynh.
- **FR-064**: Khi sàng lọc chặn tin hoặc phát hiện dấu hiệu cần hỗ trợ an toàn, nền tảng MUST không giao việc, không hỏi
  lại, và MUST xử lý như hiện nay.
- **FR-065**: Không nội dung nào chưa qua kiểm duyệt đầu ra MUST hiển thị cho người dùng, kể cả câu trả lời của agent được
  hỏi trong thanh "Đã hỏi" và trong lượt riêng ở nhóm. Kiểm duyệt MUST theo vai trò và chính sách của người xem (gồm chính
  sách không đưa đáp án cho học sinh); nội dung bị ẩn MUST ghi thành sự kiện an toàn kèm agent liên quan.
- **FR-066**: Khi người dùng rời đi giữa chừng, các lần giao việc đang chạy MUST dừng, và MUST không có hành động có tác dụng
  ra ngoài nào chạy sau đó.
- **FR-067**: Ngữ cảnh agent nhớ ở các lượt sau MUST gồm yêu cầu của người dùng, câu hỏi lại và câu trả lời, câu trả lời của
  người được hỏi, và câu trả lời cuối; MUST không gồm nội dung trung gian giữa các agent.
- **FR-068**: Báo cáo sử dụng MUST tách được lượng dùng của lượt một agent và lượt có phối hợp; không có hạn mức số lượt
  phối hợp theo người dùng, chi phí được kiểm soát bằng theo dõi và giới hạn trong từng lượt (FR-013).

**Vận hành**

- **FR-050**: Cách chạy local chính thức (`dev.ps1`) MUST dựng được đủ những gì feature cần (thay đổi dữ liệu, cấu hình mới,
  agent demo có danh sách giao việc, nhóm demo) bằng một lệnh, theo nguyên tắc III của hiến pháp.

### Key Entities *(include if feature involves data)*

- **Agent (đã có)**: Bổ sung người tạo có thể là học sinh hoặc phụ huynh, phạm vi dùng (cá nhân, đã được duyệt vào lớp),
  và danh sách "được giao việc cho" (thuộc phiên bản của agent).
- **Thu hẹp giao việc theo lớp**: Với một agent đã cài trong lớp, danh sách agent mà giáo viên cho phép nó hỏi trong lớp
  đó (tập con của danh sách của người tạo).
- **Hội thoại (đã có)**: Bổ sung loại: chat riêng hoặc nhóm. Nhóm có tên, lớp, người tạo, agent điều phối.
- **Thành viên nhóm**: Một người hoặc một agent trong nhóm, kèm vai trò hiển thị (GV Toán, học sinh, phụ huynh của …),
  thời điểm vào, quyền quản lý, được xem lịch sử hay không.
- **Tin nhắn (đã có)**: Bổ sung người gửi (người hoặc agent), lượt và lần giao việc tạo ra nó, nhãn "trả lời cho".
- **Lần giao việc**: Một câu hỏi từ agent này tới agent khác trong một lượt: agent hỏi, agent được hỏi, lần giao việc cha
  (để biết tầng), câu hỏi, câu trả lời, trạng thái, kết quả kiểm duyệt khi hiển thị, thời gian.
- **Yêu cầu gửi người**: Câu hỏi hoặc xin duyệt agent gửi cho một người: người dùng gốc, hội thoại và lượt gốc, lần giao
  việc tạo ra nó (nếu có), người nhận, loại, nội dung, lựa chọn, hạn chờ, trạng thái, câu trả lời và người trả lời.
- **Hộp yêu cầu**: Danh sách yêu cầu gửi tới một người, lọc được theo trạng thái và lớp.
- **Chính sách lớp (đã có)**: Bổ sung: học sinh và phụ huynh có được tạo nhóm không, có được đưa agent tự tạo vào lớp không.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Với câu hỏi không cần agent khác, thời gian tới chữ đầu tiên (trung vị) tăng không quá 10% so với trước
  feature, đo trên cùng bộ câu hỏi.
- **SC-002**: 100% lần giao việc tới agent ngoài danh sách được phép (kể cả do người dùng yêu cầu trong tin nhắn) bị chặn,
  kiểm tra bằng bộ ca cố tình lách quyền.
- **SC-003**: 0 dữ liệu ngoài phạm vi bị lộ qua agent được hỏi trên bộ ca tương đương OpenBot Test 2 (ví dụ điểm của học
  sinh khác).
- **SC-004**: 100% câu trả lời của người nhận quay về đúng hội thoại gốc và agent làm tiếp được, kể cả khi yêu cầu do agent
  tầng 2 tạo.
- **SC-005**: 0 câu trả lời trùng lặp (một câu hỏi tới agent nhận hai câu trả lời, hoặc một yêu cầu gửi người nhận hai câu
  trả lời) trên bộ kịch bản kiểm thử có chèn lỗi mạng và tải lại trang.
- **SC-006**: 0 mã lỗi kỹ thuật hiển thị cho người dùng cuối khi một agent được hỏi lỗi; trong 100% trường hợp đó, câu trả
  lời cuối nói rõ phần nào chưa kiểm chứng được.
- **SC-007**: Trên bộ kịch bản luồng nhiều agent, ít nhất 85% lượt có đúng tập agent được hỏi như kỳ vọng (không thiếu agent
  cần thiết, thừa tối đa một).
- **SC-008**: Trong nhóm, tin nhắn hiện ở thiết bị các thành viên khác trong vòng 2 giây ở điều kiện chạy local.
- **SC-009**: Trong buổi thử với người dùng mẫu, ít nhất 4/5 người trả lời đúng "agent nào đã được hỏi và nó trả lời gì" chỉ
  bằng cách nhìn giao diện, ở cả chat riêng và nhóm.
- **SC-010**: Một học sinh mới tạo được agent cá nhân đầu tiên và chat với nó trong vòng 5 phút mà không cần hướng dẫn.
- **SC-011**: Một giáo viên trả lời được một yêu cầu xin duyệt trong hộp yêu cầu với không quá 2 thao tác sau khi mở.
- **SC-012**: Tỉ lệ nội dung vi phạm lọt ra người dùng trên bộ red-team hiện có cộng các ca lách qua giao việc và qua nhóm
  không cao hơn so với khi chỉ một agent trả lời.
- **SC-013**: Trên bộ kịch bản, tỉ lệ hỏi thừa (hỏi lại với yêu cầu đã đủ rõ) không quá 10% và tỉ lệ hỏi đúng lúc (hỏi lại
  với yêu cầu thật sự mơ hồ) đạt ít nhất 80%; 100% lượt tuân thủ giới hạn 1 lần hỏi lại, 3 câu mỗi lần.
- **SC-014**: 0 hành động "cần xác nhận" (kể cả gửi yêu cầu cho người khác) chạy khi chưa có xác nhận rõ ràng, kiểm tra bằng
  các ca cố tình bảo agent bỏ qua xác nhận.

## Assumptions

- Feature được triển khai trên `main`, mở rộng runtime agent, orchestrator, guard, kiểm định và trình tạo agent đang có
  trên `main`. Không dùng, không chờ và không hợp nhất với nhánh `feat/dify-runtime`.
- Các ràng buộc lấy từ spec 002 (nhánh `feat/dify-runtime`) đã được viết lại thành yêu cầu của spec này (FR-051 đến
  FR-068, SC-013, SC-014); spec 002 không phải phụ thuộc. Phần không mang sang: bộ 5 công cụ giáo viên có tác dụng ra ngoài
  của 002 (lưu tài liệu lớp, đổi ghi chú agent, cài agent, đăng thông báo, giao bài luyện). Trong spec này, hành động "cần
  xác nhận" duy nhất là gửi yêu cầu cho người khác; công cụ khác sẽ dùng chung cơ chế khi được thêm sau.
- Danh sách "được giao việc cho" để trống là mặc định khi tạo agent mới (an toàn mặc định, giống OpenBot). Agent nền tảng
  mẫu được seed sẵn danh sách hợp lý (ví dụ trợ lý lớp được hỏi các gia sư môn; gia sư môn được hỏi agent tài liệu và agent
  tạo đề).
- Agent do học sinh và phụ huynh tạo mặc định chỉ dùng cá nhân. Đưa vào lớp cần qua kiểm định tự động hiện có và giáo
  viên cho phép; chính sách lớp quyết định có cho đưa vào hay không (mặc định cho phép xin duyệt).
- Nhóm chat luôn gắn với một lớp. Nhóm không thuộc lớp, nhóm liên lớp và nhắn tin riêng giữa hai người (không có agent)
  nằm ngoài phạm vi.
- "Giáo viên các môn" lấy theo môn của giáo viên trong lớp. Nếu dữ liệu lớp hiện chưa ghi môn cho từng giáo viên thành
  viên thì feature bổ sung trường này.
- Thông báo yêu cầu mới chỉ trong ứng dụng (huy hiệu, hộp yêu cầu). Email, SMS, thông báo đẩy nằm ngoài phạm vi.
- Hạn chờ mặc định: yêu cầu gửi người 72 giờ; giới hạn giao việc theo FR-013. Các con số là điểm khởi đầu, chỉnh được.
- Agent tự góp lời trong nhóm khi không được gọi và không do agent điều phối giao (agent "tự chen vào") nằm ngoài phạm vi.
- Dữ liệu và kịch bản kiểm thử dùng dữ liệu demo của trường học, không dùng lại dữ liệu pháp chế trong ví dụ OpenBot; ví
  dụ OpenBot chỉ là mẫu hành vi.
