import { readdirSync } from "node:fs";
import { join } from "node:path";
import { defineConfig } from "@playwright/test";

const testDir = "./e2e";

// Playwright silently skips anything that is not a regular file. OneDrive can turn a file into a cloud placeholder,
// which would drop a whole spec while the run still reports success, so that is an error here.
const skipped = readdirSync(join(import.meta.dirname, testDir), { withFileTypes: true }).filter((entry) => entry.name.endsWith(".spec.js") && !entry.isFile());
if (skipped.length) {
  throw new Error(`These test files are not regular files, so Playwright would skip them: ${skipped.map((entry) => entry.name).join(", ")}. Move the project out of OneDrive, or mark the folder "Always keep on this device".`);
}

// These tests need the whole stack already running. See docs/TESTING.md.
export default defineConfig({
  testDir,
  timeout: 120000,
  workers: 1,
  reporter: "list",
  outputDir: process.env.E2E_OUTPUT_DIR || "test-results",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
