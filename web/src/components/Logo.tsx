import { navigate } from "../app/router";
import { AppMark } from "./AppMark";

export function Logo({ compact = false, inverse = false }: { compact?: boolean; inverse?: boolean }) {
  return (
    <button
      className={`logo ${compact ? "logo--compact" : ""} ${inverse ? "logo--inverse" : ""}`}
      type="button"
      onClick={() => navigate("/")}
      aria-label="Về trang giới thiệu"
    >
      <span className="logo__mark" aria-hidden="true"><AppMark /></span>
      {!compact && (
        <span className="logo__copy">
          <strong>EduAgent</strong>
          <small>Hub</small>
        </span>
      )}
    </button>
  );
}
