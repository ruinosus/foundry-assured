# Fatias — Binding MCP, Toolbox e snapshot de descoberta

## Legenda

- `[ ]` pending · `[~]` in-progress · `[x]` done · `[!]` blocked · `[-]` skipped
- type: `AFK` (away-from-keyboard) | `HITL` (human-in-the-loop)
- deps: IDs de fatias bloqueadoras separados por vírgula; `—` se nenhuma
- US: user stories cobertas (IDs do `02-prd.md`)
- sec: triggers NORDOR-122 aplicáveis
- `→ F{NN}.md`: detalhe imutável da fatia

## Fila

- [x] F01 [AFK] Discovery de Toolbox com versão fixa — deps: — — US: US-001, US-003, US-006, US-009 — sec: auth, input-validation, criptografia, logs, dados-sensiveis → F01.md
- [ ] F02 [AFK] Binding estrito e conformidade — deps: F01 — US: US-001, US-006, US-010 — sec: auth, input-validation, dados-sensiveis → F02.md
- [ ] F03 [AFK] Endpoint direto aprovado e egress fail-closed — deps: F01 — US: US-002, US-005, US-006 — sec: auth, input-validation, rate-limit, logs → F03.md
- [ ] F04 [AFK] Autenticação sem transporte de segredo — deps: F03 — US: US-003, US-005, US-006, US-009 — sec: auth, criptografia, logs, dados-sensiveis → F04.md
- [ ] F05 [AFK] Classificação Admin e enforcement runtime — deps: F02, F04 — US: US-004, US-010 — sec: auth, input-validation, logs → F05.md
- [ ] F06 [AFK] Drift por tool, review e stale — deps: F05 — US: US-007, US-008, US-010 — sec: auth, input-validation, logs → F06.md
- [ ] F07 [AFK] Discovery adversarial limitada e observável — deps: F03, F06 — US: US-003, US-006, US-009 — sec: input-validation, rate-limit, logs, dados-sensiveis → F07.md
- [ ] F08 [HITL] Validação implantada de segurança e evidência — deps: F04, F06, F07 — US: US-002, US-006, US-009, US-010 — sec: auth, rate-limit, criptografia, logs, dados-sensiveis → F08.md

## Histórico

Log cronológico de revisões deste plano (mais antigo primeiro). Mantido por `sc-revisar`.

- (sem revisões ainda)
