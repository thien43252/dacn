<!--
Sync Impact Report
- Version change: (template, chưa ban hành) → 1.0.0
- Modified principles: toàn bộ placeholder được thay bằng nội dung cụ thể
  - [PRINCIPLE_1_NAME] → I. Tài liệu và spec viết bằng tiếng Việt (từ yêu cầu người dùng)
  - [PRINCIPLE_2_NAME] → II. Không tự commit (từ yêu cầu người dùng)
  - [PRINCIPLE_3_NAME] → III. An toàn học sinh là lõi, không được nới lỏng (suy ra từ README/PLAN)
  - [PRINCIPLE_4_NAME] → IV. Kiểm thử chạy được không cần hạ tầng ngoài (suy ra từ README)
  - [PRINCIPLE_5_NAME] → V. Giữ hợp đồng và đo lường được (suy ra từ PLAN-DIFY)
- Added sections: Ràng buộc kỹ thuật; Quy trình phát triển
- Removed sections: không có
- Follow-up TODOs: không có. Nguyên tắc III–V được suy ra từ repo, cần chủ dự án xác nhận.
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
