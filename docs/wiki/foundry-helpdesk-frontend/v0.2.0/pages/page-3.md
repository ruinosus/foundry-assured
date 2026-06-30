---
title: "O Registry de Domínios e o Runtime CopilotKit"
description: "Como lib/domains.ts dirige tudo e como o runtime CopilotKit roteia cada domínio para o seu agente AG-UI, incluindo o resume-bridge da HITL."
---

# O Registry de Domínios e o Runtime CopilotKit

## A ideia central (first principles)

O insight de arquitetura do frontend cabe em uma frase: **um array é o sistema de configuração**. Cada `Domain` em `DOMAINS` é simultaneamente: um agente no runtime, um item de nav, um role-card, um conjunto de prompts e — se tiver `hostedAgentId` — um toggle Live/Hosted. A consequência prática é que *não há wiring por-domínio espalhado*; tudo deriva do registry [lib/domains.ts:1-6](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/lib/domains.ts#L1-L6).

## A forma de um Domain

```ts
// Pseudocódigo da interface (lido em lib/domains.ts)
interface Domain {
  id: string;            // == agentId backend + segmento do path AG-UI
  icon: string;
  label: string;
  kind: "workflow" | "grounded" | "tool";
  blurb: string;
  suggested: string[];   // chips de prompt inicial
  endpoint: string;      // path AG-UI default
  hostedAgentId?: string; // habilita o toggle live/hosted
}
```

Campos e seus papéis [lib/domains.ts:8-26](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/lib/domains.ts#L8-L26):

| Campo | Dirige | Onde é consumido |
|---|---|---|
| `id` | agentId no runtime + `agentId` do `CopilotChat` | [route.ts:73](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/app/api/copilotkit/%5B%5B...slug%5D%5D/route.ts#L73), [AssuranceConsole.tsx:37](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/components/console/AssuranceConsole.tsx#L37) |
| `kind` | tipo de agente no runtime + UI condicional | [route.ts:75-78](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/app/api/copilotkit/%5B%5B...slug%5D%5D/route.ts#L75-L78) |
| `endpoint` | URL AG-UI default | [route.ts:66](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/app/api/copilotkit/%5B%5B...slug%5D%5D/route.ts#L66) |
| `hostedAgentId` | renderiza o toggle Live/Hosted | [AssuranceConsole.tsx:69](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/components/console/AssuranceConsole.tsx#L69) |
| `suggested` | chips de SuggestedPrompts | [SuggestedPrompts.tsx:44-48](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/components/console/SuggestedPrompts.tsx#L44-L48) |

## O runtime CopilotKit — montando o mapa de agentes

A rota é um **catch-all** `[[...slug]]` de propósito: o cliente v2 chama sub-paths (`/api/copilotkit/agent/<id>/run`, sync), e um `route.ts` exato só casaria `/api/copilotkit` e daria 404 nas chamadas de agent-run [app/api/copilotkit/[[...slug]]/route.ts:1-5](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/app/api/copilotkit/%5B%5B...slug%5D%5D/route.ts#L1-L5).

O mapa `registryAgents` é construído a partir de `DOMAINS` com uma única regra: domínios `grounded` recebem um `HttpAgent` simples (request→response); domínios que carregam interrupções (`workflow` + `tool`) recebem o **resume-bridge** [app/api/copilotkit/[[...slug]]/route.ts:72-79](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/app/api/copilotkit/%5B%5B...slug%5D%5D/route.ts#L72-L79):

```ts
// route.ts (lido)
const registryAgents = Object.fromEntries(
  DOMAINS.map((d) => [
    d.id,
    d.kind === "grounded"
      ? new HttpAgent({ url: urlFor(d) })
      : withResumeBridge(d.id === "helpdesk" ? AGUI_URL : urlFor(d)),
  ]),
);
```

A URL de cada domínio admite override por env var `<ID>_AGUI_URL` (ex.: `COCKPIT_AGUI_URL`, `PLATFORM_AGUI_URL`), caindo para `http://localhost:8000<endpoint>` [app/api/copilotkit/[[...slug]]/route.ts:65-66](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/app/api/copilotkit/%5B%5B...slug%5D%5D/route.ts#L65-L66).

Aos agentes do registry, somam-se os **twins hospedados**: `helpdesk-hosted` (um `HttpAgent` puro, sem interrupts) e `platform-hosted` (com resume-bridge, porque carrega o write-approval) [app/api/copilotkit/[[...slug]]/route.ts:84-88](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/app/api/copilotkit/%5B%5B...slug%5D%5D/route.ts#L84-L88).

```mermaid
graph TD
  DOM["DOMAINS[]"] --> MAP{"d.kind"}
  MAP -->|grounded| HA["HttpAgent simples"]
  MAP -->|workflow / tool| RB["withResumeBridge"]
  HA --> AG["registryAgents"]
  RB --> AG
  AG --> RT["CopilotRuntime.agents"]
  HH["helpdesk-hosted<br>HttpAgent puro"] --> RT
  PH["platform-hosted<br>resume-bridge"] --> RT
  RT --> EP["copilotRuntimeNextJSAppRouterEndpoint<br>GET/POST"]

  classDef d fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  class DOM,MAP,HA,RB,AG,RT,HH,PH,EP d
```
<!-- Sources: app/api/copilotkit/[[...slug]]/route.ts:61-101 -->

## Por que o resume-bridge existe

Há um descasamento de formato entre as duas pontas: o runtime CopilotKit valida `resume` como um **array** (forma do cliente AG-UI, `[{ interruptId, status, payload }]`), mas o backend agent-framework espera um **dict** (`{ interrupts: [{ id, value }] }`) [app/api/copilotkit/[[...slug]]/route.ts:7-11](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/app/api/copilotkit/%5B%5B...slug%5D%5D/route.ts#L7-L11).

`withResumeBridge` sobrescreve o `fetch` do `HttpAgent` para traduzir o corpo logo antes de bater no backend [app/api/copilotkit/[[...slug]]/route.ts:36-59](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/app/api/copilotkit/%5B%5B...slug%5D%5D/route.ts#L36-L59):

```mermaid
sequenceDiagram
  autonumber
  participant UI as TicketApproval
  participant RT as CopilotRuntime
  participant BR as withResumeBridge.fetch
  participant BE as Backend AG-UI
  UI->>RT: runAgent({ resume: [ {interruptId,status,payload} ] })
  RT->>BR: POST body (resume = ARRAY)
  BR->>BR: se Array.isArray(body.resume): mapear
  BR->>BE: POST body (resume = { interrupts: [{id,value}] })
  BE-->>UI: workflow retomado (SSE)
```
<!-- Sources: app/api/copilotkit/[[...slug]]/route.ts:36-59, components/chat/TicketApproval.tsx:100-104 -->

> **Inferência (marcada):** o `helpdesk-hosted` usa `HttpAgent` puro porque o caminho hospedado é request→response sem interrupts — o comentário no código afirma isso explicitamente [app/api/copilotkit/[[...slug]]/route.ts:23-25](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/app/api/copilotkit/%5B%5B...slug%5D%5D/route.ts#L23-L25), enquanto `platform-hosted` precisa do bridge por carregar o write-approval [app/api/copilotkit/[[...slug]]/route.ts:29-32](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/app/api/copilotkit/%5B%5B...slug%5D%5D/route.ts#L29-L32).

## Adicionar um 5º domínio (receita)

1. Adicione uma entrada em `DOMAINS` (`id`, `kind`, `endpoint`, etc.) [lib/domains.ts:28](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/lib/domains.ts#L28).
2. Suba o agente correspondente no backend no path `endpoint`.
3. Pronto — nav, landing, `/d/<id>`, runtime e prompts pegam de graça (`getDomain` resolve o id) [lib/domains.ts:88-89](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/frontend/lib/domains.ts#L88-L89).

## Related Pages

| Página | Relação |
|------|-------------|
| [Visão Geral](page-1.md) | Tabela dos 4 domínios |
| [Assurance Console](page-4.md) | Onde o toggle Live/Hosted é renderizado |
| [Human-in-the-loop](page-5.md) | O `runAgent({ resume })` que o bridge traduz |
| [Arquitetura e Stack](page-2.md) | A ponte AG-UI no contexto geral |
