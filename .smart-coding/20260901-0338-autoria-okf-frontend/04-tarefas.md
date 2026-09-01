# Fatias — Autoria OKF e evolução completa do frontend

## Revisão 2026-09-01 — fundação visual independente

As fatias mantêm IDs, dependências e user stories, mas substituem CURA pelo Assured UI próprio do produto. Nenhuma fatia pode adicionar pacote, asset, fonte ou identidade visual da Rede D'Or.

**Seções afetadas:** F01, F02–F15 (skills de UI), F14 e F15

## Legenda

- `[ ]` pending · `[~]` in-progress · `[x]` done · `[!]` blocked · `[-]` skipped
- type: `AFK` (away-from-keyboard) | `HITL` (human-in-the-loop)
- deps: IDs de fatias bloqueadoras separados por vírgula; `—` se nenhuma
- US: user stories cobertas (IDs do `02-prd.md`)
- sec: triggers NORDOR-122 aplicáveis (auth, input-validation, rate-limit, criptografia, logs, dados-sensiveis)
- `→ F{NN}.md`: ponteiro para arquivo de detalhe

## Fila

- [x] F01 [AFK] Fundação Assured UI com seam e ambiente local visível — deps: — — US: US-001, US-003 → F01.md
- [x] F02 [AFK] Contexto tenant-área e administração autorizada — deps: F01 — US: US-003, US-016, US-017 — sec: auth, input-validation, logs, dados-sensiveis → F02.md
- [x] F03 [AFK] Catálogo factual e detalhe de recurso — deps: F02 — US: US-004, US-005 — sec: auth, input-validation, logs → F03.md
- [x] F04 [AFK] ChangeSet local durável e concorrência otimista — deps: F02 — US: US-003, US-010, US-016 — sec: auth, input-validation, logs, dados-sensiveis → F04.md
- [x] F05 [AFK] Três rotas de autoria guiadas por FormFlow — deps: F01, F04 — US: US-006, US-007 — sec: auth, input-validation, logs → F05.md
- [x] F06 [AFK] Builder multi-documento fundamentado no catálogo — deps: F03, F04, F05 — US: US-008 — sec: auth, input-validation, logs, dados-sensiveis → F06.md
- [ ] F07 [AFK] Registries e bindings isolados por área — deps: F02, F03 — US: US-009, US-016 — sec: auth, input-validation, logs, dados-sensiveis → F07.md
- [ ] F08 [AFK] Bundle Editor versionado e consistente — deps: F04, F05, F06, F07 — US: US-010 — sec: auth, input-validation, logs → F08.md
- [ ] F09 [AFK] Conformidade honesta por fase — deps: F03, F04, F07, F08 — US: US-011 — sec: auth, input-validation, logs → F09.md
- [ ] F10 [HITL] Submissão, revisão e decisão do Approver — deps: F04, F08, F09 — US: US-012, US-017 — sec: auth, input-validation, logs, dados-sensiveis → F10.md
- [ ] F11 [HITL] Pull request GitHub com identidade delegada — deps: F10 — US: US-013, US-015, US-017 — sec: auth, input-validation, rate-limit, criptografia, logs, dados-sensiveis → F11.md
- [ ] F12 [HITL] Pull request Azure DevOps com OBO — deps: F10 — US: US-013, US-015, US-017 — sec: auth, input-validation, rate-limit, criptografia, logs, dados-sensiveis → F12.md
- [ ] F13 [HITL] Reconciliação e materialização pós-merge — deps: F11, F12 — US: US-014, US-015, US-017 — sec: auth, input-validation, rate-limit, criptografia, logs, dados-sensiveis → F13.md
- [ ] F14 [AFK] Redesign Assured UI das rotas legadas — deps: F01, F02 — US: US-002, US-018 — sec: auth, input-validation, logs, dados-sensiveis → F14.md
- [ ] F15 [HITL] Gate integrado e ativação do frontend Assured UI — deps: F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, F14 — US: todas — sec: auth, input-validation, rate-limit, criptografia, logs, dados-sensiveis → F15.md

## Histórico

- 2026-09-01 — patch — removida dependência e identidade visual da Rede D'Or; adotado Assured UI próprio
