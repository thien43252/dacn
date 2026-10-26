import { defineConfig } from "@playwright/test";

/**
 * End-to-end check of the demo script (docs/DEMO.md) against running servers:
 *   docker compose -f infra/docker-compose.yml up -d
 *   cd backend && uv run alembic upgrade head && uv run python -m scripts.seed_demo && uv run uvicorn app.main:app --port 8001
 *   cd web && npm run dev            # then, in another terminal:
 *   npm run test:e2e                 # BASE_URL overrides the address, CHROME_PATH a local Chromium
 * Runs with LLM_PROVIDER=fake so replies and certification outcomes are deterministic.
 */
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: process.env.BASE_URL || "http://127.0.0.1:5173",
    locale: "vi-VN",
    viewport: { width: 1440, height: 900 },
    launchOptions: process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {},
  },
});
