<!-- Keep PRs small and focused. Title in Conventional Commits style, e.g.
     feat(eval): add safety judges  ·  fix(chat): refresh OBO token -->

## What & why

<!-- What does this change and why? Link the issue: Closes #123 -->

## How

<!-- Key implementation notes / decisions / trade-offs -->

## Scope

- [ ] Backend (`apps/backend`)
- [ ] Frontend (`apps/frontend`)
- [ ] Hosted agent (`apps/hosted-agent`)
- [ ] Infra (`infra/`) / azd
- [ ] Docs

## Checklist

- [ ] CI is green (policy gate, typecheck, build, bicep)
- [ ] No SDK signatures invented — verified against the installed package / docs (CLAUDE.md rule #1)
- [ ] No secrets, keys, or `.env` values committed
- [ ] Agent prompts changed only in `app/agents/prompts.py` (single source of truth)
- [ ] Docs updated (`README.md` / `docs/DEPLOYMENT.md`) if behavior or setup changed
- [ ] Eval impact considered (new policy / golden item / safety case if relevant)

## Screenshots / output

<!-- For UI or agent-behavior changes -->
