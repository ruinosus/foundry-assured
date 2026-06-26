// Product identity — the single place to rebrand the showcase for your own domain.
// Changing these four strings re-skins the whole UI (browser title, app shell, login
// screen, sign-in prompt, nav). The hero copy on the Overview page (app/page.tsx) and
// the agent instructions (backend app/agents/prompts.py) are domain *content* you
// rewrite separately — see docs/CUSTOMIZE.md for the full recipe.
export const branding = {
  /** Product name — browser title, sidebar brand, login screen. */
  product: "Foundry Helpdesk",
  /** Short tagline under the brand mark. */
  tagline: "Engineering support",
  /** One-line description — <meta description> + login subtitle. */
  description: "Internal engineering support concierge",
  /** The assistant's display name — nav item + sign-in prompt. */
  assistant: "Concierge",
};
