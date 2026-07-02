---
title: "Autenticação Entra (MSAL) e os Proxies de API"
description: "Como o frontend faz login Entra com MSAL, encaminha o access token para o backend (OBO), gateia o app inteiro atrás do sign-in, e mantém a URL do backend fora do browser via proxies."
---

# Autenticação Entra (MSAL) e os Proxies de API

## O modelo: SPA token → backend OBO

O frontend não fala com Graph/Azure direto. Ele faz o usuário **consentir um único escopo** (`api://<apiClientId>/access_as_user`) e encaminha o access token resultante ao backend, que faz o **OBO (on-behalf-of) server-side**. A configuração lê apenas vars `NEXT_PUBLIC_`; na ausência delas a app roda sem auth, espelhando o fallback `DefaultAzureCredential` do backend [apps/frontend/lib/auth/msal.ts:3-18](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/lib/auth/msal.ts#L3-L18).

| Variável | Papel | Fonte |
|---|---|---|
| `NEXT_PUBLIC_ENTRA_TENANT_ID` | authority | [apps/frontend/lib/auth/msal.ts:9](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/lib/auth/msal.ts#L9) |
| `NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID` | clientId da SPA | [apps/frontend/lib/auth/msal.ts:10](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/lib/auth/msal.ts#L10) |
| `NEXT_PUBLIC_ENTRA_API_CLIENT_ID` | id da API (monta o scope) | [apps/frontend/lib/auth/msal.ts:11](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/lib/auth/msal.ts#L11) |

`authConfigured` é `true` só quando **as três** existem e não está em demo mode [apps/frontend/lib/auth/msal.ts:13-15](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/lib/auth/msal.ts#L13-L15). A `msalInstance` (`PublicClientApplication`) só é construída no browser (toca `window`/`crypto`); no servidor fica `null` [apps/frontend/lib/auth/msal.ts:34-38](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/lib/auth/msal.ts#L34-L38).

## O sign-in wall (AuthGate)

```mermaid
graph TD
  P["Providers"] --> Q{"authConfigured?"}
  Q -->|não| PASS["render direto (children)"]
  Q -->|sim| R{"msal ready?"}
  R -->|não| SPL["splash Loading…"]
  R -->|sim| MP["MsalProvider"]
  MP --> AGT{"isAuthenticated?"}
  AGT -->|não| LS["LoginScreen (app inteiro)"]
  AGT -->|sim| APP["children (shell + rotas)"]

  classDef d fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  class P,Q,PASS,R,SPL,MP,AGT,LS,APP d
```
<!-- Sources: apps/frontend/components/shell/Providers.tsx:21-56 -->

Quando não autenticado, `AuthGate` renderiza **somente** a `LoginScreen` — o shell e as rotas nunca montam, então nada é alcançável sem login [apps/frontend/components/shell/Providers.tsx:21-25](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/shell/Providers.tsx#L21-L25). MSAL é hoisteado para o app todo porque o redirect URI é a origem `/` (a Overview, que não tem chat mas precisa consumir a resposta de auth) [apps/frontend/components/shell/Providers.tsx:3-7](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/shell/Providers.tsx#L3-L7).

## Aquisição e renovação do token (chat)

Tanto `AssuranceConsole` quanto `HelpdeskApp` seguem o mesmo padrão: `acquireTokenSilent` no mount, fallback para `acquireTokenRedirect`, e um `setInterval` que **renova a cada 4 min** — caso contrário o chat OBO 401-a silenciosamente ao expirar (~1h) [apps/frontend/components/chat/HelpdeskApp.tsx:109-127](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/chat/HelpdeskApp.tsx#L109-L127), [apps/frontend/components/console/AssuranceConsole.tsx:116-133](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/console/AssuranceConsole.tsx#L116-L133). O token vira o header `Authorization: Bearer <token>` no `CopilotKitProvider` [apps/frontend/components/console/AssuranceConsole.tsx:40-43](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/console/AssuranceConsole.tsx#L40-L43).

```mermaid
sequenceDiagram
  autonumber
  participant U as Usuário
  participant M as MSAL
  participant C as AuthedConsole
  participant K as CopilotKitProvider
  participant B as "Backend (OBO)"
  U->>M: loginRedirect(scopes)
  M-->>C: account
  C->>M: acquireTokenSilent(apiScopes)
  M-->>C: accessToken
  C->>K: headers: Authorization Bearer
  K->>B: runs do agente (token encaminhado)
  loop a cada 4 min
    C->>M: acquireTokenSilent (refresh)
  end
```
<!-- Sources: apps/frontend/components/console/AssuranceConsole.tsx:116-146 -->

## authedFetch — o cliente para os proxies

Chamadas REST (admin, tenant, me, evals, tickets) usam `authedFetch`, que anexa o token via a singleton `msalInstance` (sem hook React, então funciona de qualquer client component). Em dev (`authConfigured=false`) degrada para `fetch` puro [apps/frontend/lib/auth/api.ts:11-26](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/lib/auth/api.ts#L11-L26). Se não houver token silencioso, envia sem auth e deixa o chamador tratar o 401 — não força redirect [apps/frontend/lib/auth/api.ts:18-22](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/lib/auth/api.ts#L18-L22).

## Os proxies de API (tabela)

Todos os proxies são server-side (`route.ts`), `force-dynamic`, e existem por dois motivos: **sem CORS** e **a URL do backend fica fora do browser** [apps/frontend/app/api/me/route.ts:5-6](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/app/api/me/route.ts#L5-L6).

| Rota | Backend | Encaminha token? | Fonte |
|---|---|---|---|
| `/api/copilotkit/[[...slug]]` | `/helpdesk`, `/cockpit`, … (AG-UI) | sim (header do provider) | [route.ts:96-103](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/app/api/copilotkit/[[...slug]]/route.ts#L96-L103) |
| `/api/tenant/[...path]` | `/tenant/*` | sim | [route.ts:9-19](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/app/api/tenant/[...path]/route.ts#L9-L19) |
| `/api/admin/[...path]` | `/admin/*` | sim | [route.ts:9-19](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/app/api/admin/[...path]/route.ts#L9-L19) |
| `/api/me` | `/me` (identidade + roles) | sim | [route.ts:8-18](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/app/api/me/route.ts#L8-L18) |
| `/api/evals` | `/eval/foundry` | sim | [route.ts:10-23](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/app/api/evals/route.ts#L10-L23) |
| `/api/tickets` | `/tickets` | sim | [route.ts:10-23](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/app/api/tickets/route.ts#L10-L23) |
| `/api/health` | `/healthz` | não | [route.ts:9-15](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/app/api/health/route.ts#L9-L15) |

A URL do backend cai para `http://localhost:8000` quando `BACKEND_URL` não está setada [apps/frontend/app/api/me/route.ts:6](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/app/api/me/route.ts#L6).

## O dot de status do backend

O `AppShell` checa `/api/health` no mount e mostra um dot verde/vermelho ("backend online/offline") — sem CORS nem URL exposta [apps/frontend/components/shell/AppShell.tsx:39-57](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/shell/AppShell.tsx#L39-L57).

## Related Pages

| Página | Relação |
|------|-------------|
| [Admin e Multi-tenancy](page-6.md) | Quem consome `authedFetch` e os proxies |
| [Assurance Console](page-4.md) | O chat que encaminha o Bearer token |
| [Arquitetura e Stack](page-2.md) | Os Providers e o fluxo SSR/CSR |
| [Registry e Runtime](page-3.md) | O proxy `/api/copilotkit` em detalhe |
