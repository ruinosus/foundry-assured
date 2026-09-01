# ADR-032 — OKF projeta recursos oficiais; bindings ligam; publicação compensa

- **Status:** Proposed
- **Date:** 2026-08-31
- **Context:** [plano da plataforma de autoria OKF](../superpowers/plans/2026-08-31-okf-copilot-authoring-platform.md),
  [análise dos protótipos](../../Análise%20de%20wizard%20AG-UI/ANALISE-ACHADOS.md)
- **Builds on:** [ADR-009](./ADR-009-native-tool-approval-foundry-connection-resolution.md),
  [ADR-011](./ADR-011-hosted-per-tenant-foundry-toolbox-passthrough.md),
  [ADR-015](./ADR-015-agentschema-replaces-the-dna-sdk.md),
  [ADR-020](./ADR-020-canonical-frameworks-modular-organization.md),
  [ADR-022](./ADR-022-proposer-not-publisher.md)

## Context

Os protótipos do Builder descrevem copilotos que propõem documentos OKF para combinar agentes,
knowledge bases, skills, toolboxes, MCP, middleware e políticas. A fronteira é legítima somente se
OKF representar intenção e bindings sem virar uma segunda implementação ou um catálogo paralelo
ao Foundry.

A F00 pesquisou quatro fontes antes de definir o contrato: os pacotes instalados, Microsoft Learn,
os repositórios `microsoft/agent-framework`, `microsoft/AgentSchema` e
`microsoft-foundry/foundry-samples`, e o histórico/release metadata dessas superfícies. As versões
medidas foram:

| Pacote | Versão medida |
|---|---:|
| `azure-ai-projects` | 2.4.0 |
| `agent-framework` | 1.14.0 |
| `agent-framework-ag-ui` | 1.1.0 |
| `agent-framework-declarative` | 1.0.2 |
| `mcp` | 1.28.0 |

O resultado muda o centro do desenho: agentes, skills, toolboxes, connections, knowledge bases,
descoberta MCP e aprovação de tool já têm donos oficiais. A lacuna do produto é autorizar uma
pessoa sem acesso ao portal a propor uma composição coerente, revisá-la como conjunto e publicar
as projeções usando esses donos.

## Matriz de capacidade

| Necessidade | Capacidade oficial | Cola necessária | Evidência verificada |
|---|---|---|---|
| Listar e versionar agentes | `AIProjectClient.agents`: `list`, `get`, `create_version`, `list_versions`, `delete_version` | Projeção tenant-safe e autorização da rota | Fonte instalada de `azure-ai-projects` 2.4.0 e `modules/foundry/internal/agents.py` |
| Definir agente declarativamente | AgentSchema `PromptAgent` + reader `agent-framework-declarative` | `agent-binding` referencia a definição e a versão publicada | AgentSchema oficial e ADR-015 |
| Listar e publicar skills | `AIProjectClient.beta.skills`: `list`, `get`, `create`, `list_versions`, `delete_version` | Projeção e validação do formato agentskills.io | Fonte instalada; `modules/foundry/internal/skills.py`. Superfície **beta** |
| Listar e versionar toolboxes | `AIProjectClient.toolboxes`: `list`, `get`, `create_version`, `list_versions`, `delete_version` | Projetar conteúdo e escolher endpoint default ou versionado | Fonte instalada; `modules/foundry/internal/toolboxes.py`; Learn recomenda Toolbox |
| Listar e resolver connections | `AIProjectClient.connections`: `list`, `get`; connections e OBO guardam/resolvem credenciais | Binding guarda somente o identificador; criação continua admin/out-of-band | Fonte instalada, ADR-008/009 e Learn MCP authentication |
| Listar knowledge bases | `SearchIndexClient.list_knowledge_bases`, `list_knowledge_sources` e operações de status | Projetar bases/fontes sem copiar conteúdo ou ACL | SDK instalado e `modules/foundry/internal/knowledge_catalog.py`. API Search **preview** |
| Conectar e descobrir MCP remoto | `MCPStreamableHTTPTool(load_tools=..., allowed_tools=..., approval_mode=...)`, método `MCPTool.load_tools()` e MCP `tools/list` | Referenciar Toolbox/connection permitidos e capturar observação de descoberta | Assinatura instalada do Agent Framework 1.14.0 e fonte oficial `_mcp.py` |
| Aprovar tools seletivamente | `approval_mode` aceita `always_require`, `never_require` ou `MCPSpecificApproval`; Foundry MCP aceita `require_approval` global ou por nomes | Política escolhe o modo mais restritivo e a UI traduz o evento nativo | Fonte instalada e Learn “Connect agents to MCP server endpoints” |
| Autenticar tools | Foundry Toolbox + project connections + user Entra token/OBO | Selecionar referências já autorizadas; nunca transportar segredo em OKF | Learn e ADR-009/011 |
| Aplicar middleware | Middleware nativo do runtime, dentro do módulo que o executa | `middleware-binding` aponta para implementação concreta compatível | ADR-020; não há middleware universal a materializar |
| Propor vários documentos | Nenhuma primitiva Foundry representa uma mudança OKF multi-documento | `OkfChangeSet`, validação, diff, autorização e procedência | Lacuna de produto confirmada; ADR-022 separa proposta de publicação |
| Publicar atomicamente em vários serviços | Não existe transação distribuída entre Foundry, Search e storage | Pré-validação, journal, idempotência e compensações | Lacuna de produto; recursos oficiais são versionados, mas independentes |

### Limites da verificação

- `skills` e knowledge bases permanecem em superfícies preview/beta. O código deve continuar
  confinado aos módulos donos, sem wrapper que prometa estabilidade.
- O SDK instalado confirma `client.toolboxes.create_version`; documentação mais nova também usa
  esse nome. Não adotar a nomenclatura antiga `create_toolbox`.
- Tool descriptions, annotations, schemas e resultados MCP são entrada não confiável. Eles ajudam
  a classificar, mas não autorizam uma escrita.
- Metadados de Foundry/AgentSchema podem guardar identidade e proveniência da projeção. Eles não
  substituem o journal do ChangeSet nem devem carregar o documento OKF inteiro.

## Decisão

### D01 — AgentSchema é a fonte de verdade de agente

Não haverá `type: agent` OKF concorrente. O documento autorável é `agent-binding`: ele seleciona
uma definição AgentSchema, uma versão publicada e os recursos oficiais ligados a ela. Alterar
instruções altera o AgentSchema e segue seu eval/publicador; alterar a composição altera o binding.

### D02 — Descoberta MCP produz snapshot de evidência, não catálogo autoritativo

O servidor MCP continua sendo a fonte operacional. Cada registro ou refresh captura uma observação
imutável com identidade do servidor/connection, instante, versão de protocolo, nomes, schemas,
annotations e hash canônico. O snapshot sustenta diff, revisão e reprodução da proposta.

Antes de ativar ou invocar uma tool de escrita, o runtime redescobre e compara. Mudança de nome,
schema ou classificação coloca o binding em `quarantined` até nova revisão. Não criaremos assinatura
criptográfica própria: hash e evento entram na evidence layer da ADR-023.

### D03 — Classificação é administrativa e aplica o mais restritivo

Annotations e descrições do servidor são sinais não confiáveis. A classificação efetiva combina:

1. classificação administrativa por `server + tool`;
2. sinal declarado pelo servidor;
3. política organizacional e papel do chamador;
4. `approval_mode`/`require_approval` nativo do runtime.

O resultado mais restritivo vence. Tool desconhecida ou sem classificação confiável é tratada como
escrita de alto risco, não pode entrar numa allowlist de execução automática e exige revisão.

### D04 — Publicação é saga compensável

O ChangeSet é validado por inteiro antes da primeira escrita, mas sua materialização não promete
uma transação que os serviços não oferecem. O publicador mantém journal por operação, chave de
idempotência, estado e compensação. Em falha, remove versões recém-criadas quando a API permitir ou
publica/reaponta a versão anterior; se não puder restaurar automaticamente, termina em
`compensation_required` com evidência e sem declarar sucesso.

### D05 — Revisão por documento; aprovação final do conjunto

Cada documento pode ser aceito, editado ou descartado durante a revisão. Qualquer edição invalida
a aprovação anterior. A publicação exige uma confirmação final do ChangeSet normalizado inteiro,
com operações, impacto, papéis e plano de compensação. Aprovação de uma tool durante execução não
aprova publicação, e aprovação de publicação não pré-aprova tool de escrita.

### D06 — Policy é visão composta, não executável, e somente administrativa

Não haverá um motor universal de policy. `type: policy` é uma visão procedimental não executável
das fontes que já aplicam cada regra: App Roles/Entra, tenant config, ACL da fonte,
Toolbox/connection e approval nativo. O enforcement permanece exclusivamente nessas fontes. A
policy organizacional registra precedência e defaults do produto, mas não copia segredos nem
substitui os enforcements oficiais. Copilotos podem apontar incompatibilidades; não podem criar ou
revisar policy.

### D07 — Middleware é implementação concreta do runtime

`middleware-binding` referencia uma implementação existente, seu runtime, contrato, versão e
configuração permitida. Para o primeiro caso de tickets, a implementação fica no módulo dono e usa
middleware/approval nativo do Agent Framework. Não nasce pacote universal, Azure Function ou
hosted agent só para uniformizar runtimes. Outro runtime ganha binding e implementação próprios,
conforme ADR-020.

### D08 — Tenancy hierárquica fica fora do MVP

O requisito confirmado é isolamento pelo tenant resolvido do request e projeto Foundry do tenant.
Hierarquias regulatórias, delegação entre áreas e herança de policy continuam cenário exploratório
da F12. Elas não entram no envelope F01 nem bloqueiam o caso vertical de tickets.

### D09 — Autoria é extensão namespaced; conformidade OKF continua upstream

O Open Knowledge Format v0.2 não é o schema estrito de publicação do produto. Sua conformidade é
verificada separadamente pelo validador vendorizado e permite chaves adicionais e referências
quebradas conforme a especificação. O contrato autorável opta explicitamente pela extensão
`x-foundry-authoring`, com `profile_version`, identidade tenant-local, revisão imutável, estado de
publicação, referências e `spec` tipado.

Os campos upstream mantêm seu significado: `resource` aponta para o ativo subjacente e não é
identidade; `status` usa `draft|stable|deprecated`; `generated`, `verified` e `sources` carregam
proveniência. `okf_version` pertence ao `index.md` raiz do bundle, não a cada conceito. O perfil
não expõe uma API de parser OKF genérico: suas classes e funções usam o prefixo `Authoring`.

### D10 — Legado coexiste e migração nunca infere autoridade

Os manifestos atuais continuam legíveis pelo loader tolerante de FormFlow e não optam
implicitamente por `x-foundry-authoring`. A migração declara formato de origem, versão de destino,
tenant, área, revisão e autor, e sempre produz `draft` sem alterar o arquivo de origem. O spec de
`formflow` pode ser transportado deterministicamente; `copilot` e `policy` exigem um spec
substituto explícito porque seus significados mudaram. Docbundles permanecem OKF upstream e só
entram no perfil por uma decisão de autoria futura.

### Nomenclatura

Usar `agent-binding`, `mcp-binding`, `middleware-binding` e `adapter-binding`. O sufixo torna claro
que o documento liga intenção a uma capacidade que existe fora dele. Nomes sem `-binding` ficam
reservados para o recurso/implementação oficial ou concreta.

## Consequências

- **+** Catálogos operacionais continuam no Foundry, Search e servidores MCP; OKF não mantém cópia
  concorrente.
- **+** Drift de tool fica visível sem tratar metadata de servidor como autorização.
- **+** A revisão parece atômica para a pessoa, enquanto a execução declara honestamente estados
  parciais e compensações.
- **+** AgentSchema, middleware e HITL continuam reconhecíveis pelas documentações dos runtimes.
- **−** Snapshot, journal, autorização do ChangeSet e diff são código nosso. Essa é a lacuna real,
  não capacidade Microsoft reimplementada.
- **−** Uma saga pode terminar exigindo intervenção. Ocultar esse estado seria mais perigoso que
  aceitar a complexidade operacional.

## Alternativas recusadas

- **Novo `type: agent` completo em OKF:** duas fontes de verdade para o mesmo agente.
- **Registry local como catálogo principal:** diverge do Foundry e dos MCP servers sem falhar.
- **Confiar em `readOnlyHint`/descrição MCP:** o próprio Learn manda tratar metadata remota como
  entrada não confiável.
- **Aprovar automaticamente tools sem classificação:** transforma ausência de evidência em
  permissão.
- **Transação distribuída simulada:** não existe commit atômico comum aos serviços envolvidos.
- **Middleware universal ou portas de runtime:** contradiz ADR-020 e duplica a volatilidade.

## Evidências externas

- [AgentSchema](https://github.com/microsoft/AgentSchema)
- [Agent Framework MCP source](https://github.com/microsoft/agent-framework/blob/main/python/packages/core/agent_framework/_mcp.py)
- [Connect agents to MCP server endpoints](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/model-context-protocol)
- [Foundry samples](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python)
