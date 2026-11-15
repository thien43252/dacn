import { describe, expect, it } from "vitest";
import { parseVideoUrl } from "./videoUrl";

describe("parseVideoUrl", () => {
  describe("YouTube URLs", () => {
    it("parses youtube.com/watch?v= format", () => {
      const result = parseVideoUrl("https://www.youtube.com/watch?v=dQw4w9WgXcQ");
      expect(result.kind).toBe("youtube");
      expect(result.embedUrl).toBe("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ");
    });

    it("parses youtube.com/watch?v= with additional query params", () => {
      const result = parseVideoUrl("https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s&feature=shared");
      expect(result.kind).toBe("youtube");
      expect(result.embedUrl).toBe("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ");
    });

    it("parses youtu.be/ short link format", () => {
      const result = parseVideoUrl("https://youtu.be/dQw4w9WgXcQ");
      expect(result.kind).toBe("youtube");
      expect(result.embedUrl).toBe("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ");
    });

    it("parses youtu.be/ with query params", () => {
      const result = parseVideoUrl("https://youtu.be/dQw4w9WgXcQ?t=120");
      expect(result.kind).toBe("youtube");
      expect(result.embedUrl).toBe("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ");
    });

    it("parses youtube.com/embed/ format", () => {
      const result = parseVideoUrl("https://www.youtube.com/embed/dQw4w9WgXcQ");
      expect(result.kind).toBe("youtube");
      expect(result.embedUrl).toBe("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ");
    });

    it("parses youtube shorts format", () => {
      const result = parseVideoUrl("https://www.youtube.com/shorts/dQw4w9WgXcQ");
      expect(result.kind).toBe("youtube");
      expect(result.embedUrl).toBe("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ");
    });
  });

  describe("Vimeo URLs", () => {
    it("parses vimeo.com/<id> format", () => {
      const result = parseVideoUrl("https://vimeo.com/76979871");
      expect(result.kind).toBe("vimeo");
      expect(result.embedUrl).toBe("https://player.vimeo.com/video/76979871");
    });

    it("parses player.vimeo.com/video/<id> format", () => {
      const result = parseVideoUrl("https://player.vimeo.com/video/76979871?title=0");
      expect(result.kind).toBe("vimeo");
      expect(result.embedUrl).toBe("https://player.vimeo.com/video/76979871");
    });

    it("parses vimeo channels link", () => {
      const result = parseVideoUrl("https://vimeo.com/channels/staffpicks/76979871");
      expect(result.kind).toBe("vimeo");
      expect(result.embedUrl).toBe("https://player.vimeo.com/video/76979871");
    });
  });

  describe("Direct video file URLs", () => {
    it("parses direct .mp4 URL", () => {
      const result = parseVideoUrl("https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4");
      expect(result.kind).toBe("direct");
      expect(result.embedUrl).toBeUndefined();
    });

    it("parses direct .webm URL with query params", () => {
      const result = parseVideoUrl("https://example.com/videos/sample.webm?token=abc123xyz");
      expect(result.kind).toBe("direct");
    });

    it("parses local/relative .mp4 path", () => {
      const result = parseVideoUrl("/api/classes/class-1/files/video-123.mp4");
      expect(result.kind).toBe("direct");
    });
  });

  describe("Other URLs (fallback to link)", () => {
    it("identifies generic web pages as link", () => {
      const result = parseVideoUrl("https://en.wikipedia.org/wiki/React_(software)");
      expect(result.kind).toBe("link");
      expect(result.embedUrl).toBeUndefined();
    });

    it("identifies non-video doc link as link", () => {
      const result = parseVideoUrl("https://example.com/document.pdf");
      expect(result.kind).toBe("link");
    });

    it("handles empty string gracefully", () => {
      const result = parseVideoUrl("");
      expect(result.kind).toBe("link");
    });
  });
});
