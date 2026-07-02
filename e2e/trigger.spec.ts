import { test, Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { completeMfa } from "./entra-mfa";

// Minimal single-user trigger to capture the deployed grounded RUN_ERROR detail (faster than the
// full 2-user round-trip). Logs in as one user, asks Cockpit (Live), and writes any copilotkit
// run-stream RUN_ERROR line to artifacts/trigger-run-error.txt.

const PASS = process.env.COCKPIT_TEST_PASSWORD ?? "";
const UPN = process.env.COCKPIT_TEST_USER_A ?? "";
const APP_HOST = (() => { try { return new URL(process.env.E2E_BASE_URL ?? "http://localhost:3000").host; } catch { return "localhost:3000"; } })();
const OUT = path.join(__dirname, "artifacts", "trigger-run-error.txt");

async function shot(_p: Page, _n: string) {}

test("trigger cockpit grounded once (capture RUN_ERROR detail)", async ({ browser }) => {
  test.skip(!PASS || !UPN, "set COCKPIT_TEST_USER_A + COCKPIT_TEST_PASSWORD");
  test.setTimeout(5 * 60 * 1000);
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const captured: string[] = [];
  page.on("response", async (r) => {
    if (/copilotkit/i.test(r.url()) && r.request().method() === "POST") {
      const b = await r.text().catch(() => "");
      for (const l of b.split("\n")) if (/RUN_ERROR/i.test(l)) captured.push(l);
    }
  });
  try {
    await page.goto("/");
    await page.getByRole("button", { name: /sign in with microsoft/i }).click();
    await page.waitForURL(/login\.microsoftonline\.com|login\.live\.com/, { timeout: 60_000 });
    await page.getByRole("button", { name: /use another account|usar outra conta/i }).click().catch(() => {});
    await page.locator('input[type="email"], input[name="loginfmt"]').fill(UPN);
    await page.locator("#idSIButton9").click();
    await page.locator('input[type="password"], input[name="passwd"]').fill(PASS);
    await page.locator("#idSIButton9").click();
    await completeMfa(page, UPN, shot, APP_HOST).catch(() => {});
    await page.locator("#idSIButton9").click({ timeout: 15_000 }).catch(() => {});
    await page.getByRole("button", { name: /accept|aceitar|yes|sim/i }).click({ timeout: 8_000 }).catch(() => {});
    await page.waitForURL((u) => u.host === APP_HOST, { timeout: 60_000 });
    await page.goto("/d/cockpit");
    await page.waitForLoadState("networkidle").catch(() => {});
    const composer = page.locator("textarea, [contenteditable='true']").first();
    await composer.click();
    await composer.fill("Como funciona a telemetria do Cockpit?");
    await composer.press("Enter");
    await page.waitForTimeout(60_000); // let the grounded call run + fail/answer
  } finally {
    fs.writeFileSync(OUT, captured.join("\n") || "(no RUN_ERROR captured — maybe it answered!)", "utf8");
    await ctx.close();
  }
});
