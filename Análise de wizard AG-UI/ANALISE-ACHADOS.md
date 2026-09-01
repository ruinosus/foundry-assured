# Análise do diretório "Análise de wizard AG-UI" — achados

> Gerado a partir da leitura dos 21 arquivos `.dc.html` (canvases interativos) do diretório e do
> cruzamento com o código atual em `apps/backend/app/modules/`. Não é um plano de execução — é um
> retrato do que os documentos propõem e de onde o produto já está hoje.

## 1. O que é este diretório

Não é documentação de uso — é um **conjunto de protótipos de design navegáveis** ("canvas", tag
`x-dc` com componentes reativos declarados em JS inline). Cada `.dc.html` é uma tela ou família de
telas clicável, com dados mockados no próprio arquivo. É material de **visão de produto**, não
spec de engenharia — mas com detalhe suficiente (manifestos YAML de exemplo, contratos de campo,
regras de validação) para funcionar como proto-especificação.

17 telas distintas (alguns arquivos têm mais de uma aba), organizadas pelo próprio "Visão
geral.dc.html" em cinco grupos: **Entender, Criar, Registrar, Operar, Provar**.

## 2. A virada de visão: de "wizard de agente" para "plataforma de copilotos declarados"

O produto hoje (ver `foundry-helpdesk-spec.md`, `CLAUDE.md`) é um **showcase de 4 domínios** fixos
(helpdesk, techdocs, selfwiki, platform) com wizards de criação de agente/skill/base escritos à
mão em React (AgentWizard.tsx e afins). Os documentos analisados propõem generalizar isso para uma
**plataforma multi-tenant onde "copiloto" é um tipo de documento**, não uma tela codada — na linha
das duas máximas já registradas no `CLAUDE.md` (Microsoft resolve a capacidade; nós ligamos /
declaramos).

### 2.1 O modelo central: bundle OKF

- Formato: diretório de markdown + frontmatter YAML (padrão citado como "de mercado", inspirado no
  Agent Bundle da Google/Vertex — mesmo espírito do `docbundle.schema.json` que o projeto já usa
  para `techdocs`/`selfwiki`).
- **Nove `type:`** de documento convivendo no mesmo formato: `copilot`, `usecase`, `formflow`,
  `policy`, `agent`, `middleware`, `adapter`, `mcp`, `bundle`/`log`.
- Regra central, repetida em quase todo arquivo: **"o produto guarda referência + contrato, nunca
  o código da peça"**. Trocar a implementação de um middleware não é editar o copiloto — é trocar
  o que o nome resolve no registry.
- Frase-âncora do conjunto: *"copiloto novo é documento novo — não componente novo"*.

### 2.2 Quatro planos que não se misturam

| Plano | Conteúdo | Regra |
|---|---|---|
| **Controle** | registries de agente/middleware/adapter/mcp (referência, nunca código) | nada entra em produção direto — primeira instalação é sempre **sombra** |
| **Dado** | bundles: manifestos, formflow, policy, doc, log | tudo é bundle ⇒ tudo é base de conhecimento, indexado, ACL por documento |
| **Execução** | copiloto propõe, tools alcançam o mundo | nada é escrito sem gesto humano; o payload exibido é o que será executado |
| **Evidência** | trilha, âncora do dia, carimbo externo, dossiê | publicado não se edita — revisão cria versão, a anterior é depreciada |

### 2.3 Seis invariantes (o "não negocia")

1. Nada escrito sem gesto humano — escrita externa passa por gate com papel.
2. Citação que resolve — fonte com SHA+range, dispositivo de norma, ou trecho de áudio com
   instante; abaixo do piso (80%) o bundle não é servido.
3. Teto de custo aplicado **antes** da chamada, por área — não no relatório do mês seguinte.
4. Sombra primeiro — peça que executa entra rodando e registrando o que faria, sem escrever.
5. Publicado não se edita — revisão gera versão nova, a anterior é depreciada (não apagada).
6. Lacuna declarada, nunca palpite — campo sem dado vira pendência com motivo e dispositivo, e
   entra na evidência.

Isso é consistente com regras já inegociáveis do projeto hoje (HITL com papel Approver, citação
obrigatória no resolver, controle de acesso como dado — ver `CLAUDE.md` regras 4-6) — os
documentos generalizam essas regras que hoje só existem no domínio helpdesk para **qualquer
copiloto que alguém venha a criar**.

### 2.4 Peças novas mais relevantes

- **`type: formflow`**: um renderizador único, três manifestos diferentes (agente, skill, base) —
  substitui os wizards escritos à mão por formulário declarado. Cada campo carrega `ai` (o
  copiloto escreve?), `allowDeclaredGap` (aceita lacuna declarada?), `rules` e `citationKind`.
- **`type: policy`**: os quatro gates de HITL (proposta, publicação, tool de escrita, escalação)
  num bloco herdado por todos os copilotos, em vez de espalhados.
- **`type: copilot` + Builder v2**: a superfície declarada — onde monta (dock/console/campo/página
  própria), sobre qual agente roda, quais campos alvo, que middlewares/MCP/adapters exige, papéis
  e tetos por área. O protótipo do Builder v2 edita **quatro copilotos muito diferentes** com o
  mesmo formulário (conformidade CFM, requisição de compras via MCP, RH, plantão por voz) — teste
  de que o "motor" cobre casos heterogêneos sem campo fora do manifesto.
- **Registries de middleware/adapter/mcp**: contrato declarado (`accepts`/`emits`/`stage`/`role`
  para middleware; identidade/região/cobrança para adapter; URL + descoberta RFC 9728 + gate de
  escrita para MCP), sempre entrando em modo sombra.
- **Camada de conformidade regulatória** (`Conformidade.dc.html`, cenário CFM): lacuna declarada
  com dispositivo de norma, citação por artigo/inciso, trilha encadeada por hash, âncora
  write-once diária, carimbo RFC 3161, assinatura com segundo fator (TOTP) e dossiê exportável.
  Introduz também **tenancy hierárquica** (rede → unidade), onde a unidade sempre assina (nunca a
  rede) e o rollup é "pior elo", nunca média.

## 3. Cruzamento com o código atual

O que os documentos descrevem como "proposta" (100% greenfield) está, na prática, **parcialmente
adiantado** no backend atual — achado que não está nos próprios canvases (eles dizem "lido do
código", mas parecem descrever um snapshot anterior):

| Módulo em `apps/backend/app/modules/` | Relação com a proposta |
|---|---|
| `formflow/` (`copilots_dir`, `flows_dir`, `load_copilot`, `load_flow`, `alvos_de`, `campos_propostaveis`, `verificar_alvos`) | Já existe um loader de "copilots" e "flows" com o conceito de **alvos** (campos que o copiloto escreve) e **campos propostáveis** — o núcleo do que os docs chamam de `type: formflow`/`type: copilot` já tem código, não é só ideia. |
| `builder/` (`build_builder_agent`, `builder_agent_proxy`, `assist_log.record_proposal/stats`) | É o assistente de preenchimento do wizard (dock lateral com `propose_field`), com **medição própria de desfecho** (aceita/editada/descartada) — exatamente o "HAVE: propose_field" do canvas "Visão geral". |
| `proposer/` (`propose_agent`, `parse_draft`, `build_prompt`, `get_optimization`/`start_optimization`) | Rascunha definição de agente a partir de descrição em linguagem natural e expõe otimização do Foundry — é o "Como este copiloto nasce? → descrever a necessidade" do "Ponta a Ponta.dc.html", já implementado como módulo com fronteira própria (ADR-017), não como mock. |
| `domains/internal/catalog.py` (`DOMAIN_KINDS`) | O domínio `builder` já existe como `kind: tool`, mesma mecânica de dispatch por `kind` que os docs descrevem para copilotos (`workflow`/`grounded`/`tool`). |
| `knowledge/internal/adapt_openwiki.py`, `wiki_builder.py`, `ingest_docbundles.py` | O conceito de **bundle de markdown + frontmatter versionado (OKF)** já é como o projeto trata `techdocs`/`selfwiki` hoje — os docs propõem estender esse MESMO formato para `copilot`/`formflow`/`policy`, não inventar um novo. |
| `foundry/internal/flow_store.py`, `foundry/internal/audited.py` (comentário `"okf_version": "0.2"`) | O `flow_store` (YAML versionado como Dataset do Foundry) já é citado no canvas como "existe hoje" — confirmado: é código real, com precedência sobre o repo. |
| `agentdefs/` (AgentSchema declarativo, ver `CLAUDE.md` seção "Prompts declarativos") | Já é a prova de que "prompt vira documento publicável" funciona em produção — os docs propõem o mesmo tratamento para copiloto inteiro, não só prompt. |

**Não encontrado no código** (genuinamente greenfield, bate com a lista `TODO` do próprio canvas
"Visão geral"):

- `type: bundle` + `okf-validate` como conceito genérico de validação/quarentena (hoje a validação
  de bundle é específica de `docbundle.schema.json` para techdocs/selfwiki).
- `type: policy` como bloco único herdado de HITL (hoje HITL é código espalhado por domínio —
  `app/modules/hitl/`).
- Registries de `middleware`/`adapter` com sombra obrigatória e teto por área.
- `workflow no harness` declarado como dado (hoje workflow é código Python em cada domínio).
- Trilha encadeada por hash + âncora write-once + RFC 3161 + dossiê (hoje só existe o "fecho diário
  da trilha" — `cli.close_audit_day`, sem hash encadeado nem carimbo externo).
- Tenancy hierárquica multi-camada (rede → unidade) com assinatura e rollup — o sub-projeto A/B/C/D
  já shipado trata tenancy por `tenant_id` único, não por hierarquia de camadas.

## 4. Tensões e perguntas que os documentos não resolvem sozinhos

1. **Duplicação de "copilot"/"agent"**: o código já tem `formflow.load_copilot` e o módulo
   `agentdefs` para agentes declarativos (`PromptAgent`). Os docs propõem outro `type: agent` no
   bundle OKF. Antes de construir os registries, vale decidir se `type: agent` do bundle é o MESMO
   documento que hoje vive em `agents/assured/*.yaml`, ou se são dois catálogos que vão divergir —
   é exatamente o risco que a "SEGUNDA MÁXIMA" do `CLAUDE.md` já nomeou ("duas listas divergem no
   primeiro item novo").
2. **`okf-validate` genérico vs `docbundle.schema.json` específico**: os dois têm o mesmo espírito
   (schema + piso de citação + quarentena), mas hoje só existe para o corpus de techdocs/selfwiki.
   Generalizar para `copilot`/`formflow`/`policy` é trabalho real de schema design, não só UI.
3. **Middleware com `stage: pre-persist` e `emits: block`** presume um pipeline de gravação com
   hooks — não há hoje um pipeline unificado de persistência entre domínios (`helpdesk`,
   `grounded`, `platform_ops` gravam de formas diferentes). Isso é a peça de maior risco de
   engenharia da proposta, e os canvases não descem a esse nível.
4. **Tenancy hierárquica (rede → unidade) do cenário de conformidade** não bate com o modelo atual
   de tenancy do sub-projeto A/B (`TenantConfigProvider`, `tid` do Entra, uma camada). Se o cenário
   CFM for perseguido, é uma extensão de arquitetura, não um campo a mais no formulário.
5. **MCP de terceiro com gate de escrita aplicado pelo "nosso runtime"**: o app `apps/mcp` hoje é
   servidor (expõe tools nossas), não cliente de MCP de terceiro. Consumir ferramentas de servidor
   MCP externo dentro de um copiloto é capacidade nova de runtime, não só registro.

## 5. Síntese

Os documentos descrevem uma evolução coerente e bem amarrada às regras que o projeto já segue
(HITL com papel, citação obrigatória, controle de acesso como dado, teto de custo por área,
"publicado não se edita") — a generalização real é: **transformar "copiloto" de conceito
implícito em código (um domínio a mais no catálogo) em um tipo de documento OKF que qualquer
pessoa da área declara**, com registries de middleware/adapter/mcp como as peças de extensão.

O achado mais importante para quem for planejar a execução é que **isso não começa do zero**: o
núcleo (`formflow`, `builder`, `proposer`, o próprio bundle OKF do knowledge) já existe e já seria
o alicerce — o trabalho real e ainda não iniciado está concentrado em: `okf-validate` genérico,
`type: policy` como bloco herdado, os registries de middleware/adapter com sombra, e a camada de
evidência (trilha encadeada, âncora, dossiê). O cenário de conformidade regulatória com tenancy
hierárquica é o pedaço que mais diverge da arquitetura shipada hoje e merece uma decisão explícita
antes de qualquer especificação — não é extensão incremental do que existe.
