import { test, expect, Page, Frame } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// ── HTML Artifacts E2E (LOCAL, auth OFF) ─────────────────────────────────────────────────────
// Drives the full artifacts lifecycle against a locally-running app with auth disabled:
//   generate (real Foundry LLM) → draft → sandbox preview → request approval → approve → published.
// Run against the local dev servers (frontend 3010 → backend 8010):
//   E2E_BASE_URL=http://localhost:3010 npx playwright test artifacts.spec.ts
// Screenshots land in artifacts/steps/NN-*.png so a human can follow the run.

const STEPS_DIR = path.join(__dirname, "artifacts", "steps-artifacts");
fs.mkdirSync(STEPS_DIR, { recursive: true });

let n = 0;
async function shot(page: Page, name: string) {
  const file = path.join(STEPS_DIR, `${String(++n).padStart(2, "0")}-${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  console.log(`  📸 ${path.relative(process.cwd(), file)}`);
}

const TITLE = `E2E smoke ${Date.now()}`;

test("artifacts: generate → preview (sandbox) → request approval → approve → published", async ({ page }) => {
  // 1) Artifacts workspace loads (no sign-in — auth is off locally).
  await page.goto("/artifacts");
  await expect(page.getByRole("heading", { name: "Artifacts", exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Generate HTML artifact" })).toBeVisible();
  await shot(page, "workspace");

  // 2) Fill the generate form and submit (this calls the real Foundry LLM).
  await page.getByPlaceholder("Q3 status report").fill(TITLE);
  await page.getByPlaceholder("Describe what to generate…").fill(
    "A tiny one-page HTML report titled 'Hello Artifacts' with an <h1>, a short paragraph, " +
      "and a small inline <script> that sets document.body.dataset.ready = '1'. Self-contained, " +
      "starting with <!doctype html>.",
  );
  const generateBtn = page.getByRole("button", { name: /^Generate$/ });
  await expect(generateBtn).toBeEnabled();
  await generateBtn.click();
  await shot(page, "generating");

  // 3) The new artifact appears as a row (generation can take a while — be patient).
  const row = page.getByRole("link", { name: TITLE });
  await expect(row).toBeVisible({ timeout: 120_000 });
  await expect(page.locator("table.evals")).toContainText("draft");
  await shot(page, "listed-draft");

  // 4) Open the detail page.
  await row.click();
  await expect(page.getByRole("heading", { name: TITLE })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".pill", { hasText: "draft" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Request approval" })).toBeVisible();

  // 5) SECURITY: the preview iframe must be sandbox="allow-scripts" with NO allow-same-origin.
  const iframe = page.locator('iframe[title="artifact-preview"]');
  await expect(iframe).toBeVisible({ timeout: 30_000 });
  const sandbox = await iframe.getAttribute("sandbox");
  expect(sandbox).toBe("allow-scripts");
  expect(sandbox ?? "").not.toContain("allow-same-origin");
  // The sandboxed document actually rendered its content (opaque origin, script ran).
  const frame: Frame | null = await iframe.elementHandle().then((h) => h!.contentFrame());
  expect(frame).not.toBeNull();
  await expect(frame!.locator("h1")).toBeVisible({ timeout: 15_000 });
  await shot(page, "detail-draft-preview");

  // 6) Request approval → pending_approval, with Approve/Reject actions.
  await page.getByRole("button", { name: "Request approval" }).click();
  await expect(page.locator(".pill", { hasText: "pending_approval" })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("button", { name: "Approve & publish" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Reject" })).toBeVisible();
  await shot(page, "pending-approval");

  // 7) Approve & publish → published, with an immutable content hash shown.
  await page.getByRole("button", { name: "Approve & publish" }).click();
  await expect(page.locator(".pill", { hasText: "published" })).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("code")).toBeVisible(); // content-hash prefix
  await shot(page, "published");
});
