import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

const db = join(tmpdir(), `wakeful-e2e-${process.pid}.db`);

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:8765", channel: "chrome", headless: true, trace: "off" },
  webServer: {
    command: `rm -f ${db} && cd ../backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8765`,
    url: "http://127.0.0.1:8765/api/health",
    reuseExistingServer: false,
    timeout: 60_000,
    env: {
      DATABASE_URL: `sqlite:///${db}`, ADMIN_PASSWORD: "e2e-password", ADMIN_PASSWORD_HASH: "", FANVUE_MODE: "mock",
      AI_PROVIDER: "mock", WORKER_POLL_SECONDS: "0.5", PUBLIC_BASE_URL: "http://127.0.0.1:8765", SECRET_KEY: "e2e",
    },
  },
});
