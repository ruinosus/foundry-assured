# Vendored: `deep-wiki` plugin (microsoft/skills)

This directory is a **verbatim vendored copy** of the `deep-wiki` plugin from
[`microsoft/skills`](https://github.com/microsoft/skills/tree/main/.github/plugins/deep-wiki) —
the official Microsoft Agent-Skills plugin for generating source-cited, Mermaid-rich wikis of a
codebase. It is the upstream superset of the two skills this project already used
(`wiki-architect`, `wiki-page-writer`); vendoring the whole plugin lets us reuse the rest
(`wiki-llms-txt`, `wiki-researcher`, `wiki-changelog`, `wiki-onboarding`, `wiki-qa`,
`wiki-vitepress`, `wiki-agents-md`, `wiki-ado-convert`) instead of hand-rolling them.

| | |
|---|---|
| Upstream | `github.com/microsoft/skills` → `.github/plugins/deep-wiki` |
| Pinned commit | `5a6104bd49d8fd4e733a30952953fd1cf9f16e62` |
| Plugin version | `2.0.0` |
| License | MIT (see `LICENSE`) |
| Vendored on | 2026-07-02 |

## Why it lives at `.github/skills/`

`.github/skills/` is a **GitHub-native** skill-discovery location: the `SKILL.md` folders here are
picked up by the **GitHub Copilot cloud agent, Copilot code review, Copilot CLI, and agent mode in
VS Code / JetBrains** — so anyone with GitHub Copilot can run the same generators we do, with no
bespoke setup. Claude Code / this repo's local flow also read them.

## How to use

- **Copilot CLI (upstream, no vendoring needed):** `/plugin marketplace add microsoft/skills`
  then `/plugin install deep-wiki@skills`.
- **Any coding agent (this vendored copy):** point it at a `skills/<name>/SKILL.md` and ask it to
  follow that skill — e.g. *"regenerate the deep-wiki for `apps/backend` following
  `wiki-page-writer`, with linked citations and the ≥80% build-fidelity gate."*
- Commands (the `/deep-wiki:*` slash commands) live under `commands/`.

## Updating

Re-vendor by re-cloning `microsoft/skills` at a newer commit and copying
`.github/plugins/deep-wiki` here; bump the pinned commit above. Do **not** hand-edit vendored
files — changes belong upstream. See [ADR-012](../../../docs/adr/ADR-012-reuse-upstream-deep-wiki-tooling.md).
