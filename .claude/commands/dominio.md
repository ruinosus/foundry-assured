---
description: Adiciona um domínio (assistente) novo — os dois registries espelhados, o texto e o gate
argument-hint: "<id-do-dominio>"
allowed-tools: Read, Grep, Glob, Edit, Write, Bash(uv run --project apps/backend --no-sync python scripts/gates.py:*), Bash(cd apps/backend && uv run:*)
---

Adicione o domínio `$ARGUMENTS`. **Não improvise a forma** — leia os dois registries e copie a
estrutura de um domínio existente do mesmo `kind`.

## O contrato

Os dois registries são **espelhos**, e `tests.registry.domain_registry_test` guarda isso. Uma
linha só de um lado passa no seu teste local e quebra o gate.

| Onde | O quê |
|---|---|
| `apps/frontend/lib/domains.ts` | uma entrada: `id`, `kind`, `endpoint`, `framework`, `icon`, `surface` |
| `apps/backend/app/modules/domains/internal/catalog.py` | `DOMAIN_KINDS` + um `DomainSpec` em `domain_specs()` |
| `apps/frontend/messages/{en,pt-BR}.json` | **todo o texto**, sob `domains.<id>` |
| o agente | documento AgentSchema em `apps/backend/agents/assured/<id>.yaml` + KB, se `grounded` |

## Três armadilhas, todas com cicatriz no repo

1. **Texto não mora no `domains.ts`.** Rótulo, descrição e prompts sugeridos vão para
   `messages/<locale>.json`. O registry é importado pela rota do CopilotKit, que roda no servidor
   **sem contexto de idioma** — um campo de texto ali nasce numa língua só. `scripts/check-hardcoded-text.mjs`
   é o gate que impede a volta. Os **dois** locales, sempre.

2. **`DomainSpec` grounded precisa de `kb_name` OU `search_index`.** Sem um dos dois o fallback
   de retrieval bate em `.../indexes/None/docs/search`. O `__post_init__` reclama.

3. **`document_access` é DECLARADO, não derivado.** O default é o seguro (`"acl"`) de propósito:
   esquecer de declarar não pode rebaixar ninguém. Só use `"session"` com motivo escrito.

## Ordem

1. Leia `domains.ts` e `catalog.py` inteiros; escolha o domínio existente mais parecido.
2. Frontend: entrada no registry + as duas chaves de tradução.
3. Backend: `DOMAIN_KINDS` + `DomainSpec`.
4. Agente: o `.yaml` (a skill `prompt-change` cobre o resto) e, se `grounded`, a KB.
5. Verifique:
   ```bash
   uv run --project apps/backend --no-sync python scripts/gates.py -k 'registry|routes|hardcoded'
   ```
6. Rode `/gates` inteiro antes do PR.

Se o pedido não disser o `kind`, **pergunte** — `workflow`, `grounded`, `tool` e `graph` têm
montagens diferentes, e escolher errado só aparece no boot.
