import { defineConfig, devices } from "@playwright/test";

// E2E against the DEPLOYED cloud app (no local webServer). Point E2E_BASE_URL at the
// deployed web FQDN (azd env get-value WEB_URL). Auth creds come from env (never committed):
//   E2E_BASE_URL  — the deployed web URL
//   E2E_USER      — an Entra test user UPN (e.g. cockpit-test-a@…onmicrosoft.com)
//   E2E_PASS      — that user's password
//
// Everything lands in ./artifacts so you can open it locally and follow each run:
//   artifacts/steps/   — named, ordered screenshots of every step (the "prints")
//   artifacts/report/  — the Playwright HTML report (npm run report)
//   artifacts/results/ — per-test trace.zip + video on failure
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: ".",
  outputDir: "artifacts/results",
  fullyParallel: false,
  workers: 1, // single session: MSAL sessionStorage lives in one context/tab
  retries: 0,
  // Cold start: the container scales to zero, so the first hit can take ~30s+. Be patient.
  timeout: 5 * 60 * 1000,
  expect: { timeout: 30 * 1000 },
  reporter: [
    ["list"],
    ["html", { outputFolder: "artifacts/report", open: "never" }],
  ],
  use: {
    baseURL: BASE_URL,
    screenshot: "on",
    video: "on",
    trace: "on",
    navigationTimeout: 90 * 1000,
    actionTimeout: 30 * 1000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
