---
status: accepted
date: 2026-09-01
challenge: 20260901-0338-autoria-okf-frontend
supersedes_partially:
  - docs/adr/ADR-032-okf-projections-bindings-and-compensable-publication.md#d08
---

# ADR-034 — Autoria independente isola por área e publica Git antes do Foundry

Decisão estrutural aceita pelo desenvolvedor atuando com autoridade de tech lead/arquiteto em
2026-09-01, após revisão das decisões, alternativas, consequências e do threat model associado.

## Contexto

O produto precisa substituir todo o frontend por uma experiência Assured UI própria, sem pacote,
asset, fonte ou identidade visual da Rede D'Or, preservar as URLs e
capacidades atuais e acrescentar autoria OKF ponta a ponta. O mesmo fluxo deve funcionar localmente
sem Azure e, quando conectado, abrir pull request com a identidade do usuário e materializar apenas
o commit integrado usando as capacidades oficiais do Foundry e do AI Search.

A ADR-032 continua sendo a base para projeções, bindings, descoberta MCP, aprovação nativa e saga
compensável. Duas decisões ficaram incompatíveis com o escopo confirmado deste desafio:

- a D08 deixa áreas fora do MVP, mas todo estado novo deve ser isolado pelo par tenant e área;
- o plano anterior associa publicação a Admin, enquanto a separação de responsabilidades mais
  recente reserva configuração ao Admin e aprovação/publicação ao Approver.

Também é necessário desenvolver todas as rotas novas sem desligar o frontend atual e realizar uma
única troca somente após equivalência funcional, responsiva e acessível.

## Decisão

### 1. Um seam de composição mantém `legacy` e `assured`

O modo de frontend será selecionado por configuração `legacy | assured` no composition root. Os dois
modos usam as mesmas URLs públicas e contratos de API; não haverá prefixo `/v2`, duplicação de regra
de negócio nem ativação por usuário. `legacy` permanece o default até a matriz completa de rotas
passar. A ativação de `assured` é uma troca única e reversível de configuração. O modo `assured`
consolida os tokens e componentes React/CSS próprios do projeto e proíbe dependências `@rededor/*`.

As rotas atuais são preservadas, inclusive `/chat` e `/techdocs` como redirects. As capacidades
novas usam `/catalog`, `/catalog/[kind]/[id]`, `/builder`, `/registries`, `/bundles`,
`/bundles/[id]`, `/bundles/[id]/edit`, `/compliance` e `/publications/[id]`. FormFlow é renderer de
Builder e Bundle Editor, não uma seção ou fonte de regra paralela.

### 2. Tenant e área são escopo obrigatório do estado de autoria

Tenant é resolvido pelo `tid` validado. Área é uma entidade tenant-local ligada a grupos Entra e
derivada no servidor a partir dos grupos autorizados do usuário. Um `area_id` recebido do cliente é
somente seleção e nunca autoridade.

Documentos, revisões, ChangeSets, registries, snapshots, checks, aprovações, journals, caches e
publicações são endereçados pelo par tenant e área. App Role autoriza a ação; grupos autorizam a
área; a permissão efetiva é a interseção. Recursos fora desse escopo respondem como ausentes.

Esta decisão substitui somente a D08 da ADR-032 para este produto. Hierarquia e herança entre áreas
continuam fora do escopo; a presença de uma área plana e autorizada entra no MVP.

### 3. Papéis separam consulta, autoria, publicação e administração

- `Reader` consulta recursos permitidos.
- `Author` cria, revisa e submete ChangeSets.
- `Approver` aprova, rejeita e inicia publicação do conjunto exato revisado.
- `Admin` configura áreas, registries, connections e policies administrativas.

Admin não ganha aprovação de publicação implicitamente. Uma pessoa pode publicar somente se também
possuir `Approver`. Builder, proposer e FormFlow não recebem dependência de escrita externa.

### 4. Git é anterior à materialização operacional

Uma aprovação final imutável inicia uma saga persistente: criar ou recuperar branch, gravar o
conteúdo aprovado, criar ou recuperar pull request, aguardar merge, conferir o commit integrado e
materializar. O repositório é a fonte versionada anterior ao recurso operacional.

Azure DevOps usa REST 7.1 com OBO e `vso.code_write`. GitHub usa o MCP oficial por Foundry Toolbox
com OAuth identity passthrough, allowlist mínima e aprovação nativa. A aplicação não recebe nem
persiste o token GitHub e não oferece fallback por PAT.

Cada operação tem chave de idempotência, journal, estado e compensação. Há no máximo três tentativas
automáticas, com backoff exponencial, jitter e respeito a `Retry-After`, somente para 408, 429, 5xx
e falha de transporte. Erro 4xx não transitório, conflito de ref, consentimento ou decisão humana
nunca é repetido automaticamente.

### 5. Somente recursos oficiais são materializados

Após o merge, a aplicação usa as superfícies oficiais verificadas:

| Artefato aprovado | Materialização |
|---|---|
| AgentSchema | nova versão de Prompt Agent |
| pacote agentskills.io | nova versão de Skill na superfície beta |
| definição de Toolbox | nova versão de Toolbox |
| definição e conteúdo de knowledge | Knowledge Source e Knowledge Base no AI Search preview |

`agent-binding` e `mcp-binding` são referências/configuração validada dessas versões.
`middleware-binding` e `adapter-binding` apontam para implementações existentes. `formflow`,
`usecase`, `policy`, `copilot`, `bundle` e `log` permanecem contratos no Git/backend e não fingem
ser recursos Foundry.

Skill em Toolbox aparece como MCP Resource e não é consumida automaticamente por Prompt Agent.
Somente runtime backend compatível pode fazer injeção direta e explícita. Se uma superfície beta ou
preview necessária estiver indisponível, a operação fica bloqueada; não haverá reimplementação.

### 6. Persistência usa o mesmo contrato em SQLite e PostgreSQL

SQLite é o adapter local durável. Azure Database for PostgreSQL Flexible Server é o adapter
conectado. Regras de produto, transições, autorização e idempotência ficam nos módulos donos e são
testadas pela mesma suíte contratual; não pertencem ao ORM ou ao adapter.

O banco guarda somente conteúdo de autoria e metadados mínimos de operação. Tokens, segredos,
headers, URLs de consentimento e respostas externas brutas são proibidos. Auditoria imutável
continua no mecanismo da ADR-023, não é substituída pelo banco transacional.

### 7. Evidência é factual e conformidade bloqueia por fase

Valores de versão, atividade, custo e permissão declaram `measured`, `estimated`, `unavailable` ou
`pending`, além de fonte e instante. Versões vêm da fonte dona; atividade local não se apresenta
como histórico total; custo estimado expõe preço e premissas; permissão é recalculada no backend.

Checks são informativos durante edição. Submissão bloqueia falhas determinísticas. Aprovação e PR
também bloqueiam referência externa, drift, lacuna obrigatória e plano de compensação.
Materialização repete os checks contra o commit integrado e exige merge, hash, conexão,
consentimento, autorização e readiness oficiais. No modo local, checks externos ficam `pending` e
bloqueiam apenas a fase que depende do serviço.

### 8. Retenção minimiza o plano de controle

Rascunhos abandonados e ChangeSets rejeitados/cancelados, com seus snapshots, expiram em 90 dias.
Publicações, journals e aprovações seguem a política de auditoria/WORM do tenant; produção não ativa
publicação sem essa política. Documentos integrados seguem a retenção do Git e telemetria permanece
separada com 30 dias. Legal hold suspende purge sem ampliar a coleta.

## Alternativas consideradas

### Ativação incremental por rota

Reduz o tamanho de cada rollout, mas contraria a substituição única confirmada e expõe dois sistemas
visuais simultaneamente. Rejeitada; slices independentes serão validados sob o seam sem virarem
default isoladamente.

### Novas rotas sob `/v2`

Simplifica a convivência, mas quebra links profundos, duplica navegação e torna a migração parte do
contrato público. Rejeitada em favor das mesmas URLs e de composição interna.

### Área informada e confiada pelo cliente

É simples para a UI, mas cria IDOR e confunde seleção com autoridade. Rejeitada; o servidor deriva e
revalida as áreas a partir da identidade.

### Admin como publicador universal

Reduz a matriz de papéis, mas mistura administração com aprovação e enfraquece segregação de
funções. Rejeitada; Admin precisa possuir Approver para publicar.

### Identidade de serviço ou PAT para Git

Evita consentimento por usuário, mas apaga autoria, amplia privilégio e cria armazenamento de
segredo. Rejeitada em favor de OBO e OAuth identity passthrough.

### Materializar antes do merge ou em paralelo

Reduz latência, mas permite que o recurso operacional anteceda ou divirja da fonte versionada.
Rejeitada; somente o commit integrado é elegível.

### Catálogo e runtime próprios para substituir superfícies preview

Evita bloqueio por disponibilidade, mas cria uma segunda verdade e viola a MÁXIMA MAIOR. Rejeitada;
indisponibilidade é estado explícito.

## Consequências

- **Positiva:** todas as rotas podem ser desenvolvidas e comparadas sem desativar o produto atual.
- **Positiva:** tenant e área formam uma fronteira verificável em toda a jornada.
- **Positiva:** Git, Foundry, Search e MCP continuam fontes donas reconhecíveis.
- **Positiva:** aprovações, retries e falhas parciais ficam auditáveis e retomáveis.
- **Negativa:** a troca única concentra risco de rollout e exige uma matriz extensa de paridade.
- **Negativa:** consentimento delegado e superfícies preview introduzem estados bloqueados legítimos.
- **Negativa:** compensação aumenta o número de estados operacionais e não elimina intervenção manual.

## Validação exigida antes de aceitar

- aprovação explícita de tech lead ou arquiteto;
- revisão do threat model `2026-09-01-okf-authoring-publication.md`;
- contratos offline e smokes autenticados para GitHub, Azure DevOps, Foundry e AI Search;
- matriz negativa de papéis, tenant e área;
- testes de idempotência, concorrência, compensação e reconciliação;
- gate de paridade por rota, Playwright desktop/mobile, teclado, foco e ausência de sobreposição;
- triagem de findings novos de segurança antes do merge.
