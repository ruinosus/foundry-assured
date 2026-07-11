import { Page } from "@playwright/test";
import { authenticator } from "otplib";
import fs from "node:fs";
import path from "node:path";

// ── Entra MFA via software TOTP, driven entirely from the harness ────────────────────────────
// Security Defaults force the test user to register an authenticator (no "Skip"). We register a
// SOFTWARE OATH method through the "use a different authenticator app" path: the wizard reveals a
// base32 secret key as on-screen text — we read it, compute the 6-digit code with otplib, finish
// registration, and persist the secret to .auth/<user>.totp so later runs skip straight to the
// code challenge. No phone, no manual step, tenant security unchanged.

const AUTH_DIR = path.join(__dirname, ".auth");

const secretFile = (user: string) =>
  path.join(AUTH_DIR, `${user.replace(/[^a-z0-9]/gi, "_")}.totp`);

export function loadSecret(user: string): string | null {
  try {
    const s = fs.readFileSync(secretFile(user), "utf8").trim();
    return s || null;
  } catch {
    return null;
  }
}

function saveSecret(user: string, secret: string) {
  fs.mkdirSync(AUTH_DIR, { recursive: true });
  fs.writeFileSync(secretFile(user), secret, "utf8");
}

const code = (secret: string) => authenticator.generate(secret.replace(/\s+/g, ""));

// Pull a base32 TOTP secret out of the revealed "Can't scan the QR code?" panel. MUST be anchored
// on the "Secret key" label — a loose base32 scan would falsely match e.g. the UPN's local part
// (all-letters strings are valid base32), so we never fall back to an unlabelled match.
function extractSecret(text: string): string | null {
  const m = text.match(/secret key[^a-z0-9]*([a-z2-7][a-z2-7 ]{15,})/i);
  if (!m) return null;
  const raw = m[1].replace(/\s+/g, "");
  return raw.length >= 16 ? raw.toUpperCase() : null;
}

const clickFirst = async (page: Page, sel: string): Promise<boolean> => {
  const el = page.locator(sel).first();
  if (await el.isVisible().catch(() => false)) {
    await el.click().catch(() => {});
    return true;
  }
  return false;
};

const PRIMARY = 'input[type="submit"]:visible, button[type="submit"]:visible, #idSIButton9:visible';

// Advance the wizard. Entra mixes classic submit inputs and React <button>s with no type=submit,
// so prefer a text/role match (covers both <button>Next</button> and <input value="Next">) and
// fall back to the classic submit selectors.
async function clickPrimary(page: Page): Promise<boolean> {
  const byText = page
    .getByRole("button", { name: /^(next|verify|done|got it|confirm|yes|finish)$/i })
    .first();
  if (await byText.isVisible().catch(() => false)) {
    await byText.click().catch(() => {});
    return true;
  }
  return clickFirst(page, PRIMARY);
}

/**
 * Run the "Keep your account secure" wizard / MFA challenge as a state machine.
 * Returns when we've left login.microsoftonline.com (back on the app), or after `maxSteps`.
 */
export async function completeMfa(
  page: Page,
  user: string,
  shot: (p: Page, name: string) => Promise<void>,
  appHost: string,
): Promise<void> {
  let secret = loadSecret(user);

  for (let step = 0; step < 18; step++) {
    // Back on the app host → authenticated, done. (URL-absence-of-"login" is unreliable: the
    // proof-up wizard itself runs on login.microsoftonline.com and has transient redirects.)
    if (page.url().includes(appHost)) return;

    await page.waitForTimeout(1500);
    const body = await page.locator("body").innerText().catch(() => "");
    await shot(page, `mfa-${String(step).padStart(2, "0")}`);

    // 1) "Set up a different authentication app" → reveals a software-OATH secret we can read.
    //    (Entra labels it "authentication app"; the secret-key path lives behind it.)
    if (/different authentic(ation|ator) app/i.test(body)) {
      await clickFirst(
        page,
        'a:has-text("different authentic"), button:has-text("different authentic"), :text("different authentic")',
      );
      continue;
    }

    // 2) Secret-key panel revealed → capture the secret, then advance to the code entry.
    if (!secret) {
      const found = extractSecret(body);
      if (found) {
        secret = found;
        saveSecret(user, secret);
        await clickPrimary(page); // Next → code entry
        continue;
      }
    }

    // 2b) "Scan the QR code" screen → the secret is hidden behind "Can't scan the QR code?".
    //     Click it to reveal the base32 key as text, then loop back to extract it.
    if (!secret && /scan the qr code/i.test(body)) {
      await clickFirst(
        page,
        "a:has-text(\"Can't scan\"), button:has-text(\"Can't scan\"), :text(\"Can't scan the QR code\")",
      );
      continue;
    }

    // 3) Code-challenge screen ("Enter the code" — registration confirm, or sign-in challenge) →
    //    compute + enter the 6-digit code. Broad selector: the registration field has no stable
    //    name/id, so also match by placeholder / one-time-code autocomplete / any visible textbox.
    const otc = page.locator(
      [
        'input[name="otc"]',
        "#idTxtBx_SAOTCC_OTC",
        'input[autocomplete="one-time-code"]',
        'input[inputmode="numeric"]',
        'input[type="tel"]',
        'input[placeholder*="ode" i]',
        'input[type="text"]:visible',
      ].join(", "),
    ).first();
    if (secret && (await otc.isVisible().catch(() => false))) {
      await otc.fill(code(secret));
      await page.waitForTimeout(300);
      await clickPrimary(page); // Verify / Next
      continue;
    }

    // 4) Success / "Stay signed in?" / generic "Next"/"Done"/"Got it" → advance.
    if (await clickPrimary(page)) continue;
    if (await clickFirst(page, ':text("Done"):visible, :text("Got it"):visible, :text("Next"):visible')) continue;

    // Nothing actionable and still on the IdP — give the page a beat, then retry.
    await page.waitForTimeout(1500);
  }
}
