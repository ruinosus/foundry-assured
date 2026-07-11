import { test, expect, Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// ── HTML Artifacts lifecycle E2E (LOCAL, auth OFF) ───────────────────────────────────────────
// The interactive CREATION flow (chat + live preview + edit approval) is covered by
// artifacts-studio.spec.ts. This spec covers the rest deterministically (no LLM):
//   seed a draft via the create-from-html API → it lists → detail renders it in the sandbox
//   viewer → request approval → approve → published (immutable + content hash).
// Run: E2E_BASE_URL=http://localhost:3010 npx playwright test artifacts.spec.ts
const STEPS_DIR = path.join(__dirname, "artifacts", "steps-artifacts");
fs.mkdirSync(STEPS_DIR, { recursive: true });
let n = 0;
async function shot(page: Page, name: string) {
  const f = path.join(STEPS_DIR, `${String(++n).padStart(2, "0")}-${name}.png`);
  await page.screenshot({ path: f, fullPage: true });
  console.log(`  📸 ${path.relative(process.cwd(), f)}`);
}

const TITLE = `Lifecycle smoke ${Date.now()}`;
const HTML =
  "<!doctype html><html><body><h1>Lifecycle Smoke</h1><p>Seeded draft for the lifecycle E2E.</p>" +
  "<script>document.body.dataset.ready='1'</script></body></html>";

test("artifacts lifecycle: seed draft → sandbox preview → request approval → approve → published", async ({ page, request, baseURL }) => {
  // 1) Seed a draft through the create-from-html proxy (auth off → tenant "default").
  const create = await request.post(`${baseURL}/api/artifacts/create`, {
    data: { title: TITLE, type: "report", html: HTML },
    headers: { "Content-Type": "application/json" },
  });
  expect(create.ok()).toBeTruthy();
  const { id } = await create.json();
  expect(id).toBeTruthy();

  // 2) It appears in the list as a draft.
  await page.goto("/artifacts");
  const row = page.getByRole("link", { name: TITLE });
  await expect(row).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("table.evals")).toContainText("draft");
  await shot(page, "listed-draft");

  // 3) Detail page renders the HTML in the sandbox viewer (fetch-by-id path).
  await row.click();
  // Canvas detail header shows the title (a span, no longer a heading).
  await expect(page.getByText(TITLE, { exact: true })).toBeVisible({ timeout: 30_000 });
  const iframe = page.locator('iframe[title="artifact-preview"]');
  await expect(iframe).toBeVisible({ timeout: 30_000 });
  expect(await iframe.getAttribute("sandbox")).toBe("allow-scripts");
  const frame = await iframe.elementHandle().then((h) => h!.contentFrame());
  await expect(frame!.locator("h1")).toBeVisible({ timeout: 15_000 });
  await shot(page, "detail-draft-preview");

  // 4) Request approval → pending_approval.
  await page.getByTestId("lifecycle-request-approval").click();
  await expect(page.getByTestId("status-pill")).toHaveText("pending_approval", { timeout: 20_000 });
  await shot(page, "pending-approval");

  // 5) Approve → published + immutable content hash.
  await page.getByTestId("lifecycle-approve").click();
  await expect(page.getByTestId("status-pill")).toHaveText("published", { timeout: 20_000 });
  await expect(page.locator("code")).toBeVisible(); // content-hash prefix
  await shot(page, "published");
});
