---
title: 'Design: o workspace do usuário final — wizard, campos assistidos e catálogo vivo'
description: Como estruturar agentes, skills, bases, MCPs e project numa interface que um usuário sem RBAC no Azure consegue operar. O backend continua sendo o Foundry; o que se constrói é a camada de acesso. Inspirado nos padrões do aap-kb (AIFieldBlock, wizard com estado compartilhado, crachá), adaptados para recursos do Foundry em vez de um backend próprio.
type: design
audience: contributor
status: draft
research: vínculo agente↔toolbox resolvido em 2026-08-17 — o toolbox é um servidor MCP
updated: 2026-08-17
---

# O workspace do usuário final

## O problema, dito com precisão

O backend está pronto: **21 rotas** cobrindo agentes, bases, skills e toolboxes, com escrita
atrás de Admin e 60 asserções offline. A interface, não. Hoje ela é o que o feedback apontou:

> "na tela só tem 2 campos… não vi no agent como adicionar skills… agora na tela de agent tá tudo
> campo texto aberto"

E está certo. O que existe é um formulário que pede JSON cru — quem sabe escrever aquele JSON não
precisa deste produto, e quem precisa deste produto não sabe escrevê-lo. **A tela reproduz a
barreira que o produto existe para remover.**

## O princípio que não muda

Nada de backend novo. O Foundry continua sendo o dono dos recursos — a MÁXIMA MAIOR vale integral.
O que se constrói é a **camada de acesso**: a diferença entre expor uma capacidade a quem não a
alcança (produto) e reimplementá-la (proibido).

O `aap-kb` é referência de **padrões de interface**, não de arquitetura: ele tem backend próprio,
nós não teremos. O que se importa de lá são quatro padrões, todos de interface.

## Os quatro padrões que valem importar

### 1. AIFieldBlock — o campo pede ajuda ao agente, não à API

No `aap-kb`, um campo de formulário não chama IA. Ao passar o mouse, ele oferece *gerar* /
*revisar* / *instrução própria*, e o clique **envia um prompt contextual ao chat**. Quem escreve
o valor é sempre o agente, pelo caminho normal — com o histórico visível e a aprovação de sempre.

É elegante por um motivo que não é estético: **não cria um segundo caminho de escrita**. Um botão
"gerar com IA" que preenche o campo direto seria uma via paralela, sem rastro no chat e sem HITL.

### 2. O estado do wizard É o estado do agente

`const { agent } = useAgent({ agentId: 'operador' })` — a tela lê `agent.state` e escreve com
`agent.setState`. Humano e agente compartilham o mesmo canvas: o que um muda, o outro vê.

Isto é o que o feedback chamou de *"CopilotKit controlando a tela"*, e já temos a infraestrutura
(`useCoAgentStateRender` está em uso no console).

### 3. Crachá em vez de linha de tabela

`cracha-agente.tsx`: o agente aparece como um cartão com identidade, competências e histórico —
não como uma linha com colunas técnicas. Para um catálogo que o usuário final navega, o cartão é
a forma certa; a tabela serve para auditoria.

### 4. Wizard com etapas nomeadas

`agente-stepper.tsx` + `bloco-step.tsx`: em vez de um formulário com todos os campos, etapas com
nome e propósito. O campo-texto-aberto de hoje vira uma sequência que ensina enquanto preenche.

### 5. O wizard de skill do `aap-kb`, que resolve o bundle

`nova-skill-wizard.tsx` (562 linhas) é o molde direto do que falta aqui — quatro passos:

| Passo | O que faz | Detalhe que importa |
|---|---|---|
| 1 | nome + descrição | valida **kebab-case** e checa duplicidade antes de seguir |
| 2 | instruções | o texto da skill |
| 3 | **arquivos** | agrupados por função: `scripts` e `references` |
| 4 | revisão | mostra o que vai ser enviado |

Duas coisas do passo 3 valem copiar. A primeira é o **agrupamento**: os arquivos não são uma pilha
plana, são `scripts` (o que a skill executa) e `references` (o que ela consulta). A segunda é
`validarNomeArquivo` — recusa `/`, `..` e `.`, a mesma proteção de travessia que o nosso
`_safe_blob_name` já faz no backend. As duas pontas conferindo é o certo: o backend porque é a
fronteira real, a tela porque erro de digitação merece resposta imediata.

Há também `importar-skill-modal.tsx`, para trazer skill pronta — que no nosso caso mapeia direto
para `POST /skills/{name}/files` com um zip.

## A estrutura proposta

### Navegação: quatro recursos sob um contexto

```
Projeto  <nome>                     ← contexto, no topo do shell (não é item de menu)
  Agentes       catálogo (crachás) · wizard de criação · detalhe com versões e sessões
  Conhecimento  catálogo · criação (arquivos | GitHub) · status de sincronização
  Skills        catálogo · criação (inline | BUNDLE de arquivos) · versões
  Ferramentas   MCPs e toolboxes — o que os agentes podem alcançar
```

**Project é contexto, não item.** Todos os recursos vivem dentro de um `FOUNDRY_PROJECT_ENDPOINT`
(`.../api/projects/<projeto>`). Ele aparece no cabeçalho do shell, como o seletor de tenant
aparece num SaaS — sempre visível, nunca uma tela.

**Correção de uma afirmação anterior desta spec.** Eu havia escrito que "não há operação de criar
project no SDK". Isso estava errado: eu confundi **data plane** (`AIProjectClient`, que de fato não
cria) com **management plane**. Project é recurso ARM e se cria por ARM —
`PUT .../Microsoft.CognitiveServices/accounts/{conta}/projects/{nome}?api-version=2026-05-01`,
`azure-mgmt-cognitiveservices` (`client.projects.begin_create`),
`az cognitiveservices account project create`, ou Bicep.

**A decisão continua a mesma, por razões melhores:**

1. **Permissão é o gargalo, não a API.** Criar project exige `Foundry Account Owner`, `Foundry
   Owner`, `Contributor` ou `Owner`. O público-alvo — quem "não tem e não vai ter" RBAC — não pode
   disparar essa chamada com a própria identidade. Fazê-lo com a identidade do produto significaria
   gravar recurso ARM em nome do cliente: fronteira de confiança nova, e gatilho de threat model.
2. **O primeiro project é assimétrico.** Só ele é `isDefault`, e só ele suporta OpenAI Batch,
   fine-tuning e stored completions. "Um project por cliente" produziria clientes de primeira e de
   segunda classe — o oposto do isolamento simétrico que um SaaS precisa.
3. **Project é recurso ARM.** Entra em Azure Policy, cota, convenção de nome, tag de custo, e a
   deleção é irreversível. Transferir isso a quem não tem contexto de infra transfere risco, não
   autonomia.

Se surgir demanda de "um project por cliente", ela pertence ao modo **`dedicated`** (stamp
Managed Application), onde o provisionamento já é ARM e feito por identidade com RBAC.

**O que serve para agrupar dentro de um project**, e vale um spike:
`Microsoft.CognitiveServices/accounts/projects/applications` — agrupa um conjunto de agentes sob
`baseUrl` próprio, `authorizationPolicy` e identidades Entra próprias. É sub-agrupamento com
fronteira de autorização real, sem multiplicar recursos ARM. Há também RBAC no escopo de um agente
individual (`.../projects/{p}/agents/{nome}`), avaliado só para acesso ao endpoint do agente.

### O wizard de agente, em quatro etapas

| Etapa | O que pergunta | Como ajuda |
|---|---|---|
| **1 · Identidade** | nome, para que serve | verifica se o nome JÁ EXISTE (o backend lista); sugere um livre |
| **2 · Comportamento** | instruções, modelo | AIFieldBlock: "gerar" e "revisar" mandam prompt ao chat |
| **3 · Capacidades** | base de conhecimento, MCPs, skills | **seleção a partir do catálogo real**, não texto livre |
| **4 · Revisão** | o JSON resultante | mostra o que vai ser enviado, e publica a primeira versão |

A etapa 3 é a que responde *"não vi no agent como adicionar skills"*, e é onde mora a decisão
técnica mais importante — a próxima seção.

### Capacidades: o que cada uma exige, medido no SDK

| Capacidade | Como chega ao agente | Estado |
|---|---|---|
| Base de conhecimento | `AzureAISearchTool` direto em `tools` | ✅ implementado (atalho `knowledge_base`) |
| MCP | `MCPTool` direto em `tools` (`server_url` **ou** `connector_id`) | ✅ backend aceita; falta seleção na tela |
| Code interpreter, web search, file search… | tools de primeira parte em `tools` | ✅ passa cru; falta oferecer na tela |
| **Skill** | via toolbox, que é um **servidor MCP** — `mcp` tool com a URL do toolbox | ✅ **desbloqueado**, ver abaixo |

**RESOLVIDO — e as três hipóteses estavam erradas.** A pesquisa na documentação oficial respondeu:

> **O toolbox É um servidor MCP.** O agente aponta para ele pelo `mcp` tool comum, com
> `server_url` — não há campo dedicado, e não falta nada no SDK Python. **O vínculo é a URL.**

```
{project_endpoint}/toolboxes/{nome}/mcp?api-version=v1              ← consumer: serve a default_version
{project_endpoint}/toolboxes/{nome}/versions/{v}/mcp?api-version=v1  ← developer: testar antes de promover
```

A cadeia completa fica:

**Skill → `ToolboxSkillReference` → versão do toolbox → URL `/mcp` → `mcp` tool em
`PromptAgentDefinition.tools` → agente.**

O endpoint *consumer* serve sempre a `default_version`, então **promover uma skill é rollout sem
tocar em código de agente nem em toolbox** — é o que dá sentido ao `default` vs `latest` que a
tela já mostra.

**Skills chegam como MCP Resources**, não como tools: `skill://{nome}`, descobertas por
`resources/list` e lidas por `resources/read` (SEP-2640). Qualquer cliente MCP consome — inclusive
sem SDK do Foundry. A API de skills exige o header `Foundry-Features: Skills=V1Preview`.

**TESTADO — e o que falta é autenticação, não o mecanismo.** Criei skill → toolbox → agente e
perguntei ao agente. Ele tentou conectar ao toolbox (a URL está certa) e recebeu **401
PermissionDenied**. O `mcp` tool sozinho não autentica no endpoint: falta uma **project
connection** referenciada por `project_connection_id`, criada com
`azd ai connection create <nome> --kind remote-tool --target <url> --auth-type user-entra-token
--audience https://ai.azure.com`.

**Consequência para o produto:** oferecer o toolbox como capacidade sem essa connection produz um
agente que falha na primeira chamada. A fase 7 fica com o caminho mapeado ponta a ponta e um passo
de infraestrutura a resolver — ou automatizando a criação da connection (o repositório já gerencia
connections, sub-projeto B), ou documentando-a como pré-requisito do operador.

Dois achados menores do mesmo teste: `description` é **obrigatório** ao criar skill, embora o SDK
o declare opcional (sem ele: `invalid_payload: The request field is required`, sem nomear o
campo); e ao invocar um agente pelo `responses.create`, o `model` precisa ser o modelo do agente,
não o nome dele.

### O caminho alternativo que casa com a ADR-013

**Direct injection**, documentado: `GET {endpoint}/skills/{nome}/content` devolve um ZIP; o runtime
extrai, lê os `SKILL.md` no startup e injeta o conteúdo como instruções extras da sessão.
**Funciona sem toolbox.**

Isto é exatamente o modelo que este repositório já usa para prompts (ADR-013/014): documento
montado na composição, publicável sem rebuild. Para os agentes que rodam no NOSSO backend, é o
caminho mais curto e o mais alinhado ao que já existe.

### O meta-agente "arquiteto"

Um quinto domínio no registry, `grounded`/`tool`, com um papel só: **conhecer o Foundry deste
projeto e ajudar a preencher o wizard**. Ele:

- lê o catálogo real pelas rotas que já existem (agentes, bases, skills, modelos disponíveis);
- responde "esse nome já existe, que tal `suporte-rh-2`?";
- redige instruções quando o AIFieldBlock pede;
- explica o que cada capacidade faz, na hora de escolher.

Ele **não** cria recursos sozinho: propõe, e a criação passa pelo botão do wizard com a
autorização de sempre. O padrão de aprovação já existe no `TicketApproval`/`GraphApproval`.

### Skills: o que falta na tela

O backend já aceita **bundle** (`POST /skills/{name}/files` — zip ou vários arquivos), e a tela
não oferece. A tela de skill passa a ter:

- **catálogo** em cartões, com `default` e `latest` lado a lado (a divergência é o que explica
  "publiquei e nada mudou");
- **criação em dois caminhos**: inline (formulário com instruções) ou **bundle** (arrastar zip
  ou pasta);
- **detalhe** com versões e o conteúdo declarado.

## Fases

Cada fase entrega valor sozinha e não depende da seguinte.

| # | Entrega | Depende de |
|---|---|---|
| **1** | Wizard de skill em 4 passos (nome · instruções · **bundle agrupado** · revisão) + catálogo em cartões | nada — backend pronto |
| **2** | Project no cabeçalho do shell | nada |
| **3** | Wizard de agente (4 etapas), com verificação de nome existente | nada |
| **4** | Etapa 3 do wizard: base + MCP + tools, por seleção do catálogo | nada |
| **5** | AIFieldBlock nas etapas 2 e 3 | fase 3 |
| **6** | Meta-agente arquiteto | fase 5 |
| **7** | Skills no agente: montar a URL `/mcp` do toolbox e oferecê-la como capacidade | testar se o agente server-side lê MCP Resources |

## Uma descoberta de SEGURANÇA, fora do escopo desta spec

A documentação diz, sobre o endpoint MCP do toolbox:

> "The toolbox MCP endpoint doesn't block `tools/call` […] Your agent runtime must enforce the
> setting."

Ou seja: **`require_approval: "always"` no `mcp` tool NÃO é enforçado pelo endpoint.** É uma
declaração que o runtime do agente precisa honrar — um aviso, não um gate.

Isto importa além desta spec: se a governança de escrita do sub-projeto C (RBAC por tool, tools de
WRITE atrás da aprovação) estiver contando com esse campo como trava, ela está contando com um
aviso. **Vale uma verificação separada de onde a aprovação é realmente aplicada hoje** — no nosso
runtime (que seria correto) ou na expectativa de que o serviço bloqueie (que não bloqueia).

## O que NÃO vamos fazer

- backend próprio para qualquer um desses recursos — o Foundry é o dono
- editor visual de JSON: o wizard produz o documento, e a etapa 4 o mostra
- copiar o `aap-kb` estruturalmente — ele tem backend próprio e um domínio diferente; o que se
  importa são padrões de interface
- prometer o vínculo skill↔agente antes de saber como ele funciona

## Referências

- `aap-kb`: `apps/web/src/components/ai-field-block.tsx`, `components/skills-selector.tsx`,
  `components/cracha-agente.tsx`, `features/admin-agente-wizard/`
- SDK instalado: `PromptAgentDefinition` (10 campos), `ToolboxVersionObject`,
  `ToolboxSkillReference`, `MCPTool`, `AzureAISearchTool`
- Superfície atual: 21 rotas em `app/modules/foundry/api.py`
- MÁXIMA MAIOR em `CLAUDE.md`
