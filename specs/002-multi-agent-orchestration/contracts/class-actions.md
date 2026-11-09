# Hợp đồng: API cho thông báo lớp và bài luyện (R18)

REST dưới `/api`, xác thực bằng cookie phiên như các API khác. Lỗi quyền trả 403, không thấy lớp trả 404, như
`classes/router.py` hiện tại.

## Thông báo lớp

| Method | Path | Ai | Ghi chú |
|---|---|---|---|
| `GET` | `/classes/{class_id}/announcements` | thành viên lớp, phụ huynh có con trong lớp | lọc theo `audience` của người xem; mới nhất trước; tối đa 50 |
| `POST` | `/classes/{class_id}/announcements` | giáo viên của lớp | đăng trực tiếp trên giao diện (`source="ui"`); cùng kiểm duyệt từ khóa với tool |
| `DELETE` | `/classes/{class_id}/announcements/{id}` | giáo viên của lớp | 204 |

`AnnouncementOut`: `{id, title, body, audience, author_name, source, created_at}`.

## Bài luyện

| Method | Path | Ai | Ghi chú |
|---|---|---|---|
| `GET` | `/classes/{class_id}/assignments` | thành viên lớp, phụ huynh có con trong lớp | mới nhất trước |
| `GET` | `/classes/{class_id}/assignments/{id}` | như trên | `answer_key` chỉ có khi người xem là giáo viên của lớp |
| `DELETE` | `/classes/{class_id}/assignments/{id}` | giáo viên của lớp | 204 |

Không có `POST` trên giao diện trong feature này: bài luyện chỉ được tạo qua tool `assign_practice`.

`AssignmentOut`: `{id, title, instructions, questions, due_at, author_name, source, created_at, answer_key?}`.

## Giao diện

- `ClassDetailPage`: tab mới "Bảng tin" (thông báo + bài luyện), giáo viên có nút xoá; giáo viên đăng được thông báo.
- Trang lớp của học sinh (`StudentClassesPage` / `StudentHomePage`): danh sách thông báo và bài luyện; bài luyện có nút
  "Làm cùng gia sư", mở chat của lớp với tin nhắn soạn sẵn "Mình muốn làm bài luyện “{title}”" kèm các câu hỏi (không
  kèm đáp án).
- Trang phụ huynh: thông báo `parents`/`all` của các lớp có con, và danh sách bài luyện của con.
