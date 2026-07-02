import { test, expect, Browser, Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { completeMfa } from "./entra-mfa";

// ── Per-user ACL round-trip in the BROWSER (the end-to-end proof) ────────────────────────────
// Signs in as two Entra users against the app, asks Cockpit the same grounded question, and asserts
// the confidential doc is CITED for the CLEARED user (A) but NOT for the public-only user (B). This
// exercises the full UNIFIED grounded stack: MSAL login → the /d/cockpit route → backend /cockpit →
// OBO → stream_grounded → retrieve() (native searchIndex retrieve; x-ms-query-source-authorization
// trims per-user by the stamped `groups` field) → synthesize → the `sources` CUSTOM event →
// EvidencePanel (.citation-src). The headless API-level twin of this proof lives in
// apps/backend/eval/grounded_archetype_roundtrip_test.py (POSTs the same A/B tokens straight to the
// live /cockpit); this spec confirms the same ACL surfaces correctly in the real browser UI.
//
// NOTE (unification): cockpit no longer has a Foundry hosted twin — grounded runs live-OBO only, so
// there is no "Live" toggle to click anymore (the earlier toggle step is now a harmless no-op). The
// route (/d/cockpit) and the winning assertion (cited SOURCE FILENAMES in .citation-src, never prose)
// are UNCHANGED.
//
// REQUIRES: the app reachable at E2E_BASE_URL running the unified grounded /cockpit path, and the two
// test users' creds. Skips cleanly when creds are absent.

const PASS = process.env.COCKPIT_TEST_PASSWORD ?? "";
const USER_A = process.env.COCKPIT_TEST_USER_A ?? "";
const USER_B = process.env.COCKPIT_TEST_USER_B ?? "";
const CONFIDENTIAL = process.env.COCKPIT_CONFIDENTIAL_SOURCE ?? "telemetry";
// Probe aligned with the headless retrieve() twin (step0_searchindex_kb_acl_abtest) — the extra
// "qual servidor MCP expõe a telemetria" clause reliably steers the cleared user's synthesis to CITE
// the confidential telemetry doc (not merely retrieve it), so the browser ACL + content-on-click
// assertions track the same deterministic surface as the green retrieve()-level proof.
const PROBE =
  "Como funciona a telemetria e a observabilidade do Cockpit? Qual servidor MCP expõe a telemetria e como consultá-la?";

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

// What askCockpitAs returns: the cited source filenames (for the ACL check) and — when the caller
// asks to probe content-on-click — the inline snippet text revealed by clicking the first citation.
interface AskResult {
  sources: string; // lowercased, newline-joined .citation-src texts (the FONTES panel)
  snippet: string | null; // the .citation-content text after clicking citation #1 (null if not probed)
}

// Sign in a specific user in a FRESH context (no shared MSAL cache), then ask Cockpit (Live) the
// probe and return the citations panel text + the answer text. When `probeContent` is set, also
// click the first citation and capture the inline snippet (content-on-click) that renders.
async function askCockpitAs(
  browser: Browser,
  upn: string,
  tag: string,
  probeContent = false,
): Promise<AskResult> {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  // Diagnostics: capture console errors + the copilotkit run-stream body so a missing answer is
  // explained (backend RunError vs slow render) without guessing.
  const diag: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") diag.push(`console.error: ${m.text()}`); });
  page.on("response", async (r) => {
    if (/copilotkit/i.test(r.url()) && r.request().method() === "POST") {
      const body = await r.text().catch(() => "");
      const errs = body.split("\n").filter((l) => /RUN_ERROR|error|403|401|exception|denied/i.test(l)).slice(0, 6);
      if (errs.length) diag.push(`run-stream errors:\n${errs.join("\n")}`);
    }
  });
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
    // Post-unification cockpit runs live-OBO only (no hosted twin), so there's usually no "Live"
    // toggle — this click is a harmless no-op kept for older builds that still render it.
    await page.getByRole("button", { name: /^live$/i }).click().catch(() => {});
    const composer = page.locator("textarea, [contenteditable='true']").first();
    await composer.click();
    await composer.fill(PROBE);
    await composer.press("Enter");

    // Wait for the ANSWER to render (grounded synthesis: OBO + direct search + gpt-5-mini, cold ~60-120s),
    // then for citations to settle. Waiting on the assistant text (not just .citation) also covers B,
    // whose "não sei" answer has no citation.
    const assistant = page.locator(".copilotKitAssistantMessage, [data-message-role='assistant']").last();
    await assistant.waitFor({ state: "visible", timeout: 150_000 }).catch(() => {});
    await page.locator(".citation").first().waitFor({ state: "visible", timeout: 20_000 }).catch(() => {});
    await page.waitForTimeout(2000);
    await shot(page, `cockpit-${tag}`);
    if (diag.length) fs.writeFileSync(path.join(STEPS_DIR, `diag-${tag}.log`), diag.join("\n\n"), "utf8");
    // Return the CITED SOURCE FILENAMES (the FONTES panel), NOT the answer text — the question is
    // about "telemetria", so the answer text mentions the topic even for B; the ACL check must be on
    // whether the confidential DOCUMENT is cited, i.e. the source filenames.
    const sources = (await page.locator(".citation-src").allInnerTexts().catch(() => [])) || [];

    // Content-on-click: click the first citation and capture the INLINE snippet the EvidencePanel
    // reveals (.citation-content). On the fixed unified path this is the retrieved snippet; the
    // regressed/empty path instead renders the `.muted` fallback ("… sem prévia"), which is NOT a
    // .citation-content element — so a non-empty .citation-content text is exactly the proof.
    let snippet: string | null = null;
    if (probeContent) {
      const firstCitation = page.locator(".citation .citation-btn").first();
      await firstCitation.waitFor({ state: "visible", timeout: 20_000 }).catch(() => {});
      await firstCitation.click().catch(() => {});
      const content = page.locator(".citation-content").first();
      await content.waitFor({ state: "visible", timeout: 10_000 }).catch(() => {});
      snippet = (await content.innerText().catch(() => "")) || "";
      await shot(page, `cockpit-${tag}-citation-open`);
    }

    return { sources: sources.join("\n").toLowerCase(), snippet };
  } finally {
    await ctx.close();
  }
}

test.describe.configure({ mode: "serial" });

test("cockpit ACL round-trip — A sees the confidential doc, B does not", async ({ browser }) => {
  test.skip(!PASS || !USER_A || !USER_B, "set COCKPIT_TEST_USER_A/B + COCKPIT_TEST_PASSWORD to run");
  test.setTimeout(10 * 60 * 1000); // two full logins (MFA) + two cold grounded answers

  const resultA = await askCockpitAs(browser, USER_A, "A-cleared", /*probeContent*/ true);
  const resultB = await askCockpitAs(browser, USER_B, "B-public");

  const needle = CONFIDENTIAL.toLowerCase();
  const aSees = resultA.sources.includes(needle);
  const bSees = resultB.sources.includes(needle);
  console.log(`A sees "${needle}": ${aSees} | B sees "${needle}": ${bSees}`);

  // A (cleared) must ground on / cite the confidential doc; B (public-only) must NOT.
  expect(aSees, `cleared user A should surface the confidential doc "${needle}"`).toBeTruthy();
  expect(bSees, `public-only user B must NOT surface the confidential doc "${needle}" (ACL leak)`).toBeFalsy();

  // Content-on-click (the unified-path snippet fix): clicking A's first citation must reveal the
  // retrieved snippet INLINE (.citation-content), not the "sem prévia" fallback. The fallback lives
  // in a `.muted` span, so a non-empty .citation-content is itself the proof; we also assert it is
  // not the fallback prose, for a readable failure.
  const snippet = (resultA.snippet ?? "").trim();
  console.log(`A citation snippet (${snippet.length} chars): ${snippet.slice(0, 120)}`);
  expect(snippet.length, "clicking A's citation must reveal an inline snippet (content-on-click)").toBeGreaterThan(0);
  expect(snippet.toLowerCase(), "snippet must be the retrieved content, not the 'sem prévia' fallback").not.toContain(
    "sem prévia",
  );
});
