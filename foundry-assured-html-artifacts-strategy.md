# Estratégia para geração, armazenamento e exibição de HTMLs no `foundry-assured`

## 1. Contexto

Com a evolução das LLMs, a criação de HTMLs para apresentações, relatórios, dashboards narrativos, brainstormings e artefatos executivos ficou muito mais rápida. HTML deixou de ser apenas um formato de página web tradicional e passou a funcionar como um **artefato visual gerável por IA**.

A pergunta central analisada foi:

> Considerando que o repositório `ruinosus/foundry-assured` já possui infraestrutura Azure via Bicep/`azd`, frontend Next.js, backend Python/FastAPI, agentes, Entra e deploy em Azure Container Apps, qual seria a melhor opção para exibir HTMLs gerados por IA?

---

## 2. Pesquisa inicial: opções Microsoft para HTMLs/apresentações/relatórios web

A Microsoft não possui, pelo menos como produto central, algo exatamente como um **“HTML Deck Manager”** ou um **“PowerPoint baseado em HTML gerado por IA”**. Porém, ela possui várias peças que resolvem partes do problema.

### 2.1 Microsoft Sway

O Microsoft Sway é uma ferramenta para criação de apresentações, relatórios, newsletters e histórias interativas em formato web.

**Encaixe:**

- apresentações visuais simples;
- relatórios narrativos;
- newsletters internas;
- storytelling visual;
- conteúdo web sem backend próprio.

**Limitação:**

Sway é mais um editor/produto final de conteúdo do que uma plataforma para armazenar, versionar e distribuir HTML customizado gerado por LLM.

Fonte consultada:

- https://sway.cloud.microsoft

---

### 2.2 SharePoint Pages

SharePoint é a plataforma Microsoft mais comum para intranet, comunicação corporativa, portais internos e publicação governada de conteúdo.

Ele permite páginas modernas, web parts, embeds e integração com Microsoft 365. Porém, SharePoint moderno não é ideal para executar HTML/JS arbitrário gerado por IA, principalmente por segurança e governança.

**Encaixe:**

- portal corporativo;
- publicação interna;
- descoberta de conteúdo;
- distribuição de links e páginas;
- comunicação institucional.

**Limitação:**

Não é a melhor opção para “colar qualquer HTML com CSS/JS livre”. Para customização séria, normalmente se usa SharePoint Framework, não HTML solto.

Fontes consultadas:

- https://support.microsoft.com/en-us/sharepoint/sites-pages/add-content-to-your-page-using-the-embed-web-part
- https://support.microsoft.com/en-us/sharepoint/sites-pages/allow-or-restrict-the-ability-to-embed-content-on-sharepoint-pages

---

### 2.3 Azure Static Web Apps

Azure Static Web Apps é um serviço para hospedar sites/apps estáticos ou full-stack, com integração com GitHub/Azure DevOps, deploy automatizado, SSL, domínio customizado e suporte a autenticação/autorização.

**Encaixe:**

- HTML/CSS/JS gerado por IA;
- microsites;
- apresentações independentes;
- relatórios navegáveis publicados por link;
- artefatos versionados por Git;
- páginas estáticas com assets.

**Limitação no contexto do `foundry-assured`:**

Seria um **segundo frontend/plataforma de hosting**. Como o repositório já possui um frontend Next.js em Azure Container Apps, adicionar Azure Static Web Apps agora aumentaria a superfície operacional: auth, domínio, deploy, roteamento e governança duplicados.

Fonte consultada:

- https://learn.microsoft.com/en-us/azure/static-web-apps/overview

---

### 2.4 Power Pages

Power Pages permite criar sites empresariais low-code com identidade, dados, Dataverse, formulários e customizações com HTML/CSS/Liquid/JavaScript.

**Encaixe:**

- portais internos/externos;
- experiências com autenticação;
- sites corporativos;
- formulários e dados do Dataverse;
- governança Power Platform.

**Limitação:**

Pode ser pesado demais para o caso de uso de simples artefatos HTML gerados por IA dentro de um produto já existente.

Fontes consultadas:

- https://learn.microsoft.com/en-us/power-pages/configure/create-code-sites
- https://learn.microsoft.com/en-us/power-pages/configure/visual-studio-code-editor

---

### 2.5 Azure Blob Storage Static Website

Azure Storage permite hospedar sites estáticos usando o recurso Static Website. É barato e simples para HTML/CSS/JS estático.

**Encaixe:**

- HTML público;
- landing pages simples;
- relatórios sem controle de acesso;
- artefatos estáticos baratos.

**Limitação crítica:**

O recurso Static Website do Azure Storage serve conteúdo de forma anônima e não oferece AuthN/AuthZ próprio. Para conteúdo interno, tenant-aware, com RBAC ou controle por usuário, ele não deve ser a camada principal de exibição.

Fonte consultada:

- https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blob-static-website

---

## 3. Evidências do repositório `ruinosus/foundry-assured`

A análise do repositório mostrou que ele já possui uma base muito adequada para incorporar um fluxo de geração e exibição de HTMLs.

### 3.1 Natureza do produto

O README descreve o `foundry-assured` como um concierge interno de suporte de engenharia e showcase Microsoft Foundry. Ele inclui base de conhecimento aterrada, workflow multiagente com streaming, memória por usuário, human-in-the-loop, avaliação offline e hosted-agent deployment.

O frontend é **CopilotKit + Next.js**, comunicando com backend Python via **AG-UI**.

Trecho relevante do README:

```text
An internal engineering support concierge — a Microsoft Foundry showcase...
The frontend is CopilotKit (Next.js) talking to a Python backend over the AG-UI protocol.
```

Origem no repositório:

- `README.md`, linhas 5–9.

---

### 3.2 Deploy atual

O guia de deploy mostra que a infraestrutura é criada via `azd up` e Bicep.

Os principais recursos provisionados incluem:

- Foundry account + project + models;
- Azure AI Search;
- Storage account;
- Azure Container Registry;
- Container Apps Environment;
- RBAC;
- backend + frontend em Azure Container Apps.

Origem no repositório:

- `docs/DEPLOYMENT.md`, linhas 47–56;
- `docs/DEPLOYMENT.md`, linhas 74–84.

---

### 3.3 Frontend e backend já publicados em Azure Container Apps

O guia de deployment possui uma etapa específica para publicar backend + frontend em Azure Container Apps.

Origem no repositório:

- `docs/DEPLOYMENT.md`, Step 7, linhas 20–37 da segunda parte consultada.

O arquivo `azure.yaml` confirma dois serviços principais:

```yaml
services:
  backend:
    project: apps/backend
    host: containerapp
    language: docker

  web:
    project: apps/frontend
    host: containerapp
    language: docker
```

Origem no repositório:

- `azure.yaml`, linhas 8–15;
- `azure.yaml`, linhas 64–74.

---

### 3.4 Bicep de Container Apps

O arquivo `infra/containerapps.bicep` define:

- backend Container App;
- web Container App;
- ingress externo;
- uso de identidade gerenciada;
- comunicação entre frontend e backend por FQDN;
- scale-to-zero;
- Azure Files para persistência de dados de tickets.

Origem no repositório:

- `infra/containerapps.bicep`, linhas 95–100;
- `infra/containerapps.bicep`, linhas 100–163;
- `infra/containerapps.bicep`, linhas 165–207.

---

### 3.5 Domínios configuráveis no frontend

O arquivo `apps/frontend/lib/domains.ts` mostra que o frontend já usa um registry de domínios.

Ele diz explicitamente que o registry dirige:

- agent map;
- sidebar nav;
- rota genérica `/d/[domain]`;
- landing cards;
- prompts sugeridos.

Também diz que adicionar um domínio equivale a adicionar uma entrada nesse arquivo e um backend agent.

Origem no repositório:

- `apps/frontend/lib/domains.ts`, linhas 3–8.

Domínios atuais:

- `helpdesk`;
- `cockpit`;
- `selfwiki`;
- `platform`.

Origem no repositório:

- `apps/frontend/lib/domains.ts`, linhas 30–94.

---

### 3.6 RBAC / App Roles

O guia de deploy define app roles no Entra:

- Admin;
- Author;
- Approver;
- Reader.

Isso combina diretamente com uma feature de HTML artifacts:

- Author cria/edita HTML;
- Approver aprova publicação;
- Reader visualiza;
- Admin governa tudo.

Origem no repositório:

- `docs/DEPLOYMENT.md`, linhas 154–170.

---

## 4. Opções consideradas para exibir HTMLs no contexto do repo

### Opção A — Azure Static Web Apps

**Descrição:**

Publicar cada HTML, ou conjunto de HTMLs, como site estático independente.

**Vantagens:**

- excelente para HTML/CSS/JS puro;
- CI/CD simples;
- custom domains;
- SSL;
- bom para microsites independentes.

**Desvantagens no `foundry-assured`:**

- cria uma segunda camada de frontend;
- duplica parte da preocupação de auth/roteamento;
- não aproveita totalmente o frontend Next.js já existente;
- pode fragmentar a experiência do produto.

**Quando usar:**

Quando os HTMLs virarem microsites independentes, públicos ou semi-independentes, com ciclo de vida próprio.

---

### Opção B — Azure Blob Static Website

**Descrição:**

Servir os HTMLs diretamente pelo endpoint estático do Storage.

**Vantagens:**

- barato;
- simples;
- adequado para conteúdo público;
- bom para demos rápidas.

**Desvantagens:**

- não é adequado para conteúdo com controle fino de acesso;
- autenticação/autorização não é nativa nesse modo;
- mais fraco para RBAC, tenant e governança.

**Quando usar:**

Para HTMLs públicos, sem informação sensível e sem necessidade de login.

---

### Opção C — SharePoint Pages

**Descrição:**

Distribuir ou incorporar HTMLs/páginas no SharePoint.

**Vantagens:**

- ótimo para intranet;
- governança Microsoft 365;
- descoberta corporativa;
- fácil compartilhamento interno.

**Desvantagens:**

- não é ideal para HTML/JS arbitrário gerado por IA;
- customização mais séria exige SPFx;
- menos aderente ao produto técnico já existente no repo.

**Quando usar:**

Como camada de distribuição/descoberta, apontando para os links oficiais do `foundry-assured`, não como runtime principal dos HTMLs.

---

### Opção D — Power Pages

**Descrição:**

Criar um portal Power Platform para exibir HTMLs e relatórios.

**Vantagens:**

- bom para portais empresariais;
- integração com Dataverse;
- segurança e governança Power Platform;
- low-code.

**Desvantagens:**

- potencialmente pesado para o caso;
- cria outra plataforma paralela;
- menos natural dado que o repo já tem frontend, backend, Bicep e deploy.

**Quando usar:**

Quando o objetivo for criar um portal de negócio em Power Platform, não uma feature dentro do produto existente.

---

### Opção E — Frontend Next.js atual + Backend FastAPI + Blob Storage

**Descrição:**

Gerar HTML via IA, armazenar o artefato em Blob Storage e exibir pelo próprio frontend Next.js do `foundry-assured`, usando backend para autorização, metadados e assinatura de acesso.

**Vantagens:**

- aproveita a arquitetura existente;
- mantém experiência unificada;
- usa Container Apps já provisionado;
- usa Storage já presente;
- usa Entra/RBAC já existente;
- permite versionamento e aprovação;
- facilita integração com agentes e AG-UI;
- evita criar outro produto/plataforma de hosting.

**Desvantagens:**

- exige implementar camada de segurança/sanitização;
- exige viewer adequado, preferencialmente com iframe sandbox;
- exige modelo de metadados e versionamento.

**Quando usar:**

É a melhor opção para o `foundry-assured` neste momento.

---

## 5. Recomendação final

A melhor opção para o repositório `foundry-assured` é:

> Manter a exibição dos HTMLs no próprio frontend Next.js hospedado em Azure Container Apps, armazenar os HTMLs gerados em Azure Blob Storage e servir/renderizar os artefatos por rotas autenticadas do backend/frontend, com RBAC, versionamento, aprovação e iframe sandbox.

---

## 6. Arquitetura proposta

```text
Usuário pede um relatório/apresentação
        ↓
Agente/LLM gera HTML
        ↓
Backend valida, sanitiza e persiste
        ↓
HTML vai para Azure Blob Storage
        ↓
Metadados ficam no backend
        ↓
Frontend Next.js exibe em rota autenticada
        ↓
Renderização isolada em iframe sandbox
```

### Diagrama lógico

```text
┌──────────────────────────────┐
│ Next.js Web / Container Apps │
│ /artifacts                   │
│ /artifacts/[id]/preview      │
└───────────────┬──────────────┘
                │
                │ Authenticated request
                ▼
┌──────────────────────────────┐
│ FastAPI Backend              │
│ - gera HTML via agente        │
│ - valida segurança            │
│ - aplica RBAC                 │
│ - assina URLs temporárias     │
└───────────────┬──────────────┘
                │
                ▼
┌──────────────────────────────┐
│ Azure Blob Storage           │
│ /html-artifacts/{tenant}/{id}│
│ index.html                   │
│ assets/*                     │
│ manifest.json                │
└──────────────────────────────┘
```

---

## 7. Modelo de produto sugerido

### 7.1 Novo domínio no frontend

Adicionar um domínio novo em `apps/frontend/lib/domains.ts`, por exemplo:

```ts
{
  id: "artifacts",
  icon: "🧩",
  label: "HTML Artifacts",
  kind: "tool",
  blurb: "Gere, aprove, versione e publique relatórios/apresentações HTML.",
  suggested: [
    "Crie uma apresentação HTML sobre a arquitetura do Foundry Assured",
    "Gere um relatório executivo dos últimos evals",
    "Monte um walkthrough visual do fluxo helpdesk"
  ],
  endpoint: "/artifacts"
}
```

---

### 7.2 Rotas sugeridas no frontend

```text
/artifacts
/artifacts/new
/artifacts/[id]
/artifacts/[id]/preview
/artifacts/[id]/versions
/artifacts/[id]/settings
```

---

### 7.3 Endpoints sugeridos no backend

```text
POST /artifacts/html/generate
GET  /artifacts/html
GET  /artifacts/html/{id}
GET  /artifacts/html/{id}/content
GET  /artifacts/html/{id}/versions
POST /artifacts/html/{id}/approve
POST /artifacts/html/{id}/publish
POST /artifacts/html/{id}/archive
DELETE /artifacts/html/{id}
```

---

### 7.4 Modelo de metadados

Exemplo de `manifest.json` ou registro equivalente:

```json
{
  "id": "artifact_123",
  "tenantId": "tenant_abc",
  "title": "Foundry Assured Executive Overview",
  "description": "Apresentação HTML gerada por IA sobre a arquitetura do produto.",
  "type": "presentation",
  "status": "draft",
  "createdBy": "user_id",
  "createdAt": "2026-07-06T00:00:00Z",
  "updatedAt": "2026-07-06T00:00:00Z",
  "approvedBy": null,
  "approvedAt": null,
  "version": 1,
  "visibility": "private",
  "roles": ["Admin", "Author", "Approver", "Reader"],
  "blobPath": "html-artifacts/tenant_abc/artifact_123/v1/index.html",
  "assetsPath": "html-artifacts/tenant_abc/artifact_123/v1/assets/"
}
```

---

## 8. Segurança recomendada

HTML gerado por IA deve ser tratado como conteúdo potencialmente perigoso, especialmente se puder conter JavaScript.

### 8.1 Renderização em iframe sandbox

O viewer deve usar `iframe sandbox`.

Exemplo inicial:

```html
<iframe
  src="/api/artifacts/html/artifact_123/render"
  sandbox="allow-scripts allow-popups allow-downloads"
></iframe>
```

Recomendação importante:

- começar sem `allow-same-origin`;
- evitar acesso do HTML gerado a cookies/localStorage do app pai;
- usar CSP restritivo;
- bloquear chamadas externas por padrão;
- permitir assets apenas do próprio blob/proxy controlado.

---

### 8.2 Sanitização e validação

Antes de persistir/publicar:

- validar estrutura HTML;
- bloquear scripts externos não aprovados;
- bloquear iframes aninhados, salvo exceções;
- bloquear forms não aprovados;
- bloquear chamadas para endpoints internos;
- remover tracking externo;
- aplicar Content Security Policy;
- salvar hash do conteúdo;
- manter versão imutável após aprovação.

---

### 8.3 Separação de conteúdo e aplicação

O HTML gerado deve ser exibido de forma isolada. Ele não deve rodar com o mesmo contexto de segurança do app principal.

Boa prática:

```text
App principal:
  https://ca-web-xxx.azurecontainerapps.io

Render/proxy de artefatos:
  https://ca-web-xxx.azurecontainerapps.io/artifacts/[id]/preview

Conteúdo real:
  Blob privado + acesso mediado pelo backend
```

Em uma fase mais madura, pode-se considerar domínio/subdomínio separado para renderização:

```text
https://artifacts.foundry-assured.example.com
```

---

## 9. Versionamento e aprovação

O modelo ideal é tratar HTML como artefato versionado.

### Estados sugeridos

```text
draft
pending_approval
approved
published
archived
rejected
```

### Fluxo sugerido

```text
Author gera HTML
        ↓
Salva como draft
        ↓
Solicita aprovação
        ↓
Approver revisa no viewer sandbox
        ↓
Aprova ou rejeita
        ↓
Se aprovado, gera versão imutável
        ↓
Publica link interno
```

---

## 10. Uso dos roles existentes

Aproveitar os roles já previstos no projeto:

| Role | Uso na feature HTML |
| --- | --- |
| Admin | governa todos os artefatos, permissões e políticas |
| Author | cria e edita artefatos HTML |
| Approver | aprova publicação e alterações sensíveis |
| Reader | visualiza artefatos publicados/autorizados |

---

## 11. Organização no Blob Storage

Estrutura sugerida:

```text
html-artifacts/
  {tenantId}/
    {artifactId}/
      manifest.json
      v1/
        index.html
        assets/
          chart-data.json
          image-001.png
      v2/
        index.html
        assets/
```

Benefícios:

- separação por tenant;
- versões imutáveis;
- fácil rollback;
- controle de metadados;
- suporte a assets;
- compatível com publicação futura em Static Web Apps ou Storage Static Website.

---

## 12. Roadmap recomendado

### Fase 1 — MVP interno

- Criar domínio `artifacts` no frontend.
- Criar endpoint para gerar HTML.
- Salvar HTML em Blob Storage privado.
- Exibir em `/artifacts/[id]/preview` com iframe sandbox.
- Usar roles existentes para autorização básica.

### Fase 2 — Governança

- Adicionar status draft/pending/approved/published.
- Criar fluxo de aprovação HITL.
- Adicionar versionamento.
- Adicionar histórico e diff textual/visual.
- Criar políticas de sanitização.

### Fase 3 — Publicação

- Links compartilháveis internos.
- Expiração de links.
- Publicação por tenant/domínio.
- Templates de apresentação/relatório.
- Biblioteca de artefatos.

### Fase 4 — Export e distribuição

- Exportar para PDF.
- Exportar pacote `.zip` com HTML/assets.
- Publicar opcionalmente em Azure Static Web Apps para microsites independentes.
- Integrar com Teams/SharePoint para descoberta.

---

## 13. Decisão final resumida

| Necessidade | Melhor opção |
| --- | --- |
| Exibir HTML dentro do produto `foundry-assured` | Next.js atual + FastAPI + Blob Storage + iframe sandbox |
| HTML público barato | Azure Blob Static Website |
| Microsites independentes versionados | Azure Static Web Apps |
| Distribuição corporativa/intranet | SharePoint como catálogo/link hub |
| Portal low-code com Dataverse | Power Pages |

---

## 14. Conclusão

Para o `foundry-assured`, a melhor decisão arquitetural é **não criar uma segunda plataforma de frontend agora**.

O repositório já possui praticamente tudo que uma feature de HTML artifacts precisa:

- frontend Next.js;
- backend FastAPI;
- agentes via Foundry/AG-UI;
- Entra;
- app roles;
- Storage;
- Container Apps;
- Bicep;
- `azd`;
- deploy automatizado;
- modelo de domínios configuráveis.

Portanto, a estratégia recomendada é:

> Transformar HTML gerado por IA em um novo tipo de artefato dentro do próprio `foundry-assured`, armazenado em Blob Storage, governado pelo backend, exibido pelo frontend atual e renderizado em iframe sandbox com RBAC, versionamento e aprovação.

Essa abordagem preserva o produto como uma experiência única, reduz complexidade operacional e abre caminho para evoluir depois para publicação externa via Azure Static Web Apps quando fizer sentido.
