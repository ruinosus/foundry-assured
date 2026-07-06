import { test, expect, Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// ── Artifacts Studio E2E (LOCAL, auth OFF) ───────────────────────────────────────────────────
// Drives the CopilotKit + AG-UI canvas: describe → live sandboxed preview → in-loop edit
// approval (require_confirmation) → Save as draft. This is where the approval resume payload is
// verified live (the ArtifactStudio TODO(verify-live)).
//   E2E_BASE_URL=http://localhost:3010 npx playwright test artifacts-studio.spec.ts
const STEPS_DIR = path.join(__dirname, "artifacts", "steps-studio");
fs.mkdirSync(STEPS_DIR, { recursive: true });
let n = 0;
async function shot(page: Page, name: string) {
  const f = path.join(STEPS_DIR, `${String(++n).padStart(2, "0")}-${name}.png`);
  await page.screenshot({ path: f, fullPage: true });
  console.log(`  📸 ${path.relative(process.cwd(), f)}`);
}

test("studio: describe → live preview → confirm edit → save → draft", async ({ page }) => {
  // Tap the CopilotKit SSE so we can SEE the AG-UI events (state deltas + the approval event).
  page.on("console", (m) => {
    const t = m.text();
    if (/approval|confirm_changes|interrupt|STATE_|request_info|function_call/i.test(t)) {
      console.log("  [console] " + t.slice(0, 300));
    }
  });

  await page.goto("/artifacts/new");
  const composer = page.locator("textarea, [contenteditable='true']").first();
  await expect(composer).toBeVisible({ timeout: 30_000 });
  await shot(page, "studio-open");

  await composer.fill(
    "Create a one-page HTML report titled 'Studio Smoke' with an <h1> heading that says " +
      "'Studio Smoke' and one short paragraph. Self-contained, starting with <!doctype html>.",
  );
  await composer.press("Enter");
  await shot(page, "prompt-sent");

  // The in-loop edit-approval card appears once the model finishes the update_artifact tool call
  // (require_confirmation). This is the key signal the shared-state + confirmation flow works.
  const approve = page.getByRole("button", { name: /^Approve$/ });
  await expect(approve).toBeVisible({ timeout: 150_000 });
  await shot(page, "approval-card");

  // The live preview should already show streamed HTML (predictive STATE_DELTA) before we approve.
  const iframe = page.locator('iframe[title="artifact-preview"]');
  await expect(iframe).toBeVisible();
  expect(await iframe.getAttribute("sandbox")).toBe("allow-scripts");

  await approve.click();
  await shot(page, "approved");

  // After approval the run resumes and the final STATE_SNAPSHOT lands; the preview heading renders.
  const frame = await iframe.elementHandle().then((h) => h!.contentFrame());
  await expect(frame!.locator("h1")).toBeVisible({ timeout: 30_000 });
  await shot(page, "preview-rendered");

  // Save as draft.
  await page.getByPlaceholder("Q3 status report").fill("Studio Smoke " + Date.now());
  const save = page.getByRole("button", { name: /save as draft/i });
  await expect(save).toBeEnabled();
  await save.click();

  // Landed on the detail page as a draft.
  await expect(page.locator(".pill", { hasText: "draft" })).toBeVisible({ timeout: 30_000 });
  await shot(page, "saved-draft");
});
