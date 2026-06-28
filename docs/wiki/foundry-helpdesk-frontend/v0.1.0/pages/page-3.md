# API / Endpoints (rotas do Next.js)

Abaixo estão as rotas de API e comportamentos que constam explicitamente nos arquivos fornecidos. Cada afirmação está ancorada nas linhas do arquivo citado.

## app/api/copilotkit/[[...slug]]/route.ts
- Arquivo implementa um handler compartilhado exportado como GET e POST através de `handle` (exportações `GET` e `POST`). (app/api/copilotkit/[[...slug]]/route.ts:62-72)
- Cria um `CopilotRuntime` com agentes nomeados `helpdesk`, `helpdesk-hosted` e `cockpit`. (app/api/copilotkit/[[...slug]]/route.ts:58-60)
- Define um `HttpAgent` `helpdesk` apontando para `AGUI_URL` e sobrescreve sua `fetch` para, quando o corpo for uma string JSON contendo `resume` como um array, transformar `resume` em `{ interrupts: [...] }` mapeando `interruptId`/`id` → `id` e `payload`/`value` → `value`. (app/api/copilotkit/[[...slug]]/route.ts:21,28-41)
- Define um `HttpAgent` `helpdeskHosted` com `HOSTED_AGUI_URL`. (app/api/copilotkit/[[...slug]]/route.ts:25-26,51)
- Define um `HttpAgent` `cockpit` com `COCKPIT_AGUI_URL`. (app/api/copilotkit/[[...slug]]/route.ts:55-56)
- Chama `copilotRuntimeNextJSAppRouterEndpoint` com o `runtime`, um `ExperimentalEmptyAdapter()` e `endpoint: "/api/copilotkit"`, e usa o `handleRequest` resultante para tratar as requisições. (app/api/copilotkit/[[...slug]]/route.ts:62-69,63-67)

## app/api/evals/route.ts
- O arquivo declara `dynamic = "force-dynamic"`. (app/api/evals/route.ts:6)
- Exporta um `GET` que busca `${BACKEND}/eval/foundry`, repassando o cabeçalho `Authorization` do pedido se presente. (app/api/evals/route.ts:8,10-16)
- Em caso de resposta não-ok do backend, retorna JSON `{ runs: [], error: \`backend ${r.status}\` }` com status 502; em caso de exceção de fetch, retorna `{ runs: [], error: "backend unreachable" }` com status 502. (app/api/evals/route.ts:17-23)
- `BACKEND` tem valor padrão `"http://localhost:8000"` quando `process.env.BACKEND_URL` não está definido. (app/api/evals/route.ts:8)
- Comentário no topo afirma que o arquivo "Proxies the backend's recorded eval runs ... Forwards the caller's Entra bearer token" (comentário de intenção presente no arquivo). (app/api/evals/route.ts:1-3)

## app/api/health/route.ts
- O arquivo declara `dynamic = "force-dynamic"`. (app/api/health/route.ts:5)
- Exporta um `GET` que busca `${BACKEND}/healthz` e retorna JSON `{ ok: r.ok }` com status `200` se `r.ok` for true, caso contrário status `502`. (app/api/health/route.ts:7,9-12)
- Em caso de exceção de fetch, retorna `{ ok: false }` com status 502. (app/api/health/route.ts:13-15)
- `BACKEND` tem valor padrão `"http://localhost:8000"` quando `process.env.BACKEND_URL` não está definido. (app/api/health/route.ts:7)
- Comentário no topo indica que este arquivo "Proxies the backend health check" (comentário de intenção presente no arquivo). (app/api/health/route.ts:1-2)

## app/api/tickets/route.ts
- O arquivo declara `dynamic = "force-dynamic"`. (app/api/tickets/route.ts:6)
- Exporta um `GET` que busca `${BACKEND}/tickets`, repassando o cabeçalho `Authorization` do pedido se presente. (app/api/tickets/route.ts:8,10-16)
- Em caso de resposta não-ok do backend, retorna JSON `{ tickets: [], error: \`backend ${r.status}\` }` com status 502; em caso de exceção de fetch, retorna `{ tickets: [], error: "backend unreachable" }` com status 502. (app/api/tickets/route.ts:17-23)
- `BACKEND` tem valor padrão `"http://localhost:8000"` quando `process.env.BACKEND_URL` não está definido. (app/api/tickets/route.ts:8)
- Comentário no topo indica que este arquivo "Proxies the real tickets ... Forwards the caller's Entra bearer token" (comentário de intenção presente no arquivo). (app/api/tickets/route.ts:1-3)

## lib/auth/api.ts
- Arquivo contendo `"use client"` (diretiva de execução no cliente). (lib/auth/api.ts:1)
- Exporta `authedFetch(input, init)` que cria `Headers` a partir de `init.headers` e, se `authConfigured` e `msalInstance` estiverem definidos, tenta obter a conta com `msalInstance.getAllAccounts()[0]`. (lib/auth/api.ts:9,11-15)
- Se houver conta, tenta `msalInstance.acquireTokenSilent({ scopes: apiScopes, account })` e, em caso de sucesso, define o cabeçalho `Authorization: Bearer <token>` antes de chamar `fetch` com os headers resultantes. (lib/auth/api.ts:16-19,25)
- Se `acquireTokenSilent` falhar, o catch deixa de oferecer o token e a função prossegue para chamar `fetch` sem forçar um redirecionamento (o comentário explica o comportamento). (lib/auth/api.ts:19-22)
- Importa `apiScopes`, `authConfigured` e `msalInstance` de `@/lib/auth/msal`. (lib/auth/api.ts:9)

Observação: todas as declarações acima estão limitadas ao que aparece explicitamente nos arquivos fornecidos e estão referenciadas às linhas citadas. Informações que não constem desses arquivos foram removidas ou não foram incluídas.