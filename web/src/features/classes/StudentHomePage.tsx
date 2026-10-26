import { useAuth } from "../../auth/AuthContext";
import { ChatPanel } from "../../components/ChatPanel";

/** Student home: the class chat, full width. */
export function StudentHomePage() {
  const { user } = useAuth();
  if (!user) return null;
  return <ChatPanel inline open onClose={() => undefined} onBusyChange={() => undefined} userId={user.id} role={user.role} />;
}
