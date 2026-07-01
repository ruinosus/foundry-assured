import { test, expect, Browser, Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { completeMfa } from "./entra-mfa";

// ── Per-user ACL round-trip in the BROWSER (the end-to-end proof) ────────────────────────────
// Signs in as two Entra users against the deployed app, asks Cockpit (Live) the same grounded
// question, and asserts the confidential doc is cited for the CLEARED user (A) but NOT for the
// public-only user (B). This exercises the full stack: MSAL login → OBO → grounded.py direct-search
// (x-ms-query-source-authorization trims by the `groups` field) → synthesize → the `sources`
// CUSTOM event → EvidencePanel. The API-level proof lives in apps/backend/eval/grounded_acl_roundtrip_test.py;
// this confirms it surfaces correctly in the real UI.
//
// REQUIRES: the app reachable at E2E_BASE_URL running the Option A cockpit path, and the two test
// users' creds. Skips cleanly when creds are absent.

const PASS = process.env.COCKPIT_TEST_PASSWORD ?? "";
const USER_A = process.env.COCKPIT_TEST_USER_A ?? "";
const USER_B = process.env.COCKPIT_TEST_USER_B ?? "";
const CONFIDENTIAL = process.env.COCKPIT_CONFIDENTIAL_SOURCE ?? "telemetry";
const PROBE = "Como funciona a telemetria e a observabilidade do Cockpit?";

const STEPS_DIR = path.join(__dirname, "artifacts", "acl");
fs.mkdirSync(STEPS_DIR, { recursive: true });

const APP_HOST = (() => {
  try {
    return new URL(process.env.E2E_BASE_URL ?? "http://localhost:3000").host;
  } catch {
    return "localhost:3000";
  }
})();

async function shot(page: Page, name: string) {
  await page.screenshot({ path: path.join(STEPS_DIR, `${name}.png`), fullPage: true }).catch(() => {});
}

// Sign in a specific user in a FRESH context (no shared MSAL cache), then ask Cockpit (Live) the
// probe and return the citations panel text + the answer text.
async function askCockpitAs(browser: Browser, upn: string, tag: string): Promise<string> {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  try {
    await page.goto("/");
    const signIn = page.getByRole("button", { name: /sign in with microsoft/i });
    await expect(signIn).toBeVisible({ timeout: 60_000 });
    await signIn.click();

    await page.waitForURL(/login\.microsoftonline\.com|login\.live\.com/, { timeout: 60_000 });
    // "Use another account" if a cached tile shows, then email.
    await page.getByRole("button", { name: /use another account|usar outra conta/i }).click().catch(() => {});
    const email = page.locator('input[type="email"], input[name="loginfmt"]');
    await email.waitFor({ timeout: 30_000 });
    await email.fill(upn);
    await page.locator("#idSIButton9").click();

    const pwd = page.locator('input[type="password"], input[name="passwd"]');
    await pwd.waitFor({ timeout: 30_000 });
    await pwd.fill(PASS);
    await page.locator("#idSIButton9").click();

    // MFA (registration or code) if the tenant prompts; a no-op when the user has none.
    await completeMfa(page, upn, shot, APP_HOST).catch(() => {});
    // "Stay signed in?" + optional consent.
    await page.locator("#idSIButton9").click({ timeout: 15_000 }).catch(() => {});
    await page.getByRole("button", { name: /accept|aceitar|yes|sim/i }).click({ timeout: 8_000 }).catch(() => {});

    await page.waitForURL((u) => u.host === APP_HOST, { timeout: 60_000 });
    await page.goto("/d/cockpit");
    await page.waitForLoadState("networkidle").catch(() => {});
    // Ensure Live (not the hosted toggle).
    await page.getByRole("button", { name: /^live$/i }).click().catch(() => {});
    const composer = page.locator("textarea, [contenteditable='true']").first();
    await composer.click();
    await composer.fill(PROBE);
    await composer.press("Enter");

    // Wait for citations to settle, then capture the sources panel + the last answer text.
    await page.locator(".citation, .source-chip").first().waitFor({ state: "visible", timeout: 90_000 }).catch(() => {});
    await page.waitForTimeout(2500);
    await shot(page, `cockpit-${tag}`);
    const evidence = (await page.locator(".evidence").innerText().catch(() => "")) || "";
    const answer = (await page.locator("[data-message-role='assistant'], .copilotKitAssistantMessage").last().innerText().catch(() => "")) || "";
    return `${evidence}\n${answer}`.toLowerCase();
  } finally {
    await ctx.close();
  }
}

test.describe.configure({ mode: "serial" });

test("cockpit ACL round-trip — A sees the confidential doc, B does not", async ({ browser }) => {
  test.skip(!PASS || !USER_A || !USER_B, "set COCKPIT_TEST_USER_A/B + COCKPIT_TEST_PASSWORD to run");

  const textA = await askCockpitAs(browser, USER_A, "A-cleared");
  const textB = await askCockpitAs(browser, USER_B, "B-public");

  const needle = CONFIDENTIAL.toLowerCase();
  const aSees = textA.includes(needle);
  const bSees = textB.includes(needle);
  console.log(`A sees "${needle}": ${aSees} | B sees "${needle}": ${bSees}`);

  // A (cleared) must ground on / cite the confidential doc; B (public-only) must NOT.
  expect(aSees, `cleared user A should surface the confidential doc "${needle}"`).toBeTruthy();
  expect(bSees, `public-only user B must NOT surface the confidential doc "${needle}" (ACL leak)`).toBeFalsy();
});
