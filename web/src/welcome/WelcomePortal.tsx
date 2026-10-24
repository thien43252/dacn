import { useState } from "react";

import { AppMark } from "../components/AppMark";
import { type PortalTheme, welcomeHeading } from "./portalAssets";
import "./welcome.css";

const MOTES = [0, 1, 2, 3, 4, 5, 6];

interface Props {
  theme: PortalTheme | null;
  name: string;
  leaving: boolean;
  slow: boolean;
}

/** Opaque, text-free cover held while the 300 ms decision runs, so neither the shell nor a skeleton shows first. */
export function WelcomeCover() {
  return <div className="welcome-portal welcome-portal--cover" data-portal="cover" aria-hidden="true" />;
}

/** Full-screen welcome shown only while the destination is still preparing. The artwork is decorative: a broken or
 *  slow image leaves the CSS gradient backdrop, and nothing here waits for it. */
export function WelcomePortal({ theme, name, leaving, slow }: Props) {
  const [imageState, setImageState] = useState<"loading" | "loaded" | "failed">("loading");
  const className = ["welcome-portal", theme ? "" : "welcome-portal--neutral", leaving ? "welcome-portal--leaving" : ""].filter(Boolean).join(" ");
  return (
    <div className={className} data-portal={theme?.id ?? "neutral"} data-image={imageState}
      style={theme ? ({ "--fx": `${theme.focusX}%`, "--fy": `${theme.focusY}%` } as React.CSSProperties) : undefined}>
      {theme && imageState !== "failed" && (
        <img className="welcome-portal__art" src={theme.src} alt="" decoding="async" draggable={false}
          style={{ objectPosition: `${theme.focusX}% ${theme.focusY}%` }}
          onLoad={() => setImageState("loaded")} onError={() => setImageState("failed")} />
      )}
      {theme && (
        <div className="welcome-portal__glow" aria-hidden="true">
          {MOTES.map((index) => <i key={index} style={{ "--i": index } as React.CSSProperties} />)}
        </div>
      )}
      <div className="welcome-portal__scrim" aria-hidden="true" />
      <div className="welcome-portal__copy" role="status" aria-live="polite">
        <span className="welcome-portal__mark" aria-hidden="true"><AppMark /></span>
        {theme && <h1>{welcomeHeading(name)}</h1>}
        <p className="welcome-portal__loading">
          <span className="welcome-portal__spinner" aria-hidden="true" />
          Đang chuẩn bị không gian của bạn…
        </p>
        {slow && <p className="welcome-portal__slow">Đang tải lâu hơn dự kiến…</p>}
      </div>
    </div>
  );
}
