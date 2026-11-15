export type VideoKind = "youtube" | "vimeo" | "direct" | "link";

export interface ParsedVideoUrl {
  kind: VideoKind;
  embedUrl?: string;
  originalUrl: string;
}

/**
 * Normalizes video URLs to embeddable URLs or identifies direct video / external link.
 * Supports:
 * - YouTube: watch?v=, youtu.be/, /embed/, /shorts/ -> https://www.youtube-nocookie.com/embed/{id}
 * - Vimeo: vimeo.com/{id}, player.vimeo.com/video/{id} -> https://player.vimeo.com/video/{id}
 * - Direct: .mp4, .webm
 * - Other: kind "link"
 */
export function parseVideoUrl(input: string): ParsedVideoUrl {
  const trimmed = (input || "").trim();
  if (!trimmed) {
    return { kind: "link", originalUrl: trimmed };
  }

  try {
    // Relative or absolute URL parsing
    const url = trimmed.startsWith("http://") || trimmed.startsWith("https://")
      ? new URL(trimmed)
      : new URL(trimmed, "http://localhost");

    const host = url.hostname.toLowerCase();
    const pathname = url.pathname;

    // 1. YouTube
    if (host === "youtu.be" || host.endsWith(".youtu.be")) {
      const videoId = pathname.replace(/^\/+/, "").split("/")[0]?.split("?")[0];
      if (videoId) {
        return {
          kind: "youtube",
          embedUrl: `https://www.youtube-nocookie.com/embed/${videoId}`,
          originalUrl: trimmed,
        };
      }
    }

    if (host === "youtube.com" || host.endsWith(".youtube.com") || host === "youtube-nocookie.com" || host.endsWith(".youtube-nocookie.com")) {
      // watch?v=
      const vParam = url.searchParams.get("v");
      if (vParam) {
        return {
          kind: "youtube",
          embedUrl: `https://www.youtube-nocookie.com/embed/${vParam}`,
          originalUrl: trimmed,
        };
      }

      // /embed/:id or /shorts/:id
      const embedMatch = pathname.match(/^\/(?:embed|shorts)\/([^/?&#]+)/);
      if (embedMatch && embedMatch[1]) {
        return {
          kind: "youtube",
          embedUrl: `https://www.youtube-nocookie.com/embed/${embedMatch[1]}`,
          originalUrl: trimmed,
        };
      }
    }

    // 2. Vimeo
    if (host === "vimeo.com" || host.endsWith(".vimeo.com")) {
      // player.vimeo.com/video/:id
      const playerMatch = pathname.match(/^\/video\/([0-9]+)/);
      if (playerMatch && playerMatch[1]) {
        return {
          kind: "vimeo",
          embedUrl: `https://player.vimeo.com/video/${playerMatch[1]}`,
          originalUrl: trimmed,
        };
      }

      // vimeo.com/:id or vimeo.com/channels/*/:id
      const vimeoMatch = pathname.match(/\/([0-9]+)(?:[/?&#]|$)/);
      if (vimeoMatch && vimeoMatch[1]) {
        return {
          kind: "vimeo",
          embedUrl: `https://player.vimeo.com/video/${vimeoMatch[1]}`,
          originalUrl: trimmed,
        };
      }
    }

    // 3. Direct .mp4 / .webm
    const cleanPath = pathname.toLowerCase();
    if (cleanPath.endsWith(".mp4") || cleanPath.endsWith(".webm")) {
      return {
        kind: "direct",
        originalUrl: trimmed,
      };
    }
  } catch {
    // If URL parsing fails, check extension directly for path strings
    const lower = trimmed.toLowerCase();
    if (lower.endsWith(".mp4") || lower.endsWith(".webm")) {
      return { kind: "direct", originalUrl: trimmed };
    }
  }

  return {
    kind: "link",
    originalUrl: trimmed,
  };
}
