import { useState } from "react";
import { parseVideoUrl } from "./videoUrl";

interface VideoPlayerProps {
  url?: string | null;
  embedUrl?: string | null;
  fileUrl?: string | null;
  title?: string;
}

export function VideoPlayer({ url, embedUrl, fileUrl, title = "Video" }: VideoPlayerProps) {
  const [hasError, setHasError] = useState(false);

  const targetUrl = fileUrl || url || "";
  const parsed = parseVideoUrl(url || "");
  const effectiveEmbed = embedUrl || (parsed.kind === "youtube" || parsed.kind === "vimeo" ? parsed.embedUrl : null);
  const isDirect = fileUrl || parsed.kind === "direct";

  if (hasError) {
    return (
      <div className="lms-video-player lms-video-player--error">
        <p className="ea-muted">Không thể phát video này trong trang.</p>
        {targetUrl && (
          <a
            href={targetUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="button button--secondary"
          >
            Mở ở tab mới
          </a>
        )}
      </div>
    );
  }

  return (
    <div className="lms-video-player">
      {effectiveEmbed ? (
        <div className="lms-video-player__responsive">
          <iframe
            src={effectiveEmbed}
            title={title}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen
            onError={() => setHasError(true)}
          />
        </div>
      ) : isDirect ? (
        <div className="lms-video-player__media">
          <video
            controls
            playsInline
            preload="metadata"
            src={targetUrl}
            onError={() => setHasError(true)}
          >
            <source src={targetUrl} />
            Trình duyệt của bạn không hỗ trợ thẻ video HTML5.
          </video>
        </div>
      ) : (
        <div className="lms-video-player__fallback">
          <p className="ea-muted">Video từ liên kết ngoài:</p>
          {targetUrl && (
            <a
              href={targetUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="button button--secondary"
            >
              Mở ở tab mới
            </a>
          )}
        </div>
      )}

      {targetUrl && (
        <div className="lms-video-player__footer">
          <a
            href={targetUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="lms-video-player__external-link"
          >
            Mở ở tab mới ↗
          </a>
        </div>
      )}
    </div>
  );
}
