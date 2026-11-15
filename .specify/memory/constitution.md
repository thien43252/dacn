<!--
Sync Impact Report
- Version change: 1.1.0 → 1.1.1 (PATCH: bỏ thành phần không có trên `main`; không thêm hay bỏ nguyên tắc)
- Modified principles:
  - III. Script `dev.ps1` luôn chạy được bản mới nhất: bỏ Dify khỏi danh sách stack, khỏi các thay đổi
    "ảnh hưởng tới bước chạy" và khỏi phần lý do. Stack trên `main` là Postgres, backend, web.
- Added sections: không có
- Removed sections: không có
- Templates: không cần sửa (plan/spec/tasks template không nhắc Dify)
- Follow-up TODOs:
  - TODO(MISSING_PRINCIPLES) (giữ từ 1.1.0): report của 1.0.0 liệt kê nguyên tắc "An toàn học sinh là lõi",
    "Kiểm thử chạy được không cần hạ tầng ngoài", "Giữ hợp đồng và đo lường được" cùng các mục
    "Ràng buộc kỹ thuật", "Quy trình phát triển", nhưng nội dung chưa từng được ghi vào file. Chủ dự án cần
    xác nhận có khôi phục các nguyên tắc này không.
-->

# EduAgent Hub Constitution

## Core Principles

### I. Tài liệu và spec viết bằng tiếng Việt

- Mọi tài liệu của dự án (README, `docs/`, báo cáo) và mọi sản phẩm Spec Kit (`spec.md`, `plan.md`,
  `tasks.md`, checklist, research, data model, quickstart) MUST viết bằng tiếng Việt.
- Tên định danh trong code, tên file, tên API, khóa cấu hình, thuật ngữ kỹ thuật chuẩn (SSE, MCP,
  pgvector, guard…) và trích dẫn nguyên văn MAY giữ tiếng Anh.

### II. Không tự commit

- Agent (Claude Code, lệnh Spec Kit, hook) MUST NOT chạy `git commit`, `git push`, `git merge`,
  `git rebase`, `git tag` hay thao tác ghi lịch sử git nào khác, trừ khi người dùng yêu cầu rõ ràng
  cho đúng lần đó.
- Thay đổi MUST được để lại trong working tree để người dùng tự xem và tự commit. Agent MAY đề xuất
  commit message.
- Commit message do agent đề xuất MUST viết bằng tiếng Anh (ngoại lệ của nguyên tắc I), theo dạng
  `type(scope): mô tả` của Conventional Commits.
- Hook hoặc extension tự commit (ví dụ `speckit.git.commit`) MUST bị tắt hoặc chỉ ở dạng tùy chọn.

### III. Script `dev.ps1` luôn chạy được bản mới nhất

- `dev.ps1` ở gốc repo là cách chạy local chính thức: một lệnh `.\dev.ps1` MUST dựng được toàn bộ
  stack (Postgres, backend, web) của trạng thái code hiện tại.
- Mọi thay đổi ảnh hưởng tới bước chạy MUST cập nhật `dev.ps1` trong cùng thay đổi đó. "Ảnh hưởng
  tới bước chạy" gồm: thêm, bỏ hoặc đổi service hay container; đổi cổng; thêm biến môi trường bắt
  buộc trong `.env`; thêm bước migration, seed, build hay cài dependency; đổi lệnh khởi động, thư mục,
  endpoint health.
- Khi bước thủ công trong mục "Chạy local" của `README.md` thay đổi, README MUST được cập nhật cùng
  lúc để hai nơi không mâu thuẫn.
- Trước khi coi thay đổi là xong, agent MUST ít nhất kiểm tra cú pháp `dev.ps1` và, nếu hạ tầng có
  sẵn, chạy `.\dev.ps1` để xác nhận; nếu không chạy được thì MUST nói rõ là chưa chạy thử.
- `dev.ps1` MUST giữ được tính chạy lại an toàn (chạy nhiều lần không phá dữ liệu) và báo lỗi rõ ràng
  khi thiếu công cụ, thiếu `.env` hoặc service không lên.
- `tasks.md` của feature có thay đổi thuộc loại trên MUST có task cập nhật `dev.ps1`.

Lý do: dự án có nhiều thành phần chạy riêng (Postgres trong Docker, backend, web) và đồ án cần
demo được bất cứ lúc nào. Script lệch với code là nguyên nhân phổ biến khiến demo hỏng mà test
không phát hiện.

## Governance

- Hiến pháp này có hiệu lực cao hơn mọi quy ước khác của dự án. Lệnh `/speckit-plan` MUST đối chiếu
  plan với các nguyên tắc ở trên (Constitution Check) và ghi rõ mọi ngoại lệ kèm lý do.
- Sửa đổi được thực hiện qua `/speckit-constitution`, kèm Sync Impact Report, và do chủ dự án tự
  commit (nguyên tắc II).
- Phiên bản theo semver: MAJOR khi bỏ hoặc định nghĩa lại nguyên tắc theo cách không tương thích;
  MINOR khi thêm nguyên tắc hoặc mở rộng đáng kể; PATCH khi chỉ sửa câu chữ.

**Version**: 1.1.1 | **Ratified**: 2026-11-06 | **Last Amended**: 2026-11-15
