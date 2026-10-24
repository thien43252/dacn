import type { Role } from "../auth/api";
import type { IconName } from "../components/Icon";
import { matchPath } from "./router";

export interface NavigationItem {
  label: string;
  path: string;
  icon: IconName;
}

export interface RouteMeta {
  /** Pattern understood by `matchPath`, e.g. `/teacher/classes/:classId`. */
  pattern: string;
  title: string;
  eyebrow?: string;
  description: string;
  /** Plan week in which the screen gets real content; shown on the placeholder until then. */
  week: number;
}

/** Sidebar entries. The last path segment doubles as the onboarding guide target (`nav-<segment>`). */
export const navigation: Record<Role, NavigationItem[]> = {
  teacher: [
    { label: "Lớp của tôi", path: "/teacher/classes", icon: "school" },
    { label: "Agent Hub", path: "/teacher/hub", icon: "layers" },
    { label: "Agent của tôi", path: "/teacher/builder", icon: "sparkles" },
    { label: "Nhật ký an toàn", path: "/teacher/audit", icon: "shield" },
  ],
  student: [
    { label: "Trợ lý học tập", path: "/student/home", icon: "home" },
    { label: "Lớp của tôi", path: "/student/classes", icon: "school" },
    { label: "Agent Hub", path: "/student/hub", icon: "layers" },
    { label: "Agent của tôi", path: "/student/agents", icon: "sparkles" },
  ],
  parent: [
    { label: "Con của tôi", path: "/parent/home", icon: "team" },
    { label: "Báo cáo học tập", path: "/parent/reports", icon: "book" },
    { label: "Agent Hub", path: "/parent/hub", icon: "layers" },
    { label: "Đồng ý & quyền riêng tư", path: "/parent/consent", icon: "lock" },
  ],
  admin: [
    { label: "Kiểm định agent", path: "/admin/certification", icon: "shield" },
    { label: "Agent nền tảng", path: "/admin/agents", icon: "layers" },
    { label: "Tool & MCP", path: "/admin/tools", icon: "layout" },
    { label: "Nhật ký hệ thống", path: "/admin/audit", icon: "history" },
  ],
};

export const routes: RouteMeta[] = [
  { pattern: "/teacher/classes", title: "Lớp của tôi", description: "Tạo lớp, gửi mã mời cho học sinh và phụ huynh.", week: 3 },
  { pattern: "/teacher/classes/:classId", title: "Chi tiết lớp", description: "Thành viên, agent, tài liệu, chính sách và nhật ký của lớp.", week: 3 },
  { pattern: "/teacher/hub", title: "Agent Hub", description: "Tìm agent theo môn, khối lớp và kết quả kiểm định rồi cài vào lớp.", week: 9 },
  { pattern: "/teacher/builder", title: "Agent của tôi", description: "Tạo agent từ tool của nền tảng, thử và chia sẻ lên Hub.", week: 6 },
  { pattern: "/teacher/audit", title: "Nhật ký an toàn", description: "Các lần hệ thống chặn hoặc cảnh báo trong lớp của bạn.", week: 8 },
  { pattern: "/student/home", title: "Trợ lý học tập", description: "Hỏi bài, ôn tập và luyện tập với các agent của lớp.", week: 4 },
  { pattern: "/student/classes", title: "Lớp của tôi", description: "Nhập mã lớp để tham gia và xem các lớp đang học.", week: 3 },
  { pattern: "/student/hub", title: "Agent Hub", description: "Kéo agent đã kiểm định về dùng riêng hoặc cho nhóm.", week: 9 },
  { pattern: "/student/agents", title: "Agent của tôi", description: "Các agent bạn đã kéo về. Agent vẫn tuân theo chính sách của lớp.", week: 6 },
  { pattern: "/parent/home", title: "Con của tôi", description: "Liên kết với con và xem con đang học lớp nào, dùng agent nào.", week: 3 },
  { pattern: "/parent/reports", title: "Báo cáo học tập", description: "Tóm tắt hằng tuần việc học của con.", week: 10 },
  { pattern: "/parent/hub", title: "Agent Hub", description: "Agent giúp phụ huynh kèm con học, đã qua kiểm định.", week: 9 },
  { pattern: "/parent/consent", title: "Đồng ý & quyền riêng tư", description: "Quyết định con có được dùng agent và dữ liệu nào được lưu.", week: 3 },
  { pattern: "/admin/certification", title: "Kiểm định agent", description: "Hàng đợi và kết quả kiểm định agent trước khi lên Hub.", week: 9 },
  { pattern: "/admin/agents", title: "Agent nền tảng", description: "Agent mẫu do nền tảng xây dựng và duy trì.", week: 10 },
  { pattern: "/admin/tools", title: "Tool & MCP", description: "Các tool đã kiểm chứng mà agent được phép dùng.", week: 5 },
  { pattern: "/admin/audit", title: "Nhật ký hệ thống", description: "Sự kiện an toàn và chi phí gọi model toàn hệ thống.", week: 8 },
];

export interface MatchedRoute {
  meta: RouteMeta;
  params: Record<string, string>;
}

export function matchRoute(pathname: string): MatchedRoute | null {
  for (const meta of routes) {
    const params = matchPath(meta.pattern, pathname);
    if (params) return { meta, params };
  }
  return null;
}
