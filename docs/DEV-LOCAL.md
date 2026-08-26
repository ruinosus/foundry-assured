# Rodar local — o que já funciona, o que falta e o que cada peça custa

> Levantado por medição em 2026-08-26, com o `apps/mcp` já no ar. Cada linha da tabela foi
> executada, não inferida.

## O que já funciona hoje, com zero Azure

`scripts/dev-nocloud.sh` sobe backend e frontend sem nuvem nenhuma. Os seams que tornam isso
possível já existiam:

- `InMemoryTrail`, `InMemoryConversationStore`, `InMemoryShareIndex` e `InMemoryTenantStore`
  entram sozinhos quando `AZURE_STORAGE_ACCOUNT` está vazio;
- `settings.auth_enabled` é falso sem as variáveis do Entra, e todo o produto degrada aberto —
  o mesmo caminho que o dev local sempre teve;
- o único requisito de boot é `FOUNDRY_PROJECT_ENDPOINT`, e um endpoint **sintático** basta: o
  SDK só recusa subir sem a variável; nada é chamado enquanto ninguém pedir inferência.

**O `apps/mcp` também sobe sem Azure** (medido): auth desligada, as três tools registradas, os
**10 prompts lidos do disco**, o template de resource e a extensão do selo.

## A tabela

| Peça | Local hoje | O que falta | Custo |
|---|:--:|---|---|
| Backend + frontend | ✅ | — | zero |
| MCP: listagem de tools, prompts, templates | ✅ | — | zero |
| MCP: os 10 prompts (AgentSchema) | ✅ | — | zero |
| MCP: selo de assurance, sessão, trilha | ✅ | — | zero (memória) |
| MCP: `open_ticket` | ⚠️ | `export MCP_REQUEST_STATE_KEY=$(openssl rand -hex 32)` | zero |
| MCP: tasks | ❌ | Redis local + `MCP_REDIS_URL` + `MCP_TASKS_ENCRYPTION_KEY` | zero (Docker) |
| MCP: `search_docs` | ❌ | índice do AI Search **ou** retriever local (ver abaixo) | ver abaixo |
| MCP: `document://` | ❌ | Blob **ou** leitura de disco | pequeno |
| Chat dos domínios (backend) | ❌ | projeto Foundry + `az login`, **ou** `npm run demo` | ver abaixo |

`open_ticket` sem a chave **recusa com a mensagem certa** — "é configuração do operador; tentar de
novo não resolve" — em vez de falhar obscuro. Com a chave exportada, escreve no `tickets.jsonl`
local.

## Redis, para as tasks — zero custo

```bash
docker run -d --name foundry-redis -p 6379:6379 redis:7-alpine
export MCP_REDIS_URL="redis://localhost:6379"
export MCP_TASKS_ENCRYPTION_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
```

As duas variáveis andam **juntas por desenho**: o snapshot da task carrega o access token do
chamador, e sem a chave ele iria ao armazenamento em JSON claro. Com só uma delas, o app se
recusa a ligar as tasks e diz por quê.

## `search_docs` — a decisão de verdade

Não existe retriever local no repositório. Os testes **monkeypatcham** `retrieve`; não há
`InMemorySearch`. Duas saídas, e elas não são equivalentes:

**(a) Um índice de verdade no AI Search.** O corpus são 13 markdowns em `knowledge/corpus/`;
`uv run python -m app.modules.knowledge.internal.ingest` monta o índice. O AI Search tem tier
gratuito — confirme os limites atuais, mas um corpus deste tamanho cabe folgado. É a opção que
**preserva o comportamento**, incluindo o trim de ACL por documento.

**(b) Um retriever local sobre `knowledge/corpus/`.** Uns 150 linhas: ler os markdowns, casar por
substring ou BM25 simples, devolver no formato `{index, source, url, snippet}` que o resto já
espera.

**O risco de (b), e é o motivo de eu não fazê-lo por conta própria:** o trim de ACL acontece
**dentro do Azure AI Search**, pelo header `x-ms-query-source-authorization` com o token OBO do
chamador (`retrieval.py:208-212`). Um retriever local não tem como reproduzir isso — ele
devolveria tudo. O local passaria a divergir da produção **exatamente na dimensão que o produto
existe para garantir**, e um bug de ACL deixaria de aparecer em dev.

Se (b) for feito, precisa vir com um aviso alto no boot e um gate que impeça o modo local de
existir com `auth_enabled` verdadeiro.

## Chat dos domínios

- **Com conta Azure:** `az login` mais um projeto Foundry com deployment de modelo. Não precisa
  provisionar nada com `azd` — o `DefaultAzureCredential` usa a sua sessão.
- **Sem conta:** `npm run demo` reproduz um fixture gravado do AG-UI (`apps/frontend/demo/fixtures`).
  Serve para ver a interface e o fluxo; não exercita modelo nem recuperação.

## O que NÃO tem caminho local hoje

- **API key em vez de credencial.** Não existe: `grep` por `AzureKeyCredential`, `api_key=` e
  `AZURE_OPENAI_API_KEY` no `app/` devolve zero. Tudo é `DefaultAzureCredential` ou OBO — é a
  regra 2 do `CLAUDE.md`. Ver [ADR-029](./adr/ADR-029-caminho-por-api-key.md).
