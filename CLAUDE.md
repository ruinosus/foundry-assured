# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Estado atual

Repositório **shipped** (v0.6.0): todas as 6 fases do showcase estão verdes (KB, workflow streaming, memória + OBO, HITL, eval, hosted-agent), e por cima delas o **mecanismo de assurance** (build-fidelity → recall → completeness → controle de acesso por documento → red-team).

**Por cima disso, shipou a evolução para SaaS multi-tenant (A→B→C→D, tudo as-built):** um seam de **deployment mode** com três modos — `self_hosted` (single-tenant de hoje, default byte-idêntico), `dedicated` (stamp Azure **Managed Application** + **Lighthouse** na subscription do cliente) e `shared` (multi-tenant real, tenant resolvido por request do `tid` do Entra). **Sub-projeto A** = fundação multi-tenant (`TenantConfigProvider` Single/Multi, resolução de tenant por request + OBO downstream, memória namespaced por tenant, tenant store swappable Azure Table/in-memory). **Sub-projeto B** = `TenantRecord` + `Connection` que **referenciam** connections do Foundry (nunca guarda segredo), API admin `/tenant` + página de Connections. **Sub-projeto C** = brokering de credenciais Microsoft-nativo (OBO p/ servers de audiência Microsoft; Foundry connections caso contrário) + governança de escrita (RBAC por tool, stricter-of-both; tools de WRITE atrás da tool-approval nativa do framework). **Sub-projeto D-runtime** = domínios montam globalmente e são gated por tenant via **DomainAssignment** (entitlement de licença, `enabled_domains`, ADR-010) + endpoint gêmeo `/platform-hosted`. **Sub-projeto D-packaging** = o **platform hosted agent** deployável (Invocations + Foundry Toolbox + OAuth identity passthrough, ADR-011) e o **dedicated stamp** (`infra/managed-app/` + `infra/lighthouse/`, ADR-002). Há um **4º domínio — `platform`**: concierge de ops **tool-driven** sobre MCP servers first-party da Microsoft (Learn, Azure, Entra, ADO, GitHub) com HITL nas ações de escrita.

**Camada mais recente — prompts declarativos:** os prompts dos agentes saíram do Python e viraram **documentos AgentSchema** em `apps/backend/agents/helpdesk/` (ADR-013), publicáveis sem rebuild via mount do Azure Files (ADR-014), lidos pelo reader oficial da Microsoft `agent-framework-declarative` depois que o DNA SDK foi removido (ADR-015). Ver "Prompts declarativos" abaixo.

A fonte de verdade hoje é o código + o [`README.md`](./README.md) e [`docs/METHOD.md`](./docs/METHOD.md) (modelo as-built); a arquitetura-alvo SaaS está em [`docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md`](./docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md), as decisões nas **ADRs 001–023** ([`docs/adr/README.md`](./docs/adr/README.md)), os designs/planos em `docs/superpowers/specs/` + `docs/superpowers/plans/`, e o runbook de empacotamento em [`docs/D-PACKAGING-RUNBOOK.md`](./docs/D-PACKAGING-RUNBOOK.md). A `foundry-helpdesk-spec.md` e a [`docs/ASSURANCE-MECHANISM-PLAN.md`](./docs/ASSURANCE-MECHANISM-PLAN.md) são plano/histórico (as 6 fases do showcase, com seus critérios verde/vermelho, estão lá) — leia-as como contexto, não como o estado atual.

## O que é

Showcase do **Microsoft Foundry** — um concierge de suporte de engenharia interno. Dev pergunta no chat → sistema **tria** intenção/urgência → **busca** na base de conhecimento → **redige** resposta fundamentada com citações → **decide** se basta responder ou se precisa de ação (abrir ticket/escalar) com **aprovação humana** → **lembra** preferências e resoluções entre sessões. Tudo **avaliado** (groundedness + rubric + policies) e **rastreável** (OpenTelemetry).

O domínio é **swappable**: a arquitetura "pergunte → fundamente → resolva → escale" vale para qualquer assistente do tipo. Trocar o domínio = trocar o corpus de conhecimento e os prompts. Hoje há **quatro domínios**: três grounded/workflow (helpdesk, cockpit, selfwiki) e um **tool-driven** (`platform`) — concierge de ops sobre MCP servers Microsoft com HITL nas escritas. E roda em **três deployment modes** (`self_hosted`/`dedicated`/`shared`) sobre um único codebase (ver "Estado atual").

## Stack

- **Backend** (Python 3.12): `agent-framework` (agentes + `WorkflowBuilder`), `agent-framework-ag-ui` (adapter AG-UI: `AgentFrameworkAgent`, `add_agent_framework_fastapi_endpoint`), `agent-framework-declarative` (reader AgentSchema — **pin exato `==1.0.0rc2`**, ver o comentário no `pyproject.toml` antes de mexer), `azure-ai-projects>=2.2.0` (Foundry client: KB, `.beta.memory_stores`, eval), `azure-identity` (`DefaultAzureCredential`), `fastapi`, `uvicorn`. Deps via **`uv`**.
- **Frontend** (Next.js 16, App Router, React 19): `@copilotkit/react-core`, `@copilotkit/react-ui`, `@copilotkit/runtime`, com `HttpAgent` apontando para o endpoint AG-UI do backend; auth via `@azure/msal-react`.
- **Foundry** (provisionar via `azd` + extensão Foundry): project + model deployment (default seguro: **`gpt-5-mini`**), Foundry IQ knowledge base, memory store, Application Insights (tracing OTEL). Foundry **connections** + **Toolbox** sustentam o brokering de credenciais (sub-projeto C) e o platform hosted agent (sub-projeto D-packaging).
- **SaaS multi-tenant** (sobre o mesmo codebase): seam de `DEPLOYMENT_MODE` com `TenantConfigProvider` (Single/Multi), tenant store swappable (Azure Table / in-memory), e — no modo `dedicated` — Azure **Managed Application** + **Lighthouse** (`infra/managed-app/`, `infra/lighthouse/`). Detalhes em "Estado atual".

## Arquitetura (big picture)

Três camadas. O frontend Next.js conversa com o backend Python via **AG-UI sobre SSE**; o backend roda um **workflow multi-agente** que usa o Foundry na nuvem.

- **Frontend** → o "Assurance Console". A rota genérica `/d/[domain]` (ex.: `/d/helpdesk`, `/d/cockpit`, `/d/selfwiki`, `/d/platform`; as antigas `/chat` e `/cockpit` redirecionam) é dirigida por **um registry**: `apps/frontend/lib/domains.ts` define o agent map (4 domínios; `kind: workflow | grounded | tool`), a nav, a rota genérica e os prompts sugeridos. No modo `shared`, os domínios montam globalmente mas são gated por tenant via **DomainAssignment** (ADR-010). `app/api/copilotkit/route.ts` registra um `CopilotRuntime` com um `HttpAgent` por domínio. A página usa `useCoAgentStateRender` para mostrar os passos intermediários, `useCopilotAction` (`renderAndWaitForResponse`) para o approval card, e um `EvidencePanel` para as fontes citadas + badges de assurance.
- **Backend** → `apps/backend/app/main.py` é fino: cria o FastAPI (rodado como `app.main:app`), aplica CORS, chama `setup_telemetry()`, `include_routers(app)` e `mount_domains(app)`. O registry do backend é `app/registry.py` — **um `DomainSpec` por domínio e um único loop que despacha por `kind`** (`workflow` → AG-UI do helpdesk; `grounded` → cockpit/selfwiki; `tool` → platform). A organização é um **monolito modular por domínio** (ADR-017): `app/modules/<domínio>/` com `public.py` (única superfície importável) e `internal/` (privado), sobre um shared kernel `app/shared/` (settings, auth, telemetria) que não importa nenhum módulo. As fronteiras são verificadas em CI por `import-linter` (22 contratos). A resolução de tenant (modo `shared`) + brokering de credenciais ficam em `app/modules/tenancy/`.
- **Foundry** → o retriever consulta a **Foundry IQ KB** e trima por entitlement (`app/modules/knowledge/internal/secure_search.py`, `app/modules/knowledge/internal/acl_setup.py`); triage/resolver leem/escrevem **memória**; eval e traces vão para o Foundry Control Plane.

**Adicionar um domínio = 3 coisas:** uma linha no registry do frontend (`apps/frontend/lib/domains.ts`), um `DomainSpec` no registry do backend (`apps/backend/app/registry.py`) e o agente/KB correspondente. Os dois registries são espelhos — `eval/domain_registry_test.py` guarda esse contrato.

### Layout do repositório

Monolito modular por domínio (ADR-017) — a pergunta que organiza não é "que tipo de arquivo
é esse?", é "**de que negócio esse arquivo é?**". `import-linter` mantém a resposta.

```
apps/backend/
  app/main.py            composition root: setup_telemetry → tenancy.install → routers → domínios
  app/registry.py        DomainSpec + mount_domains (despacha por `kind`) + include_routers
  app/api_health.py      transversal
  app/shared/            SHARED KERNEL — settings, auth, telemetry/. NÃO importa módulo algum
  app/modules/<m>/       módulos de negócio: public.py (única superfície) + internal/
                         tenancy · admin · knowledge · helpdesk · grounded · platform_ops
                         tickets · hosted · evaluation · agentdefs · hitl · oncall · deepcall
                         usecases · foundry · conversations · proposer · builder · audit
  agents/helpdesk/       documentos AgentSchema (prompts) — NÃO se move (contrato de deploy)
  eval/                  harness de assurance = PRODUTO (8 gates que os workflows invocam)
  tests/<módulo>/        testes, espelhando os módulos; + smoke/ e architecture/
  importlinter.toml      os 22 contratos de fronteira
  cli/                   provision_*
apps/frontend/           Next.js App Router: app/, components/<área>/, lib/ (registry + auth)
apps/hosted-*/           containers dos hosted agents (helpdesk, techdocs, selfwiki, platform)
knowledge/               CONTEÚDO que vira base de conhecimento (nunca código) — ver README lá
  corpus/                13 runbooks fictícios → KB do helpdesk; congelado (base do eval)
  wiki-bundle/           bundle indexável do selfwiki, derivado de openwiki/ pelo adapt
openwiki/                a wiki gerada deste repo (formato da ferramenta) — fonte do bundle
infra/                   bicep/azd (+ managed-app/ e lighthouse/ para o stamp dedicated)
e2e/                     Playwright contra o app DEPLOYADO (sign-in Entra real)
scripts/                 bootstrap, setup-entra, up-all, dev-shared, demo, push-prompts; spikes/
docs/                    documentação PARA HUMANOS apenas — nada indexável mora aqui
docs/adr/                ADR-001..023 — decisões de arquitetura
```

Regra de conteúdo: **`apps/` é código, `knowledge/` é o que os agentes indexam, `docs/` é para
pessoas.** O corpus vivia dentro do pacote Python e o bundle dentro de `docs/` — por isso
ninguém achava nem um nem outro, e um bundle de modelo aposentado ficou meses sendo servido
como atual.

Regra de dependência, verificada em CI:

```
composition (main.py, registry.py)  →  o public de qualquer módulo
modules/<m>/                        →  app.shared + o public de outro módulo
shared/                             →  nada de dentro do app
```

## Prompts declarativos (AgentSchema)

**Prompt não se edita em Python.** A fonte de cada prompt é um documento **AgentSchema `PromptAgent`** em `apps/backend/agents/helpdesk/` (`triage.yaml`, `retrieve.yaml`, `resolve.yaml`, `concierge-{grounded,ungrounded}.yaml`, `cockpit.yaml`, `selfwiki.yaml`, `platform.yaml`).

- O que o AgentSchema **não** modela mora ao lado, como dado do repositório: catálogo do escopo (`scope.yaml`), persona compartilhada (`personas/*.md`), regras cross-cutting (`guardrails/*.md`). Um agente referencia persona/guardrail **por nome** no `metadata`, sob a chave `x-foundry-assured`.
- `app/modules/agentdefs/internal/definitions.py` carrega e compõe (ordem fixa: persona → instructions → additionalInstructions → guardrails); `app/modules/agentdefs/public.py` é o **único ponto de consumo** e compõe no import. Não altere esses dois para mudar texto de prompt.
- `AGENTS_DIR` seleciona um diretório externo de definições (no ACA, o mount read-only do Azure Files em `/mnt/agents`) — ADR-014: sem a env var usa a cópia baked; com a env var e escopo ausente cai pra baked com log alto; com escopo presente, qualquer falha de load é **loud**. `scripts/push-prompts.sh` publica sem redeploy.
- **PowerFx (`=Env.X`) é recusado no load**, não usado — o reader devolveria a string literal quando o runtime .NET falta. Ver docstring de `definitions.py`.
- Mudou contrato de prompt? Atualize o caso correspondente em `agents/helpdesk/eval-cases/` **no mesmo PR** — `uv run python -m eval.prompt_contract_test` é o guarda de CI.

## MÁXIMA MAIOR — a Microsoft já resolveu; nosso trabalho é ligar

**Esta regra governa todas as outras.** Quando ela e qualquer regra abaixo discordarem, ela vence.

Se existe capacidade equivalente no Azure / Foundry / AI Search / Agent Framework / MCP oficial,
**ela ganha do nosso código por definição** — mesmo que o nosso ficasse mais elegante, mais curto
ou mais adaptado. O teto do que se escreve aqui é a **cola**: endpoints finos que orquestram
serviços e SDKs de primeira parte.

**Ordem de trabalho, invertida em relação ao instinto:**

1. **Pesquisar primeiro** — `learn.microsoft.com`, `Azure-Samples`, `microsoft-foundry`, o
   **código do pacote instalado** (fonte de verdade sobre a versão em uso), release notes.
2. **Mapear o que já existe** — qual API/tipo/serviço cobre cada pedaço do pedido.
3. **Só então** propor a cola mínima, dizendo qual peça oficial cada parte usa.

**O ônus da prova é invertido.** Escrever código nosso exige *demonstrar que se procurou e não
existe* — não basta achar que dá menos trabalho fazer à mão. "Não achei" só vale depois de
procurar nos quatro lugares acima.

**Quando a plataforma cobre parcialmente, diga o tamanho da lacuna** em vez de escrever o resto
em silêncio: *"existe X, cobre 80%, faltam estes 20% e custam N linhas"* é decisão do
desenvolvedor, não do agente.

**O que isto NÃO significa.** A máxima proíbe reimplementar capacidade, não proíbe construir
produto. A frase que define a diferença, do dono do projeto:

> **"Não é recriar nada da Microsoft, é preencher lacunas e trazer outros perfis de usuário para
> consumir recursos Microsoft."**

O portal do Foundry atende quem tem conta e RBAC no Azure. Este produto atende quem **não tem e
não vai ter** — usuário final que precisa criar, usar e manter agentes, bases e skills sem
nunca abrir o portal. Construir essa camada de acesso é preencher lacuna; reescrever o que o
portal faz por baixo dela é violar a máxima.

O teste, quando surgir a dúvida: **estou expondo uma capacidade a um perfil que não a alcança,
ou reimplementando a capacidade?** O primeiro é o produto. O segundo é proibido.

**A única exceção, calibrada explicitamente:** a **camada de assurance é nossa** — os gates
(`eval/`, `tests/architecture/`), a resolubilidade de citações, o contrato de decisão HITL. É o
diferencial do projeto, foi pesquisada (não há equivalente de primeira parte — ver
`docs/superpowers/specs/2026-08-16-citation-resolvability-as-a-product-design.md`) e por isso
sobrevive à máxima. Tudo que for **produto** segue a máxima sem exceção.

## SEGUNDA MÁXIMA — tudo fica no Foundry; muda quem colocou e como

Não existe "agente de código" e "agente do Foundry". Existe **um lugar** — o Foundry — e dois
caminhos até ele:

```
dev      →  documento AgentSchema no repo  →  cli.provision_agents  →  Foundry
usuário  →  wizard na tela                 →  POST /agents/…        →  Foundry
```

Depois de publicado, ninguém precisa saber por qual caminho veio: mesma lista, mesma versão,
mesmo histórico, mesmo portal. O mesmo vale para base de conhecimento, skill e toolbox.

**O que isso proíbe.** Manter no código uma lista de recursos que também existem no serviço. Duas
listas divergem no primeiro item novo — e a divergência não dá erro, só faz a tela mentir. Se
algo precisa ser publicado, o publicador **deriva** da fonte que já existe (os documentos
AgentSchema para prompt; o `registry.py` para runtime), nunca declara uma cópia.

**O que isso NÃO proíbe.** Um recurso publicado cujo comportamento roda aqui. Um workflow de três
passos ou um grafo LangGraph com HITL não cabem num `PromptAgentDefinition` — publicá-los registra
identidade, prompt e versão, e a execução continua no backend. Isso é legítimo **desde que dito**:
`metadata.runtime` carrega `foundry` ou `backend`, e a interface mostra. Um recurso que mente
sobre onde executa é pior que um recurso ausente.

Esta máxima nasceu de um sintoma concreto: a tela "Meus agentes" mostrava zero enquanto o produto
exibia seis assistentes — porque os assistentes viviam só como configuração de código.

## Regras inegociáveis

1. **NÃO invente assinaturas de SDK.** A superfície dos SDKs muda rápido — em especial o namespace `.beta` de `azure-ai-projects`. Antes de fixar qualquer chamada a `azure-ai-projects`, `agent-framework`, `agent-framework-ag-ui` ou `agent-framework-declarative`, verifique contra `learn.microsoft.com/azure/foundry` e o repo `microsoft-foundry/foundry-samples`. Se não conseguir confirmar, deixe um `# TODO: verificar assinatura` explícito em vez de chutar.
2. Auth **sempre** via `DefaultAzureCredential` (ou OBO). Nada de API key hardcoded.
3. **Nenhum gate de CI pode ficar vermelho.** Ver "Gates" abaixo — os testes offline rodam sem credencial Azure justamente para serem exigíveis em todo push.
4. Toda resposta do resolver **DEVE** conter ao menos uma citação de fonte. É policy de eval (ASSERT pega violação).
5. A tool `create_ticket` só pode disparar **após aprovação humana explícita** — e a aprovação HITL exige o papel **Approver** (ou **Admin**). Autorização vem de App Roles do Entra (Admin / Author / Approver / Reader) no claim `roles` do token; gestão de usuários + papéis fica em `/admin/users` (via Microsoft Graph, app-only). Plano: [`docs/RBAC-AND-USER-MANAGEMENT-PLAN.md`](./docs/RBAC-AND-USER-MANAGEMENT-PLAN.md).
6. **Controle de acesso é DADO** (os grupos de leitura de cada fonte), **nunca lógica de classificação no código**. O acesso segue a fonte: grupos vêm do manifesto/`COCKPIT_ACL_CLASSIFICATION`, nomes resolvem para object-IDs via `COCKPIT_ACL_GROUP_MAP`; doc sem acesso declarado → fail-closed. Ver [`docs/METHOD.md`](./docs/METHOD.md).
7. **Prompt muda no documento AgentSchema**, nunca em `app/modules/agentdefs/public.py` (ver seção acima). Depois de mudar, republique com `uv run python -m cli.provision_agents` — o Foundry é onde o agente existe (SEGUNDA MÁXIMA), e um prompt que mudou só aqui deixa o portal mostrando a versão anterior.
8. **Fronteiras de módulo são verificadas por `import-linter`** (ADR-017). Código novo entra DENTRO de um módulo existente ou cria módulo novo com `public.py`/`internal/`; import cross-module só via `public`. O shared kernel (`app/shared/`) não importa nenhum módulo. Rode `uv run lint-imports --config importlinter.toml` antes de commitar.
9. **Nunca calcule caminho contando `parents[N]` a partir do próprio arquivo** — ancore no pacote `app` (`Path(app.__file__).resolve().parent.parent`). Três caminhos quebraram assim durante a ADR-017, dois em silêncio. `tests/architecture/filesystem_anchors_test.py` é o gate.
10. Nunca commitar segredo ou valor de `.env` (`TEST-CREDENTIALS.local.md` é gitignored).

## Comandos

### Desenvolvimento

```bash
# backend (de apps/backend/) — precisa de .env preenchido (cp .env.example .env) + az login
uv sync
uv run uvicorn app.main:app --port 8000 --reload

# frontend (de apps/frontend/)
npm install && npm run dev          # http://localhost:3000
npm run demo                        # modo demo com fixtures gravadas, sem Azure

# backend em modo SHARED (multi-tenant: liga /tenant, Connections, admin) — do repo root
./scripts/dev-shared.sh
```

### Gates (o que o CI exige)

Os testes são **módulos executáveis, não pytest** — cada um tem `main()` e sai com código ≠ 0 ao falhar. Rodar um teste isolado = rodar o módulo. Todos abaixo são **offline e determinísticos** (não precisam de Azure):

```bash
# de apps/backend/
uvx ruff check .                            # lint (advisory no CI)
uv run python -m eval.run_eval --self-test  # policy gate: planta violação e prova que pega
uv run python -m eval.test_attribution      # ACL attribution round-trip (chunk key == blob key)
uv run python -m eval.docbundle_contract_test  # contrato do doc-bundle (produtor ↔ consumidor)
uv run python -m eval.prompt_contract_test  # invariantes dos prompts AgentSchema

# gates de arquitetura (ADR-017)
uv run lint-imports --config importlinter.toml           # 14 contratos de fronteira
uv run python -m tests.smoke.routes_snapshot_test        # superfície HTTP (self_hosted + shared)
uv run python -m tests.architecture.module_graph_test    # nenhuma dependência cross-module nova
uv run python -m tests.architecture.filesystem_anchors_test  # nenhum parents[N] contado do arquivo
uv run python -m tests.shared.telemetry_test             # telemetria off por default; captura opt-in
uv run python -m tests.architecture.proposer_read_only_test  # ADR-022: o propositor nunca publica
uv run python -m tests.audit.trail_test                  # ADR-023: cadeia, redator e fail-closed
uv run python -m tests.tickets.store_path_test           # o chamado cai dentro do volume do bicep
uv run python -m tests.usecases.aah_formula_test         # AAH bate com o exemplo publicado pela Microsoft

# fecho diário da trilha (roda por agenda em .github/workflows/audit-anchor.yml)
uv run python -m cli.close_audit_day                     # ancora o dia; write-once, idempotente
uv run python -m tests.conversations.conversation_store_test # a conversa acumula e isola por pessoa

# de apps/frontend/
npm run typecheck && npm run lint && npm run build

# do repo root
bicep build infra/main.bicep --stdout > /dev/null
```

Gates de segurança (workflow `security-gates.yml`, precisam de identidades de teste + Azure):

```bash
uv run python -m eval.access_control_test   # zero vazamento entre grupos
uv run python -m eval.red_team_test         # ASR ≤ teto de assurance.yaml
```

Os testes por módulo ficam em `tests/<módulo>/` e rodam igual (`uv run python -m tests.<módulo>.<nome>`); `eval/` guarda só o harness de assurance — os 8 módulos que os workflows invocam por path. Os limiares de todos os gates vivem em **`eval/assurance.yaml`** (fonte única).

### Eval com nuvem

```bash
# de apps/backend/ — precisa de credencial Azure + KB no ar
uv run python -m eval.run_eval              # policy gate sobre saídas reais do agente
uv run python -m eval.run_eval --cloud      # + groundedness/relevance/coherence no Foundry (link do portal)
uv run python -m eval.run_eval --safety     # set adversarial (jailbreak/off-policy)
```

### Provisionamento e deploy

```bash
azd auth login && az login
./scripts/up-all.sh [--with-auth]           # orquestra tudo: preflight → azd up → bootstrap
# ou passo a passo:
azd up
./scripts/setup-entra.sh                    # opcional: sign-in Entra + OBO
./scripts/bootstrap.sh                      # preenche .env, ingesta a KB, provisiona memória
# de apps/backend/:
uv run python -m app.modules.knowledge.internal.ingest       # (re)constrói a Foundry IQ KB
uv run python -m cli.provision_memory       # cria o memory store
azd deploy helpdesk-concierge               # hosted agent (idem cockpit-expert/selfwiki-expert/platform-concierge)
```

### E2E (contra o app deployado)

```bash
cd e2e && npm install && npm run install:browser
export E2E_BASE_URL="$(cd ../apps/backend && azd env get-value WEB_URL)"
export E2E_USER=… E2E_PASS=…                # credenciais nunca no repo
npm test && npm run report
```

## Convenções de trabalho

Detalhe completo em [`CONTRIBUTING.md`](./CONTRIBUTING.md). O essencial:

- Trunk-based: branch curta a partir de `main` (`feat/…`, `fix/…`, `chore/…`, `docs/…`, `ci/…`) → PR → **squash-merge**. `main` é protegida; o check obrigatório é **`CI passed`**.
- Commits e títulos de PR em **Conventional Commits** (`feat(eval): …`), escopos `backend`/`frontend`/`hosted-agent`/`infra`/`eval`/`auth`/`deps`.
- Trabalho não-trivial é rastreado no board SDLC em YAML em **`.dna/foundry-dev/`**, via o CLI `dna` (`uv tool install dna-cli`, `DNA_BASE_DIR=$PWD/.dna`). É **ferramenta de dev-time** — nenhum app depende do `dna-sdk` desde a ADR-015.

## Referências

- Foundry samples: `github.com/microsoft-foundry/foundry-samples` (pasta `python/hosted-agents/agent-framework`)
- Build 2026 demos (memory, toolboxes, eval): `github.com/microsoft-foundry/build-2026-demos`
- Agent Framework: `github.com/microsoft/agent-framework`
- AgentSchema: `github.com/microsoft/AgentSchema`
- AG-UI ↔ Agent Framework: `learn.microsoft.com/agent-framework/integrations/ag-ui/`
- CopilotKit + MAF: `docs.copilotkit.ai/ms-agent-dotnet` (vale p/ Python também)
- Foundry IQ cookbook: `microsoft-foundry/forgebook` → notebook "mastering-foundry-iq"
- ASSERT (eval policies): `aka.ms/assert`

<!-- OPENWIKI:START -->

## OpenWiki

See [AGENTS.md](AGENTS.md) for OpenWiki agent instructions.

<!-- OPENWIKI:END -->
