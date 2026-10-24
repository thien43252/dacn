import type { Role } from "../auth/api";

export type GuideRole = Extract<Role, "teacher" | "student" | "parent">;

export interface GuideStep {
  id: string;
  /** Value of the `data-guide` attribute on the real element the step points at. */
  target: string;
  title: string;
  /** Two or three short sentences that quote the labels visible on the screen. */
  text: string;
  /** At most three short lines when the step has a few distinct points. */
  bullets?: string[];
}

export interface GuideDef {
  /** Storage id: the overview keeps the bare key, a contextual guide adds its own id. */
  id: string;
  kind: "overview" | "context";
  role: GuideRole;
  /** Name shown in the help menu. */
  label: string;
  /** The route the guide lives on; leaving it ends the guide without storing a result. */
  route: string;
  steps: GuideStep[];
}

/** Bump to show every guide again to everyone: the storage keys carry this version. */
export const GUIDE_VERSION = 1;

export const GUIDE_HOME: Record<GuideRole, string> = {
  teacher: "/teacher/classes",
  student: "/student/home",
  parent: "/parent/home",
};

export const GUIDE_NAME: Record<GuideRole, string> = { teacher: "Đũa phép", student: "Sách", parent: "Sách" };

export function isGuideRole(role: Role | undefined): role is GuideRole {
  return role === "teacher" || role === "student" || role === "parent";
}

const teacherOverview: GuideDef = {
  id: "overview",
  kind: "overview",
  role: "teacher",
  label: "Tổng quan EduAgent Hub",
  route: "/teacher/classes",
  steps: [
    { id: "classes", target: "nav-classes", title: "Tạo và quản lý lớp",
      text: "Trong “Lớp của tôi”, tạo lớp mới rồi gửi mã lớp cho học sinh và phụ huynh. Mỗi lớp có thành viên, agent, tài liệu và chính sách riêng." },
    { id: "hub", target: "nav-hub", title: "Tìm agent trên Hub",
      text: "Agent Hub có các agent do nền tảng và giáo viên khác chia sẻ. Lọc theo môn và khối lớp, xem kết quả kiểm định rồi cài vào lớp.",
      bullets: ["Chỉ agent đã qua kiểm định mới hiện với học sinh và phụ huynh."] },
    { id: "builder", target: "nav-builder", title: "Tự tạo agent",
      text: "Trong “Agent của tôi”, chọn tool có sẵn, viết hướng dẫn cho agent và thử ngay. Khi chia sẻ lên Hub, agent sẽ được kiểm định tự động." },
    { id: "audit", target: "nav-audit", title: "Theo dõi an toàn",
      text: "“Nhật ký an toàn” ghi lại các lần hệ thống chặn hoặc cảnh báo trong lớp của bạn, kèm lý do." },
    { id: "assistant", target: "chat-launcher", title: "Trò chuyện với agent",
      text: "Bấm nút trợ lý để hỏi các agent đã cài. Gõ @ để gọi đích danh một agent.",
      bullets: ["Câu trả lời chỉ để tham khảo. Quyết định là của bạn."] },
  ],
};

const studentOverview: GuideDef = {
  id: "overview",
  kind: "overview",
  role: "student",
  label: "Tổng quan EduAgent Hub",
  route: "/student/home",
  steps: [
    { id: "home", target: "nav-home", title: "Trợ lý học tập của bạn",
      text: "Trang này gom các agent của lớp và của riêng bạn. Hỏi bài, ôn tập hoặc luyện tập ngay tại đây." },
    { id: "classes", target: "nav-classes", title: "Tham gia lớp",
      text: "Nhập mã lớp giáo viên gửi để tham gia. Agent và tài liệu của lớp sẽ hiện cho bạn." },
    { id: "hub", target: "nav-hub", title: "Khám phá agent",
      text: "Agent Hub có các agent đã qua kiểm định an toàn. Bạn có thể kéo agent về dùng riêng hoặc cho nhóm." },
    { id: "agents", target: "nav-agents", title: "Agent của bạn",
      text: "Xem và gỡ các agent bạn đã kéo về. Agent vẫn tuân theo chính sách của lớp." },
    { id: "assistant", target: "chat-launcher", title: "Hỏi khi cần",
      text: "Bấm nút trợ lý rồi nhập câu hỏi. Gõ @ để chọn agent.",
      bullets: ["Agent gợi ý cách làm, bạn vẫn là người tự làm bài."] },
  ],
};

const parentOverview: GuideDef = {
  id: "overview",
  kind: "overview",
  role: "parent",
  label: "Tổng quan EduAgent Hub",
  route: "/parent/home",
  steps: [
    { id: "home", target: "nav-home", title: "Theo dõi con",
      text: "Trang này cho biết con đang học lớp nào và dùng agent nào. Liên kết với con bằng mã lớp giáo viên gửi." },
    { id: "reports", target: "nav-reports", title: "Báo cáo học tập",
      text: "Xem tóm tắt hằng tuần: con đã hỏi gì, ôn chủ đề nào và cần hỗ trợ ở đâu." },
    { id: "hub", target: "nav-hub", title: "Agent cho phụ huynh",
      text: "Agent Hub có các agent giúp phụ huynh kèm con học. Tất cả đều đã qua kiểm định." },
    { id: "consent", target: "nav-consent", title: "Đồng ý và quyền riêng tư",
      text: "Bạn quyết định con có được dùng agent hay không và dữ liệu nào được lưu. Có thể rút lại bất cứ lúc nào." },
    { id: "assistant", target: "chat-launcher", title: "Hỏi trợ lý phụ huynh",
      text: "Bấm nút trợ lý để hỏi về việc học của con." },
  ],
};

export const GUIDES: Record<GuideRole, GuideDef[]> = {
  teacher: [teacherOverview],
  student: [studentOverview],
  parent: [parentOverview],
};

export function overviewOf(role: GuideRole): GuideDef {
  return GUIDES[role][0];
}

export function contextGuidesFor(role: GuideRole, pathname: string): GuideDef[] {
  return GUIDES[role].filter((guide) => guide.kind === "context" && guide.route === pathname);
}
