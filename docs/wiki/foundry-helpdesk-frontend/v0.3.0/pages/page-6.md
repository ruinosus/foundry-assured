---
title: "Admin e Multi-tenancy — Users, Connections e Proxies"
description: "A UI de tenant/onboarding da linha SaaS: gestão de usuários e papéis via Graph, configuração de data-plane e conexões, tudo passando por proxies que mantêm os segredos no backend."
---

# Admin e Multi-tenancy — Users, Connections e Proxies

## O princípio: a UI nunca segura segredos

Toda a área admin é **camada de conveniência sobre o backend**. O browser nunca chama o Graph nem o Azure direto; ele chama proxies Next que **encaminham o bearer token Entra** do usuário para o FastAPI, que detém as credenciais app-only e re-gateia cada chamada server-side pelo papel **Admin** [apps/frontend/components/admin/Connections.tsx:3-6](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/admin/Connections.tsx#L3-L6), [apps/frontend/components/admin/AdminUsers.tsx:3-5](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/admin/AdminUsers.tsx#L3-L5).

```mermaid
graph LR
  subgraph br["Browser (Admin UI)"]
    CONN["Connections.tsx"]
    USERS["AdminUsers.tsx"]
  end
  subgraph nx["Next proxies"]
    PT["/api/tenant/[...path]"]
    PA["/api/admin/[...path]"]
  end
  subgraph be["Backend"]
    BT["/tenant/*"]
    BA["/admin/* (Graph app-only)"]
  end
  CONN -->|authedFetch| PT --> BT
  USERS -->|authedFetch| PA --> BA

  classDef d fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  class CONN,USERS,PT,PA,BT,BA d
```
<!-- Sources: apps/frontend/components/admin/Connections.tsx:8-9, apps/frontend/app/api/tenant/[...path]/route.ts:9-19, apps/frontend/app/api/admin/[...path]/route.ts:9-19 -->

## Visibilidade no nav (gate de UI)

Os itens `Admin` e `Connections` só aparecem na sidebar para o papel Admin; o gate real é server-side em cada endpoint [apps/frontend/components/shell/AppShell.tsx:100-102](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/shell/AppShell.tsx#L100-L102). Os papéis vêm de `/api/me` via `useMyRoles` [apps/frontend/lib/auth/roles.ts:10-23](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/lib/auth/roles.ts#L10-L23), e `isAdmin` testa `roles.includes("Admin")` [apps/frontend/lib/auth/roles.ts:25](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/lib/auth/roles.ts#L25). Cada página admin repete o gate: enquanto `roles===null` mostra "Loading…", se não-admin mostra um card pedindo o papel [apps/frontend/app/admin/connections/page.tsx:16-27](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/app/admin/connections/page.tsx#L16-L27).

## Connections — onboarding + data-plane + conexões

`Connections.tsx` é o coração da multi-tenancy do frontend. Os campos do data-plane e a lista de conexões são servidos por `/api/tenant/*`. As constantes de UI (tipos e papéis) são listas fixas [apps/frontend/components/admin/Connections.tsx:11-12](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/admin/Connections.tsx#L11-L12):

| Constante | Valores | Fonte |
|---|---|---|
| `KINDS` | github, azdo, azure, entra, learn, m365 | [Connections.tsx:11](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/admin/Connections.tsx#L11) |
| `ROLES` | Reader, Author, Approver, Admin | [Connections.tsx:12](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/admin/Connections.tsx#L12) |

### Data-plane configurável

Os campos do data-plane são o endpoint do projeto Foundry, o modelo, o endpoint do Azure Search e a knowledge base — exatamente o que torna o backend apontável para o data-plane de cada tenant [apps/frontend/components/admin/Connections.tsx:14-20](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/admin/Connections.tsx#L14-L20).

### Conexões: nunca o segredo, sempre a referência

Uma conexão referencia um `foundry_connection_id` **ou** um `keyvault_ref` — nunca o valor do segredo [apps/frontend/components/admin/Connections.tsx:21-30](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/admin/Connections.tsx#L21-L30). O aviso no rodapé reforça: o segredo vive no Foundry/Key Vault, aqui só vai a referência.

```mermaid
sequenceDiagram
  autonumber
  participant A as Admin
  participant C as Connections.tsx
  participant P as "/api/tenant proxy"
  participant B as "backend /tenant"
  A->>C: abre /admin/connections
  C->>P: GET /tenant
  P->>B: GET /tenant (Bearer)
  B-->>C: { onboarded, record }
  alt não onboarded e can_onboard
    A->>C: clica "Onboard tenant"
    C->>P: POST /tenant/onboard
  end
  A->>C: salva data plane
  C->>P: PUT /tenant/config { foundry_*, azure_search_* }
  A->>C: adiciona conexão
  C->>P: POST /tenant/connections { kind, label, ref, roles }
```
<!-- Sources: apps/frontend/components/admin/Connections.tsx:8-30, apps/frontend/app/api/tenant/[...path]/route.ts:9-33 -->

## AdminUsers — usuários + papéis via Graph

`AdminUsers.tsx` faz o lifecycle de usuários (invite guest / create member / remove) e a atribuição de papéis, tudo via `/api/admin/*` [apps/frontend/components/admin/AdminUsers.tsx:3-5](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/admin/AdminUsers.tsx#L3-L5). Os papéis disponíveis vêm do próprio backend (`GET /admin/roles`) — _"the app owns the roles; your company maps its groups onto them"_.

| Ação | Endpoint (via proxy) | Fonte |
|---|---|---|
| Listar usuários / atribuições / papéis | `GET users` / `role-assignments` / `roles` | [AdminUsers.tsx:40-54](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/admin/AdminUsers.tsx#L40-L54) |
| Atribuir / revogar papel | `POST` / `DELETE role-assignments` | [AdminUsers.tsx:40-54](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/admin/AdminUsers.tsx#L40-L54) |
| Convidar guest / criar member / remover | `POST users/invite` / `POST users` / `DELETE users/{id}` | [AdminUsers.tsx:40-54](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/components/admin/AdminUsers.tsx#L40-L54) |

## Os proxies de tenant/admin (server-side)

Ambos os proxies são `[...path]` catch-all, `force-dynamic`, e seguem o mesmo padrão: pegam o `authorization`, montam a URL `${BACKEND}/<base>/<path>`, repassam o corpo em métodos não-GET/DELETE, e devolvem 502 se o backend estiver inalcançável [apps/frontend/app/api/tenant/[...path]/route.ts:6-33](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/app/api/tenant/[...path]/route.ts#L6-L33). A diferença é só o segmento base (`/tenant/` vs `/admin/`) e os verbos suportados — `tenant` adiciona `PUT` (para `/config`) [apps/frontend/app/api/tenant/[...path]/route.ts:42-47](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/app/api/tenant/[...path]/route.ts#L42-L47).

## O domínio platform (tool) e o toggle

O 4º domínio, `platform`, é o lado de runtime da multi-tenancy: `kind: "tool"`, endpoint `/platform`, twin `platform-hosted` [apps/frontend/lib/domains.ts:77-91](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/lib/domains.ts#L77-L91). Por ser `tool`, ele recebe o resume-bridge no runtime (write-approval) [apps/frontend/app/api/copilotkit/[[...slug]]/route.ts:71-78](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/frontend/app/api/copilotkit/[[...slug]]/route.ts#L71-L78) e o card de aprovação de tool descrito em [Human-in-the-loop](page-5.md). Junto com `helpdesk`, é um dos **dois únicos** domínios que ainda declaram `hostedAgentId` (os grounded largaram os twins na v0.3.0).

## Related Pages

| Página | Relação |
|------|-------------|
| [Autenticação Entra](page-7.md) | `authedFetch`, `useMyRoles`, o gate de Admin |
| [Human-in-the-loop](page-5.md) | A aprovação de write-tool do domínio platform |
| [Registry e Runtime](page-3.md) | Como `platform`/`platform-hosted` entram no runtime |
| [Visão Geral](page-1.md) | O que mudou na linha grounded |
