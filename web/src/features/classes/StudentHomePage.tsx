import { useLocation } from "../../app/router";
import { useAuth } from "../../auth/AuthContext";
import { ChatPanel } from "../../components/ChatPanel";

/** Student home: the class chat, full width. `?class=…&draft=…` (from "Làm cùng gia sư") opens that class with the
 *  practice set already in the chat box. */
export function StudentHomePage() {
  const { user } = useAuth();
  const { search } = useLocation();
  if (!user) return null;
  const params = new URLSearchParams(search);
  const classId = params.get("class") ?? undefined;
  const draft = params.get("draft") ?? undefined;
  return (
    <ChatPanel
      key={`${classId ?? ""}:${draft ?? ""}`}
      inline
      open
      onClose={() => undefined}
      onBusyChange={() => undefined}
      userId={user.id}
      role={user.role}
      contextClassId={classId}
      draft={draft}
    />
  );
}
