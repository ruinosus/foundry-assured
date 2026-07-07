import { test, expect, Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// ── Artifacts Studio E2E (LOCAL, auth OFF) — skill-driven ─────────────────────────────────────
// Drives the reshaped CopilotKit + AG-UI canvas: describe → the agent picks a SKILL, streams the
// HTML into the sandbox, and AUTO-FILLS Title/Type/Skill (from the function_approval_request args,
// option c) → in-loop edit approval → Save as draft. Case B pins a skill via the selector.
//   E2E_BASE_URL=http://localhost:3010 npx playwright test artifacts-studio.spec.ts
const STEPS_DIR = path.join(__dirname, "artifacts", "steps-studio");
fs.mkdirSync(STEPS_DIR, { recursive: true });
let n = 0;
async function shot(page: Page, name: string) {
  const f = path.join(STEPS_DIR, `${String(++n).padStart(2, "0")}-${name}.png`);
  await page.screenshot({ path: f, fullPage: true });
  console.log(`  📸 ${path.relative(process.cwd(), f)}`);
}

async function send(page: Page, text: string) {
  const composer = page.locator("textarea, [contenteditable='true']").first();
  await expect(composer).toBeVisible({ timeout: 30_000 });
  await composer.fill(text);
  await composer.press("Enter");
}

test("studio (auto skill): describe → agent fills title/type/skill → approve → save → draft", async ({ page }) => {
  await page.goto("/artifacts/new");
  await shot(page, "studio-open");

  await send(page, "Create a one-page HTML report titled 'Studio Smoke' with an <h1> that says 'Studio Smoke' and one short paragraph. Self-contained, starting with <!doctype html>.");
  await shot(page, "prompt-sent");

  // Approval card appears once the agent completes update_artifact (require_confirmation).
  const approve = page.getByTestId("review-approve");
  await expect(approve).toBeVisible({ timeout: 180_000 });

  // AUTO-FILL (option c): Title populated from the approval args; a skill is shown as used.
  const titleInput = page.getByTestId("canvas-title");
  await expect(titleInput).not.toHaveValue("", { timeout: 10_000 });
  await expect(page.getByTestId("used-skill")).toBeVisible();
  // Canvas: the tool-activity strip shows the skill/inputs (steps rendered, not stuck cards).
  await expect(page.getByTestId("steps-strip")).toBeVisible({ timeout: 10_000 });
  await shot(page, "approval-card-autofilled");

  // Sandbox invariant.
  const iframe = page.locator('iframe[title="artifact-preview"]');
  await expect(iframe).toBeVisible();
  expect(await iframe.getAttribute("sandbox")).toBe("allow-scripts");

  await approve.click();
  const frame = await iframe.elementHandle().then((h) => h!.contentFrame());
  await expect(frame!.locator("h1")).toBeVisible({ timeout: 30_000 });
  // Canvas: no stuck "Running" tool card lingers in the transcript after approval.
  await expect(page.getByText("Running")).toHaveCount(0);
  await shot(page, "preview-rendered");

  // Save (title is already agent-filled).
  const save = page.getByTestId("save-draft");
  await expect(save).toBeEnabled();
  await save.click();

  await expect(page.locator(".pill", { hasText: "draft" })).toBeVisible({ timeout: 30_000 });
  // The detail page shows which skill generated it.
  await expect(page.locator(".muted", { hasText: /report|slides|dashboard|walkthrough/ }).first()).toBeVisible();
  await shot(page, "saved-draft");
});

test("studio (skill override): approve → pin 'slides' → regenerate → used skill is slides", async ({ page }) => {
  await page.goto("/artifacts/new");
  await send(page, "Make something about the Foundry platform.");

  // First approval → accept it (Regenerate is intentionally disabled while an approval is pending).
  const approve = page.getByTestId("review-approve");
  await expect(approve).toBeVisible({ timeout: 180_000 });
  await approve.click();
  // The preview settles (run resumed) — now Regenerate is enabled.
  const iframe = page.locator('iframe[title="artifact-preview"]');
  await expect(iframe).toBeVisible();

  // Pin the slides skill via the canvas header selector + regenerate.
  await page.getByTestId("skill-select").selectOption("slides");
  const regen = page.getByTestId("regenerate");
  await expect(regen).toBeEnabled({ timeout: 20_000 });
  await regen.click();

  // A fresh approval lands and the "Generated with" indicator reflects the slides skill.
  await expect(approve).toBeVisible({ timeout: 180_000 });
  await expect(page.getByTestId("used-skill")).toContainText(/slides/i, { timeout: 20_000 });
  await shot(page, "override-slides");
});
