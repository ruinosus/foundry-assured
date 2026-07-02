---
title: "O Quarto Domínio: Platform e Integração MCP"
description: "O concierge tool-driven sobre servidores MCP da Microsoft: o registry como dado, RBAC por ferramenta, build por requisição (self-hosted vs shared vs hosted), e a aprovação de escrita."
---

# O Quarto Domínio: Platform e Integração MCP

## Por que este domínio é diferente

Diferente dos experts grounded (cockpit/selfwiki), a capacidade do agente `platform` **é** o conjunto de ferramentas MCP first-party da Microsoft, montadas **por requisição** a partir de `app/agents/mcp/`. As ferramentas são filtradas por papel (Reader vê reads; Author/Admin veem writes) e, para servidores OBO, rodam como o usuário assinado ([apps/backend/app/agents/platform.py:1-10](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/platform.py#L1-L10)). No registry de domínios, é o único `kind: "tool"` ([apps/backend/app/domains.py:95](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/domains.py#L95)).

## Sumário

| Peça | Símbolo | Arquivo | Fonte |
|---|---|---|---|
| Catálogo de servidores (dado puro) | `SERVERS`, `McpServer` | `mcp/registry.py` | [apps/backend/app/agents/mcp/registry.py:24-116](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/registry.py#L24-L116) |
| Governança como dado | `visible_tools`, `classify_tool` | `mcp/registry.py` | [apps/backend/app/agents/mcp/registry.py:130-175](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/registry.py#L130-L175) |
| Build de ferramentas | `build_mcp_tools`, `build_from_connections`, `build_hosted_from_connections` | `mcp/tools.py` | [apps/backend/app/agents/mcp/tools.py:178-241](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/tools.py#L178-L241) |
| Agente + proxy | `build_platform_agent`, `platform_agent_proxy` | `agents/platform.py` | [apps/backend/app/agents/platform.py:31-56](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/platform.py#L31-L56) |

## O registry: governança como dado, não código

`app/agents/mcp/registry.py` é **puro** — sem rede, framework ou auth — então é unit-testável isolado. **Fail-closed:** uma tool que não está em NENHUMA lista é tratada como WRITE ([apps/backend/app/agents/mcp/registry.py:1-12](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/registry.py#L1-L12), [apps/backend/app/agents/mcp/registry.py:130-134](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/registry.py#L130-L134)).

| Servidor | `auth` | Habilitado? | Por quê | Fonte |
|---|---|---|---|---|
| `learn` | `public` | sim | endpoint público (Microsoft Learn) | [apps/backend/app/agents/mcp/registry.py:43-49](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/registry.py#L43-L49) |
| `azure` | `obo` | **não** | sem endpoint remoto gerenciado (stdio local) | [apps/backend/app/agents/mcp/registry.py:55-64](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/registry.py#L55-L64) |
| `entra` | `obo` | **não** | sem endpoint first-party remoto | [apps/backend/app/agents/mcp/registry.py:68-77](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/registry.py#L68-L77) |
| `azdo` | `obo` | sim | endpoint real (`{org}` por org) | [apps/backend/app/agents/mcp/registry.py:81-90](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/registry.py#L81-L90) |
| `github` | `github_pat` | sim | OAuth do GitHub (NÃO Entra OBO) | [apps/backend/app/agents/mcp/registry.py:98-105](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/registry.py#L98-L105) |
| `m365` | `oauth_passthrough` | **não** | endpoint a confirmar | [apps/backend/app/agents/mcp/registry.py:106-115](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/registry.py#L106-L115) |

O modelo de papéis é **flat** (não escada): `READ_ROLES` = Reader/Author/Approver/Admin; `WRITE_ROLES` = Author/Admin ([apps/backend/app/agents/mcp/registry.py:18-21](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/registry.py#L18-L21)). GitHub auth **não** é Entra OBO — GitHub rejeita audiência Microsoft, então usa PAT/OAuth próprio ([apps/backend/app/agents/mcp/registry.py:91-97](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/registry.py#L91-L97)).

## RBAC por ferramenta

```mermaid
flowchart TD
  A["caller roles"] --> B{"_granted(roles, min_role)?"}
  B -- sim --> C["reads = server.read_tools"]
  B -- nao --> D["reads = []"]
  A --> E{"_granted(roles, min_role_write)?"}
  E -- sim --> F["writes = server.write_tools"]
  E -- nao --> G["writes = []"]
  C --> H["allowed = reads + writes"]
  F --> H
  H --> I{"shared mode?"}
  I -- sim --> J["+ Connection.min_role tem de bater (stricter-of-both)"]
```

<!-- Sources: apps/backend/app/agents/mcp/registry.py:137-175 -->

`visible_tools(server, roles)` retorna `(reads, writes)` visíveis ao caller — sem papel vê nada (fail-closed) ([apps/backend/app/agents/mcp/registry.py:142-147](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/registry.py#L142-L147)). Em shared mode, `visible_tools_for(server, conn, roles)` aplica o **stricter-of-both**: a min-role do registry E a do `Connection` têm de ser satisfeitas — o tenant só aperta, nunca afrouxa ([apps/backend/app/agents/mcp/registry.py:158-175](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/registry.py#L158-L175)).

## Os três caminhos de build

`build_mcp_tools()` é **mode-aware**. Quando auth está off (dev local), trata o caller como Admin — senão o filtro de papel esconderia toda tool localmente ([apps/backend/app/agents/mcp/tools.py:223-241](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/tools.py#L223-L241)):

| Caminho | Quando | Função | Auth da tool | Fonte |
|---|---|---|---|---|
| Registry flat | self-hosted (default) | `_build_one` sobre `enabled_servers()` | header_provider OBO/PAT | [apps/backend/app/agents/mcp/tools.py:236-240](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/tools.py#L236-L240) |
| Connections (interno) | shared | `build_from_connections` → `_build_from_connection` | OBO ou Foundry-connection broker | [apps/backend/app/agents/mcp/tools.py:150-181](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/tools.py#L150-L181) |
| Connections (hosted) | hosted | `build_hosted_from_connections` via `get_tool` | `project_connection_id` (Foundry resolve) | [apps/backend/app/agents/mcp/tools.py:184-210](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/tools.py#L184-L210) |

A resolução RBAC + URL + approval compartilhada vive em **um lugar** — `_connection_build_params` — usado tanto pelo path interno quanto pelo hosted ([apps/backend/app/agents/mcp/tools.py:124-147](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/tools.py#L124-L147)).

## Aprovação de escrita: interno vs hosted

```mermaid
sequenceDiagram
  autonumber
  participant M as "Modelo"
  participant Int as "MCPStreamableHTTPTool (interno)"
  participant HITL as "Nosso card HITL"
  participant H as "get_mcp_tool (hosted)"
  Note over Int: approval_mode = "never_require"
  M->>Int: chama tool
  Int->>HITL: escrita gated pelo NOSSO card (não pelo MCP nativo)
  Note over H: approval_mode = {always_require: writes, never_require: reads}
  M->>H: chama tool
  H-->>M: aprovação nativa round-trips no path hosted (Invocations)
```

<!-- Sources: apps/backend/app/agents/mcp/tools.py:1-18, apps/backend/app/agents/mcp/tools.py:143-147 -->

No path **interno** o `approval_mode="never_require"` porque a aprovação MCP nativa NÃO executa sobre AG-UI (agent-framework #3199), então a escrita é tratada pelo nosso card HITL — mas a **visibilidade** de write continua gated por papel ([apps/backend/app/agents/mcp/tools.py:1-18](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/tools.py#L1-L18)). No path **hosted/connection**, o `approval_mode` é um dict que marca `always_require_approval` para writes e `never_require_approval` para reads ([apps/backend/app/agents/mcp/tools.py:143-147](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/mcp/tools.py#L143-L147)). Por isso a ponte `/platform-hosted` usa **Invocations** — ver [Registry de Domínios e mount_domains](./page-4.md#pontes-hosted-so-duas-restam).

## O agente e o proxy

`build_platform_agent()` cria um `FoundryChatClient` com `credential_for_request()` (OBO) e chama `client.as_agent(... tools=build_mcp_tools())` ([apps/backend/app/agents/platform.py:31-44](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/platform.py#L31-L44)). O `_mount_platform` do registry serve o `platform_agent_proxy` — um `PerRequestAgent` que **reconstrói** o agente a cada `.run()`, para cada requisição obter tools filtradas pelos papéis + OBO do caller ATUAL ([apps/backend/app/agents/platform.py:47-56](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/platform.py#L47-L56), [apps/backend/app/domains.py:149-161](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/domains.py#L149-L161)). Só é montado quando `platform_configured()` retorna verdadeiro (em shared, gated por `mcp_enabled` global) ([apps/backend/app/agents/platform.py:25-28](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/platform.py#L25-L28)).

As `PLATFORM_INSTRUCTIONS` impõem: preferir tool a chute, fundamentar em resultados de tool, e **nunca alegar que executou uma escrita** ([apps/backend/app/agents/prompts.py:139-144](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/apps/backend/app/agents/prompts.py#L139-L144)).

## Related Pages

| Página | Relação |
|------|-------------|
| [Modos de Implantação e o Seam de Tenant](./page-2.md) | `Connection` e o tenant store que alimenta os builds shared |
| [Autenticação, OBO e RBAC](./page-3.md) | `current_roles`/`credential_for_request` que filtram as tools |
| [Registry de Domínios e mount_domains](./page-4.md) | `_mount_platform` e a ponte `/platform-hosted` (Invocations) |
| [Domínios de Agente e Workflow](./page-5.md) | `PerRequestAgent`, reusado aqui |
