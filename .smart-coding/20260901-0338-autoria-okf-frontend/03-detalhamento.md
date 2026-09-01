# Detalhamento técnico — Autoria OKF e evolução completa do frontend

> Arquivo: `.smart-coding/20260901-0338-autoria-okf-frontend/03-detalhamento.md`
> Artefato gerado pela skill `sc-detalhar` (Rede Dor Smart Coding).
> Próxima fase: `sc-fatiar`.
> Baseado em: `.smart-coding/20260901-0338-autoria-okf-frontend/01-entendimento.md` e `02-prd.md`.

## Resumo técnico

O frontend Next.js passa a ter duas composições internas, `legacy` e `cura`, selecionadas no
composition root sem alterar URLs ou APIs. O modo CURA só se torna o padrão após paridade funcional,
responsiva e acessível de todas as rotas. A autoria usa `OkfChangeSet` como unidade versionada,
persistida por um contrato comum em SQLite local e PostgreSQL conectado, sempre sob tenant e área.

A publicação é uma saga explícita: aprovação imutável, branch/commit/PR, confirmação do merge e
materialização pelas superfícies oficiais. GitHub usa Foundry Toolbox/MCP com OAuth identity
passthrough; Azure DevOps usa REST 7.1 com OBO. Nenhum token é persistido e indisponibilidade de uma
capacidade beta ou preview bloqueia a etapa correspondente, sem reimplementação.

## Proposta arquitetural

```text
[Next.js legacy | CURA]
          |
          v
[APIs de autoria e tenant] -> [OKF / FormFlow / Builder / Proposer]
          |                              |
          v                              v
[SQLite | PostgreSQL]          [Catálogos oficiais projetados]
          |
          v
[Publicador compensável] -> [GitHub MCP | Azure DevOps REST]
          |
          v  somente após merge + hash conferido
[Foundry Agent Service | Foundry Toolbox | AI Search]
```

### Componentes afetados

| Componente | Status | Detalhe |
|---|---|---|
| Composition root do frontend | modificado | Seleciona `legacy | cura`; `legacy` permanece default até os gates finais |
| Shell e rotas Next.js | modificados | Redesign integral em CURA, preservando URLs, redirects, auth, i18n e AG-UI |
| `tenancy` | modificado | Resolve áreas autorizadas a partir de grupos Entra e compõe o contexto tenant-área |
| `okf` | modificado | Continua dono do perfil, validação, referências e `OkfChangeSet` |
| `formflow` | modificado | Continua renderer declarativo usado no Builder e Bundle Editor, sem regra paralela |
| `builder` e `proposer` | modificados | Produzem propostas e ChangeSets; nunca escrevem em Git ou Foundry |
| Persistência de autoria | novo | Contrato comum com adapters SQLite e PostgreSQL |
| Publicador | novo | Porta pequena para publicar, consultar, reconciliar e compensar a saga |
| `foundry` | modificado | Projeta somente recursos suportados pelas APIs oficiais |
| `audit` | modificado | Recebe eventos correlacionados; não substitui o journal transacional da saga |

### O que muda vs. o que permanece

| Componente | Status | Detalhe |
|---|---|---|
| URLs públicas atuais | inalterado | Links profundos e redirects continuam válidos |
| Regras de auth e tenant | ampliado | App Roles continuam autorizando ações; grupos Entra passam a limitar a área |
| AgentSchema | inalterado | Continua fonte de verdade de Prompt Agents |
| Foundry, Search e MCP | inalterado | Continuam fontes donas dos recursos operacionais |
| Catálogo da UI | novo contrato | É projeção factual e não uma lista operacional paralela |
| Auditoria WORM | inalterado | Continua seguindo a ADR-023 |
| Workflow declarado | autoria apenas | Pode ser criado e publicado como contrato, mas não é executado neste desafio |

### Fronteiras de responsabilidade

- **Frontend -> API**: envia seleção de área e comandos; nunca decide autorização, estado da saga ou
  validade de referências.
- **Tenancy -> módulos de autoria**: entrega tenant pelo `tid`, áreas derivadas de grupos e App
  Roles; `area_id` do cliente é apenas uma seleção a ser revalidada.
- **Builder/Proposer/FormFlow -> OKF**: produzem proposta e conteúdo; `okf` valida e monta o
  ChangeSet. Nenhum deles publica.
- **Persistência -> domínio**: salva estado, revisões e journal; regras de transição, autorização e
  idempotência permanecem no módulo dono.
- **Publicador -> adapters Git**: usa uma porta de domínio comum, mas clientes e autenticação
  específicos por provedor.
- **Publicador -> Foundry/Search**: materializa somente o commit integrado e somente por APIs
  oficiais verificadas.
- **Journal -> auditoria**: journal permite retomada transacional; auditoria registra evidência
  imutável e correlacionada. Um não substitui o outro.

## Stack e runtime

- **Frontend**: TypeScript 6, Next.js 16.3, React 19.2, App Router, `next-intl`, MSAL,
  CopilotKit/AG-UI e pacotes CURA alinhados na mesma versão 2.x ou superior.
- **Backend**: Python 3.12, FastAPI, arquitetura modular `public.py`/`internal/` e dependências via
  `uv`.
- **Persistência local**: SQLite durável.
- **Persistência conectada**: Azure Database for PostgreSQL Flexible Server, com autenticação Entra
  por managed identity; schema relacional compatível com SQLite.
- **Integrações**: Microsoft Entra ID, Azure DevOps REST 7.1, GitHub MCP oficial via Foundry
  Toolbox, Foundry Agent Service e Azure AI Search.
- **ADRs aplicáveis**: ADR-023 (evidence layer), ADR-032 (projeções, bindings e compensação) e
  ADR-034 (CURA, área e publicação Git-first). A ADR-034 substitui somente a D08 da ADR-032; sua
  matriz de papéis também substitui a atribuição de publicação ao Admin registrada no plano anterior.

## Contratos transversais

- Toda rota autenticada valida bearer token, `tid`, App Roles e contexto da área.
- Rotas de autoria recebem `X-Area-ID`; o valor não é autoridade e é cruzado com os grupos Entra.
- Recurso fora do tenant-área autorizado é tratado como ausente, sem revelar sua existência.
- Escritas criadoras ou retomáveis usam `Idempotency-Key`; repetição com mesmo request retorna o
  recurso anterior, e reutilização com outro request é conflito.
- Atualizações concorrentes usam `If-Match` sobre a revisão; divergência retorna `412`.
- Erros seguem o envelope institucional herdado. Códigos de domínio são estáveis; mensagens ao
  usuário não incluem payload externo, token, segredo ou detalhe de infraestrutura.

## Contratos de API

### Identidade e áreas

| Método e rota | Papel | Entrada | Sucesso | Erros e idempotência |
|---|---|---|---|---|
| `GET /me` | autenticado | token | `200`, identidade, tenant e `areas[]` autorizadas | `401`, `403`; sem efeito |
| `GET /tenant/areas` | Admin | token | `200`, áreas do tenant | `401`, `403`; sem efeito |
| `POST /tenant/areas` | Admin | `{id, name, entra_group_ids[]}` | `201` | `409` ID existente, `422`; não repete criação |
| `PATCH /tenant/areas/{area_id}` | Admin | nome, grupos ou estado; `If-Match` | `200`, área revisada | `404`, `409`, `412`, `422` |

Não existe exclusão física de área. Área referenciada é suspensa para preservar histórico.

### Catálogo e detalhe

| Método e rota | Papel | Entrada | Sucesso | Erros |
|---|---|---|---|---|
| `GET /authoring/catalog` | Reader | `kind`, `state`, `cursor`, `limit`; `X-Area-ID` | `200 {items, next_cursor, snapshot:{id,hash,at}}` | `401`, `403`, `409 SNAPSHOT_STALE`, `422` |
| `GET /authoring/resources/{kind}/{id}` | Reader | `revision` opcional | `200`, definição/projeção, permissions, lifecycle e cost | `401`, `403`, `404`, `422` |
| `GET /authoring/resources/{kind}/{id}/versions` | Reader | cursor e limite | `200`, versões da fonte dona | `401`, `403`, `404`, `422` |
| `GET /authoring/resources/{kind}/{id}/activity` | Reader | cursor e limite | `200`, atividade com cobertura e fonte explícitas | `401`, `403`, `404`, `422` |

Campos derivados usam `{state, value, source, observed_at, reason?}`, em que `state` é `measured`,
`estimated`, `unavailable` ou `pending`. Versão vem da fonte dona; atividade local não se apresenta
como histórico total; custo estimado expõe preço e premissas; permissões são recalculadas no backend.

### ChangeSets

| Método e rota | Papel | Entrada | Sucesso | Erros e idempotência |
|---|---|---|---|---|
| `POST /authoring/changesets` | Author | fonte, snapshot e operações; `Idempotency-Key` | `201`, ou `200` no replay | `401`, `403`, `409`, `422` |
| `GET /authoring/changesets/{id}` | Reader | `X-Area-ID` | `200`, agregado e revisão atual | `401`, `403`, `404` |
| `PATCH /authoring/changesets/{id}` | Author | alterações; `If-Match` | `200`, nova revisão | `401`, `403`, `404`, `409`, `412`, `422` |
| `POST /authoring/changesets/{id}/validations` | Author | revisão e fase | `201`, relatório imutável | `401`, `403`, `404`, `409`, `422` |
| `POST /authoring/changesets/{id}/submit` | Author | revisão/hash | `200`, ChangeSet congelado | `401`, `403`, `404`, `409`, `412`, `422` |
| `POST /authoring/changesets/{id}/decisions` | Approver | `{decision, reason, content_hash}` | `200`, decisão imutável | `401`, `403`, `404`, `409`, `412`, `422` |

Qualquer edição produz nova revisão e invalida aprovação anterior. A decisão sempre referencia
tenant, área, revisão e hash normalizado exatos.

### Publicação e reconciliação

| Método e rota | Papel | Entrada | Sucesso | Erros e idempotência |
|---|---|---|---|---|
| `POST /authoring/publications` | Approver | `{changeset_id, provider, connection_id, repository, target_branch}`; `Idempotency-Key` | `202`, publicação e PR em processamento | `401`, `403`, `404`, `409`, `422`, `424`, `503` |
| `GET /authoring/publications/{id}` | Reader | `X-Area-ID` | `200`, estado e passos sanitizados | `401`, `403`, `404`; sem efeito |
| `POST /authoring/publications/{id}/reconcile` | Approver | `Idempotency-Key`, `If-Match` | `202`, confirmação de merge/materialização em processamento | `401`, `403`, `404`, `409`, `412`, `422`, `424`, `503` |
| `POST /authoring/publications/{id}/compensations` | Admin | ação permitida para agregado em `compensation_required` | `202`, compensação em processamento | `401`, `403`, `404`, `409`, `412`, `422`, `424`, `503` |

Leituras nunca disparam escrita. A reconciliação é uma ação explícita da UI; confirma o merge no
provedor, compara o commit integrado e somente então avança a materialização.

## Modelos de dados e schemas

Todos os identificadores abaixo são obrigatórios. `tenant_id`, `area_id` e os object IDs Entra são
identificadores corporativos pessoais; conteúdo OKF pode conter dados de autoria, mas dado clínico,
financeiro, segredo e credencial são proibidos.

### `authoring_areas`

- Campos: `tenant_id UUID`, `area_id UUID`, `area_key VARCHAR(63)` imutável, `name VARCHAR(120)`,
  `status active|suspended`, `revision BIGINT`, `created_at`, `updated_at`.
- Chaves: PK `(tenant_id, area_id)`; UNIQUE `(tenant_id, area_key)`.
- Retenção: enquanto houver referência; sem delete físico.

### `authoring_area_groups`

- Campos: `tenant_id UUID`, `area_id UUID`, `entra_group_id UUID`, `created_at`.
- Chaves: PK nos três IDs; FK composta para `authoring_areas` com `ON DELETE RESTRICT`.
- Relação: uma área possui zero ou mais grupos autorizados; não existe membership própria de usuário.

### `authoring_changesets`

- Campos: tenant, área, `changeset_id UUID`, `state draft|submitted|approved|rejected|superseded`,
  `current_revision BIGINT`, `source manual|builder|import|migration`, `created_by_oid`, timestamps.
- Chaves: PK composta no escopo tenant-área; FK para área com `ON DELETE RESTRICT`.
- Retenção: rascunho abandonado ou rejeitado/cancelado por 90 dias; publicado conforme auditoria.

### `authoring_changeset_revisions`

- Campos: chave do ChangeSet, `revision BIGINT`, `base_snapshot_id`, `content JSONB/TEXT`,
  `content_hash CHAR(64)`, `author_oid`, `created_at`.
- Relação: várias revisões imutáveis por ChangeSet; nenhuma sobrescrita ou delete físico.
- Bundles, FormFlows, policies, use cases e bindings permanecem documentos nesse conteúdo e no Git;
  não ganham tabelas operacionais paralelas.

### `authoring_validation_reports`

- Campos: `report_id`, ChangeSet e revisão, `overall approved|failed|pending`, `checks JSONB/TEXT`,
  `actor_oid`, `created_at`.
- Relação: relatórios append-only; uma nova execução cria evidência nova.

### `authoring_decisions`

- Campos: `decision_id`, ChangeSet e revisão, `content_hash`, `approve|reject`, `reason`,
  `approver_oid`, `roles`, `audit_ref`, `created_at`.
- Relação: decisão imutável presa ao conteúdo exato; não é atualizada após criação.

### `authoring_publications`

- Campos: tenant, área, `publication_id`, ChangeSet, revisão e hash, `decision_id`, `provider`,
  `connection_id`, `repository_id`, `target_branch`, `state`, `pr_id`, `pr_url`, `merge_sha`,
  `revision`, `actor_oid`, timestamps.
- Relações: FKs compostas com `ON DELETE RESTRICT`; uma aprovação pode originar publicação retomável.

### `authoring_publication_steps`

- Campos: publicação, `step_id`, ordem, tipo, `status pending|running|succeeded|failed|compensated|intervention_required`,
  `attempt`, `external_ref JSON`, `sanitized_error_code`, timestamps.
- Chaves: UNIQUE por publicação e ordem. `external_ref` contém somente metadados allowlisted.

### `authoring_idempotency_keys`

- Campos: tenant, área, ator, operação, `key_hash`, `request_hash`, `resource_type`, `resource_id`,
  `response_status`, `created_at`, `expires_at`.
- Chave: UNIQUE no escopo tenant-área-ator-operação-chave.
- Proibição: a chave original, tokens, headers e resposta externa bruta não são persistidos.

## Integrações externas

### Microsoft Entra ID

- Propósito: autenticação, `tid`, App Roles, grupos autorizados e OBO.
- Autorização efetiva: App Role intersectada com a área derivada dos grupos.
- Falha: acesso negado sem fallback local de identidade.

### Azure DevOps Repos

- Protocolo: REST 7.1 para push/branch, commit, criação de PR e consulta de merge.
- Autenticação: OBO com escopo mínimo `vso.code_write`.
- Timeout/retry: 30 s por operação; até três tentativas com backoff exponencial, jitter e
  `Retry-After`, somente para 408, 429, 5xx e transporte.
- Falha: 4xx não transitório, conflito de ref e autorização ficam bloqueados e exigem ação explícita.

### GitHub

- Protocolo: servidor MCP oficial chamado por Foundry Toolbox, com allowlist mínima.
- Autenticação: OAuth identity passthrough e consentimento por usuário; token não é exposto ao app.
- Timeout/retry: mesma política transitória do Azure DevOps; antes de nova escrita, journal e recurso
  remoto são consultados.
- Falha: consentimento ou aprovação pendente pausa a saga; não existe fallback por PAT ou GitHub App.

### Foundry Agent Service e Azure AI Search

- Propósito: materialização pós-merge pelas APIs oficiais.
- Matriz:

| Artefato | Resultado operacional |
|---|---|
| AgentSchema | nova versão de Prompt Agent |
| pacote agentskills.io | nova versão de Skill na superfície beta |
| definição de Toolbox | nova versão de Toolbox |
| definição/conteúdo de knowledge | Knowledge Source e Knowledge Base no AI Search preview |
| `agent-binding`, `mcp-binding` | referência/configuração validada das versões oficiais |
| `middleware-binding`, `adapter-binding` | referência a implementação existente |
| FormFlow, use case, policy, copilot, bundle e log | permanecem no Git/backend |

Skills aparecem em Toolbox como MCP Resources e não são consumidas automaticamente por Prompt
Agents. Injeção direta só pode ocorrer em runtime backend compatível. Superfície beta/preview
indisponível bloqueia a operação, sem catálogo ou runtime substituto.

## Fluxos críticos

### Máquina de estados

- ChangeSet: `draft -> submitted -> approved | rejected`.
- Editar um rejeitado cria nova revisão e retorna a `draft`; aprovado é imutável.
- Publicação: `preparing_pr -> pr_open -> merge_confirmed -> materializing -> completed`.
- Falha parcial: `compensating -> compensated | compensation_required`.
- Merge ausente em `reconcile` retorna conflito sem alterar `pr_open`.
- Lock transacional por `publication_id`, `If-Match` e idempotência impedem avanços concorrentes.

### Gates por fase

- Edição: checks informativos em tempo real.
- Submissão: schema, referências internas, segredo, tenant-área, Author e concorrência bloqueiam.
- Aprovação/PR: repete os anteriores e acrescenta referências externas, drift MCP, lacunas
  obrigatórias, plano de compensação e Approver.
- Materialização: repete tudo contra o commit integrado e exige merge, igualdade de hash, conexão,
  consentimento, autorização do serviço e readiness oficial.
- Check externo `pending` bloqueia somente a fase que depende do serviço.

### Troca do frontend

- Preservadas: `/`, `/d/[domain]`, `/chat`, `/techdocs`, `/usecases[/[id]]`,
  `/agents[/[name][/chat]]`, `/copilots[/novo|/[name]]`, `/knowledge`, `/skills`, `/tickets`,
  `/evals`, `/assistants`, `/audit`, `/admin/users` e `/admin/connections`.
- Novas: `/catalog`, `/catalog/[kind]/[id]`, `/builder`, `/registries`, `/bundles`,
  `/bundles/[id]`, `/bundles/[id]/edit`, `/compliance` e `/publications/[id]`.
- FormFlow é renderer/modo de edição, sem rota própria.
- `cura` só vira default quando todas as rotas passam ações/estados, RBAC, links profundos,
  desktop/mobile, acessibilidade, testes e build.

### Responsividade CURA

- Desktop: painéis redimensionáveis com dimensões mínimas estáveis.
- Tablet: dois painéis; terceiro conteúdo em drawer.
- Mobile: uma superfície por vez por tabs/segmented control; árvore e inspeção em drawers; canvas
  não é miniaturizado; editor e preview viram tabs.
- Tabelas mantêm colunas prioritárias e movem detalhes para expansão/drawer; rolagem horizontal só
  quando a comparação tabular for essencial.
- Ações críticas sticky não cobrem conteúdo; foco, ordem de leitura, teclado e retorno ao elemento
  de origem são preservados.

## Tratamento de erros

- **Validação**: `422`; retorna campos/checks acionáveis, sem stack trace.
- **Autenticação/autorização**: `401`/`403`; recursos fora do escopo não revelam existência.
- **Estado/conflito**: `409`; inclui código estável como `SNAPSHOT_STALE` ou estado incompatível.
- **Concorrência**: `412`; cliente deve recarregar/rebasear, nunca sobrescrever silenciosamente.
- **Dependência**: `424`; operação oficial respondeu, mas uma dependência necessária falhou.
- **Indisponibilidade**: `503`; apenas falhas transitórias elegíveis entram em retry.
- Mensagem externa é sanitizada antes de qualquer persistência. Consentimento, decisão humana,
  conflito de ref e 4xx não transitório nunca são repetidos automaticamente.

## Observabilidade

- **Logs**: operação, estado anterior/novo, tenant, área, ator, request/correlation ID, publicação,
  passo, tentativa, duração e código sanitizado; nunca conteúdo bruto ou credencial.
- **Métricas**: duração e resultado por operação/provedor, retries, pendências, compensações,
  intervenções, conflitos de revisão e checks por estado. IDs de usuário/documento não são labels.
- **Traces**: spans para validar, submeter, decidir, criar branch/commit/PR, consultar merge,
  comparar hash, materializar e compensar; correlação atravessa adapters sem transportar token.
- **Alertas**: publicação presa, repetição de 429/5xx, crescimento de `compensation_required`,
  divergência de hash e falha de auditoria/WORM.

## Segurança e compliance

- **Autenticação e autorização**: token Entra validado; tenant por `tid`; área por grupos Entra;
  Reader consulta, Author cria/submete, Approver decide/publica e Admin configura. Como exceção de
  remediação, Admin pode iniciar compensação somente quando o agregado já estiver em
  `compensation_required`; isso não concede aprovação nem publicação. Admin não recebe Approver
  implicitamente.
- **Dados sensíveis**: identidade/autoria e IDs corporativos são dados pessoais de baixo volume.
  Dados clínicos, financeiros, tokens, segredos e credenciais são proibidos. Classificação
  NORDOR-107: pessoal/corporativo, não clínico.
- **Criptografia**: TLS em trânsito; SQLite protegido pelo host de desenvolvimento; PostgreSQL e
  auditoria usam criptografia gerenciada da plataforma e acesso passwordless.
- **Auditoria**: autor, editor, aprovador, revisão, hashes, PR, merge, materialização, tentativas e
  compensações são correlacionáveis na evidence layer da ADR-023.
- **Retenção**: rascunhos abandonados e ChangeSets rejeitados/cancelados por 90 dias; publicações,
  journals e aprovações seguem WORM do tenant; Git rege documentos integrados; telemetria por 30
  dias; legal hold suspende purge.
- **Threat model exigido?**: sim. Arquivo:
  `.smart-coding/_threat-models/2026-09-01-okf-authoring-publication.md`. Gatilhos: novas
  integrações, identidade delegada, nova fronteira tenant-área, persistência e saga distribuída.

## Decisões técnicas registradas

1. O composition root seleciona `legacy | cura`, nas mesmas URLs e APIs, com uma ativação única.
2. Tenant vem do `tid`; área é tenant-local, ligada a grupos Entra e revalidada no servidor.
3. App Role define a ação e grupos definem a área; a permissão efetiva é a interseção.
4. `OkfChangeSet` é a unidade de autoria; revisões, relatórios e decisões são imutáveis.
5. SQLite e PostgreSQL implementam o mesmo contrato; regra de produto não pertence ao adapter.
6. Builder, proposer e FormFlow produzem proposta, nunca escrita externa.
7. A publicação é Git-first, retomável, idempotente e materializa apenas após merge e hash válidos.
8. Azure DevOps usa OBO/REST 7.1; GitHub usa Toolbox/MCP/OAuth passthrough, sem PAT.
9. Apenas AgentSchema, Skill, Toolbox e knowledge materializam recursos oficiais; outros documentos
   permanecem contratos no Git/backend.
10. Evidência derivada declara estado e fonte; ausência de medição nunca vira dado plausível.
11. Conformidade bloqueia por fase e `pending` nunca é promovido por fallback.
12. Auditoria imutável e journal da saga têm propósitos distintos e ambos são obrigatórios.
13. Os padrões responsivos preservam a tarefa, reorganizando painéis, tabelas, canvas e editores.
14. A ADR-034 foi aceita, supersede a D08 da ADR-032 e substitui a governança de papéis do plano
  anterior, sem alterar as demais decisões da ADR-032.

## Questões em aberto

Nenhuma — pronto para `sc-fatiar`.

---

## Histórico

Log cronológico de revisões deste detalhamento (mais antigo primeiro). Mantido por `sc-revisar`.

- (sem revisões ainda)