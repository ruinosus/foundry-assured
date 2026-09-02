# Plataforma de copilotos autores de OKF — backlog de implementação

> **Status:** F00, F01 e F02 concluídas; próxima fatia F03
>
> **Origem:** protótipos em `Análise de wizard AG-UI/`, análise em
> `Análise de wizard AG-UI/ANALISE-ACHADOS.md` e decisão desta conversa: um copiloto é um autor
> restrito de documentos OKF; ele propõe, o humano decide, o publicador materializa.
>
> **Rastreamento:** marque os itens com `[x]` somente depois que os critérios de aceite e os gates
> da task estiverem verdes. Não inferir conclusão pela existência de arquivos.

## 1. Objetivo

Permitir que uma pessoa descreva um caso de uso, selecione capacidades reais do tenant — começando
por um servidor MCP de tickets — e receba do Builder uma proposta coerente de documentos OKF. A
proposta pode criar ou revisar um ou mais documentos autorizados, reutilizar componentes já
registrados e recomendar lacunas. Nada é publicado ou executado sem validação e decisão humana.

O primeiro cenário vertical deve permitir:

1. selecionar um MCP que exponha `check_existing_ticket` e `create_ticket`;
2. descobrir as tools e classificá-las como leitura ou escrita;
3. receber a recomendação de consultar duplicidade antes de criar;
4. reutilizar um middleware compatível ou declarar a lacuna de um novo contrato;
5. gerar um patch OKF para `copilot`, `usecase` e bindings necessários;
6. revisar diff, referências, impacto, papel exigido e payload;
7. publicar uma nova versão após aprovação explícita;
8. executar `create_ticket` somente após aprovação do papel exigido.

## 2. Decisões fixadas

- [x] O copiloto escreve **propostas de documentos OKF**, não recursos diretamente.
- [x] A unidade de autorização é `type + operation`, por exemplo `usecase:create`.
- [x] FormFlow é a interface de edição; não é o limite conceitual da escrita.
- [x] O patch proposto pode abranger mais de um documento, mas sua revisão é atômica e explícita.
- [x] Publicação continua separada do propositor, conforme ADR-022.
- [x] Documento publicado é imutável; revisão cria versão nova.
- [x] Referências vêm dos catálogos reais do tenant; nomes desconhecidos são recusados ou
  declarados como lacuna, nunca inventados silenciosamente.
- [x] Tool MCP de escrita exige política, papel e HITL; a classificação mais restritiva vence.
- [x] Middleware e adapter existentes são referenciados por binding; implementação não é copiada
  para o documento do copiloto.
- [x] Quando faltar implementação, o Builder pode propor contrato/scaffold, mas deve dizer que a
  capacidade ainda não existe e não pode ser habilitada.
- [x] Toda integração Microsoft usa capacidade/SDK oficial; código próprio se limita à cola e à
  assurance.

## 3. Modelo de escrita pretendido

```yaml
type: copilot
resource: ticket-builder

writes:
  - {type: usecase, operations: [create, revise]}
  - {type: agent-binding, operations: [create, revise]}
  - {type: mcp-binding, operations: [create, revise]}
  - {type: middleware-binding, operations: [create, revise]}

cannotWrite:
  - {type: policy}
  - {type: connection}
  - {type: middleware-implementation}
  - {type: tenant-config}
```

Fluxo obrigatório:

```text
necessidade + catálogo real
          ↓
proposta de ChangeSet OKF
          ↓
validação estrutural, semântica e de autorização
          ↓
diff legível + impacto + lacunas + papel
          ↓
decisão humana
          ↓
publicação versionada
          ↓
materialização usando Foundry / Agent Framework / MCP
```

## 4. Definition of Done global

Uma task só termina quando:

- [ ] comportamento e contrato têm teste offline determinístico;
- [ ] autorização negativa está testada, não apenas o caminho feliz;
- [ ] isolamento entre tenants está testado quando houver catálogo ou persistência;
- [ ] nenhuma assinatura de SDK foi presumida; a pesquisa da MÁXIMA MAIOR está registrada;
- [ ] imports cross-module passam somente por `public.py`;
- [ ] `uv run --project apps/backend --no-sync python scripts/gates.py` está verde;
- [ ] testes frontend aplicáveis e build estão verdes;
- [ ] documentação de estado atual foi atualizada sem tratar proposta como entregue;
- [ ] nenhuma credencial, token ou payload sensível entrou em log, fixture ou documento OKF;
- [ ] os protótipos continuam distinguindo claramente o que existe do que é proposta.

## 5. Dependências entre fases

```text
F00 → F01 → F02 → F03 → F04 → F05 → F06
                   └──────→ F07 ──────┘
                         F06 → F08 → F09
                         F06 → F10
                         F09 → F11
                         F08 + F09 + F10 → F12
```

- **MVP demonstrável:** F00–F06.
- **MVP operacional:** F00–F09.
- **Visão completa dos protótipos:** F00–F12.

---

## F00 — Verificar capacidades oficiais e fechar decisões arquiteturais

**Objetivo:** impedir que o plano comece reimplementando Foundry, Agent Framework, MCP ou Azure.

**Dependências:** nenhuma.

### TODO

- [x] Usar a skill `sdk-verify` e pesquisar SDK instalado, Learn, `microsoft-foundry` e samples.
- [x] Confirmar a API oficial para listar agentes, knowledge bases, skills, toolboxes e connections.
- [x] Confirmar como o Agent Framework consome servidor MCP remoto e descobre tools.
- [x] Confirmar a primitiva oficial de aprovação de tool MCP e seu suporte a classificação por tool.
- [x] Confirmar onde metadados customizados e versões podem ser persistidos no Foundry sem criar
  catálogo duplicado.
- [x] Mapear qual recurso oficial materializa cada tipo OKF.
- [x] Medir a lacuna real para `mcp-binding`, `middleware-binding` e ChangeSet multi-documento.
- [x] Decidir se `type: agent` é projeção do AgentSchema existente ou novo documento. Não permitir
  duas fontes de verdade.
- [x] Decidir nomenclatura: `mcp` vs `mcp-binding`, `middleware` vs `middleware-binding`.
- [x] Decidir se catálogo MCP guarda snapshot assinado das tools ou sempre redescobre no servidor.
- [x] Criar/atualizar ADR com as decisões e alternativas recusadas.

### Critérios de aceite

- [x] Existe uma matriz `necessidade → capacidade oficial → cola necessária → evidência`.
- [x] Nenhuma task posterior depende de assinatura de SDK não verificada.
- [x] Há uma única fonte de verdade para agente, catálogo e versão publicada.
- [x] O tamanho da lacuna própria está explícito antes de começar o código.

**Decisão:** [ADR-032](../../adr/ADR-032-okf-projections-bindings-and-compensable-publication.md).

---

## F01 — Perfil estrito de autoria sobre OKF

**Objetivo:** definir os tipos, identidade, versão, referências e estados que sustentam toda a
plataforma.

Este contrato é um perfil estrito de autoria do produto sobre o Open Knowledge Format v0.2. Ele
não redefine conformidade OKF: o verificador upstream continua aceitando extensões e links
quebrados conforme a spec; o perfil exige mais somente nos documentos que o produto pode publicar.

**Dependências:** F00.

### TODO

- [x] Preservar o envelope OKF (`type`, `resource`, `status`, `generated`) e conter o contrato do
  produto em `x-foundry-authoring`: `profile_version`, `id`, `revision`, `publication_state`,
  `tenant`, `area`, `supersedes` e `spec`.
- [x] Definir schemas para `copilot`, `usecase`, `formflow`, `policy`, `agent-binding`,
  `mcp-binding`, `middleware-binding`, `adapter-binding`, `bundle` e `log`.
- [x] Definir identidade pelo caminho e regras de normalização sem colisão entre tenants.
- [x] Definir referência por revisão e regra para referência flutuante, se admitida.
- [x] Definir estados de publicação `draft`, `proposed`, `quarantined`, `shadow`, `active`,
  `deprecated`, sem reutilizar o `status` do OKF com outro significado.
- [x] Definir `writes[]` por `type + operations` e a semântica de `cannotWrite[]`.
- [x] Definir `requires`, `targets`, `approval`, `cost`, `citation` e `gaps`.
- [x] Definir compatibilidade e migração do OKF atual (`formflow`, copilots e docbundles).
- [x] Criar fixtures válidas e inválidas, incluindo o caso de tickets.
- [x] Criar gate do perfil de autoria por tipo e `profile_version`, separado do gate de
  conformidade OKF v0.2.

### Critérios de aceite

- [x] Um parser estruturado valida todos os tipos sem manipulação ad hoc de strings.
- [x] Documento desconhecido ou versão incompatível falha de forma explícita.
- [x] Referência entre documentos autoráveis inexistente não é aceita como disponível; resolução
  contra recursos operacionais do Foundry/MCP pertence às F03/F04.
- [x] O schema distingue contrato/binding de implementação executável.
- [x] O formato preserva legibilidade humana em markdown.

### Testes mínimos

- [x] round-trip parse/serialize sem perda semântica;
- [x] path traversal e colisão de identidade recusados;
- [x] revisão publicada não pode ser sobrescrita;
- [x] `cannotWrite` prevalece sobre `writes`;
- [x] fixture de ticket referencia somente tipos e campos válidos.

---

## F02 — ChangeSet OKF: proposta multi-documento

**Objetivo:** evoluir `propose_field` para uma proposta estruturada que possa criar e revisar um
conjunto coerente de documentos.

**Dependências:** F01.

### TODO

- [x] Definir `OkfChangeSet` com identificador, base version, operações, dependências e justificativa.
- [x] Suportar `create`, `revise` e `deprecate`; excluir `delete` do primeiro ciclo.
- [x] Representar patch por estrutura YAML/JSON; gerar markdown apenas na borda.
- [x] Validar cada operação contra `copilot.writes` e `cannotWrite`.
- [x] Validar o grafo de referências do ChangeSet antes de mostrar a proposta.
- [x] Permitir que documentos do mesmo ChangeSet referenciem recursos criados nele.
- [x] Calcular diff por documento e resumo semântico do conjunto.
- [x] Registrar procedência por operação, campo e fonte consultada.
- [x] Registrar lacunas separadamente de recursos reais.
- [x] Manter o ChangeSet efêmero até a decisão; não criar recurso durante a proposta.
- [x] Adicionar gate que impeça o módulo proposer de chamar publicadores.

### Critérios de aceite

- [x] O Builder pode propor `copilot + usecase + mcp-binding` em uma única resposta.
- [x] Operação fora do domínio de escrita é recusada antes da revisão.
- [x] Referência criada no mesmo ChangeSet resolve; referência externa inexistente falha.
- [x] O propositor não possui dependência de escrita ou publicação.
- [x] O usuário consegue aceitar, editar ou descartar por documento e confirmar o conjunto final.

### Testes mínimos

- [x] criação multi-documento válida;
- [x] revisão com base version desatualizada detecta conflito;
- [x] tentativa de alterar `policy`/`connection` é recusada;
- [x] nome inventado pelo modelo aparece como lacuna, não como referência válida;
- [x] proposta descartada não deixa persistência residual.

---

## F03 — Binding MCP, Toolbox e snapshot de descoberta

**Objetivo:** referenciar Toolboxes/servidores MCP oficiais, descobrir suas tools e oferecer ao
Builder uma projeção confiável e isolada por tenant, sem criar catálogo operacional paralelo.

**Dependências:** F01 e verificação F00.

### TODO

- [ ] Definir `mcp-binding` como referência a Toolbox + versão/default version; servidor MCP direto
  só quando não houver Toolbox aplicável.
- [ ] Projetar URL e connection a partir do recurso oficial; persistir localmente apenas binding,
  classificação administrativa e snapshot de evidência/drift.
- [ ] Nunca armazenar segredo; referenciar connection do Foundry ou identidade OBO.
- [ ] Implementar descoberta oficial de tools e seus schemas de entrada/saída via MCP `tools/list`.
- [ ] Definir origem da classificação leitura/escrita e comportamento quando ela estiver ausente.
- [ ] Aplicar fail-closed: tool sem classificação confiável não pode executar escrita.
- [ ] Detectar mudanças entre descobertas: tool removida, schema alterado, permissão alterada.
- [ ] Colocar binding novo em `shadow` ou `quarantined`, conforme risco.
- [ ] Expor projeção do catálogo oficial do tenant para Builder e FormFlow sem lista duplicada no
  backend ou frontend.
- [ ] Consultar disponibilidade/health na fonte operacional, sem persistir lifecycle local
  concorrente.
- [ ] Criar endpoint/teste de conformidade que não execute a tool durante descoberta.

### Critérios de aceite

- [ ] O Toolbox/MCP de tickets aparece na projeção com `check_existing_ticket` e `create_ticket`.
- [ ] O Builder recebe schemas reais e classificação de cada tool.
- [ ] Tenant A não vê servidor, tool ou connection do tenant B.
- [ ] Alteração incompatível no servidor bloqueia promoção até nova revisão.
- [ ] Tool de escrita nunca é marcada como automática.

### Testes mínimos

- [ ] descoberta bem-sucedida e falhas de auth/timeout/schema inválido;
- [ ] SSRF: URL e redirects obedecem política de egress;
- [ ] classificação ausente/maliciosa falha fechada;
- [ ] isolamento multi-tenant;
- [ ] nenhum segredo é serializado ou logado.

---

## F04 — Catálogo unificado para recomendação e reuso

**Objetivo:** dar ao Builder uma visão factual dos recursos disponíveis e das incompatibilidades,
sem manter uma segunda lista.

**Dependências:** F03.

### TODO

- [ ] Estender `catalog_snapshot()` com MCPs, tools, middlewares, adapters, policies e formflows.
- [ ] Incluir capabilities, contratos, lifecycle, área, custo e dependências — nunca segredos.
- [ ] Criar busca/ranking determinístico de compatibilidade antes da explicação do modelo.
- [ ] Definir regras de compatibilidade: schema aceito/emitido, estágio, papel, área, adapter e custo.
- [ ] Separar `available`, `compatible`, `requires_configuration`, `shadow` e `missing`.
- [ ] Fazer o modelo explicar recomendações usando somente IDs presentes no snapshot.
- [ ] Reaproveitar o padrão `reuse` do proposer atual.
- [ ] Exibir por que um recurso foi recomendado e por que outro foi descartado.
- [ ] Registrar versão/hash do catálogo usado na proposta para auditoria e detecção de stale data.

### Critérios de aceite

- [ ] Para o caso de tickets, o Builder recomenda verificar existência antes da criação.
- [ ] Se `duplicate-ticket-check` compatível existir, recomenda reuso e não novo middleware.
- [ ] Se não existir, declara lacuna e propõe contrato, sem afirmar que a implementação existe.
- [ ] Nenhum ID fora do catálogo entra no ChangeSet como referência válida.
- [ ] Recomendação não concede autorização nem promove lifecycle.

### Testes mínimos

- [ ] reuso compatível;
- [ ] homônimo incompatível não é recomendado;
- [ ] catálogo vazio produz lacuna explícita;
- [ ] item em sombra aparece como não promovido;
- [ ] catálogo alterado entre proposta e publicação exige revalidação.

---

## F05 — Builder autor de OKF

**Objetivo:** fazer o agente da tela transformar necessidade + catálogo em ChangeSet OKF restrito.

**Dependências:** F02 e F04.

### TODO

- [ ] Atualizar o AgentSchema do Builder para propor documentos, bindings, reuso e lacunas.
- [ ] Atualizar eval-case no mesmo PR, conforme a skill `prompt-change`.
- [ ] Fornecer ao agente catálogo e schemas como contexto factual delimitado.
- [ ] Expor tool de frontend `propose_okf_changeset`, mantendo `propose_field` para compatibilidade.
- [ ] Implementar validação determinística da resposta antes de renderizar.
- [ ] Retornar erros por operação/documento sem descartar o restante silenciosamente.
- [ ] Exigir justificativa para cada middleware/adapter recomendado.
- [ ] Impedir que o agente proponha credencial, segredo, policy ou papel fora da sua autoridade.
- [ ] Medir desfecho do ChangeSet: aceito, editado, parcialmente aceito, descartado.
- [ ] Publicar a nova versão do prompt no Foundry após validação local.

### Critérios de aceite

- [ ] A frase “quero abrir tickets pelo MCP X” gera a estrutura esperada do cenário vertical.
- [ ] A proposta cita tools e componentes reais do catálogo.
- [ ] O Builder distingue binding existente, contrato proposto e implementação ausente.
- [ ] O Builder nunca chama endpoint de publicação.
- [ ] O eval-case cobre recomendação de `check_existing_ticket` antes de `create_ticket`.

### Gates específicos

- [ ] `uv run python -m eval.prompt_contract_test`;
- [ ] gate read-only do proposer/Builder;
- [ ] eval offline contra catálogo conhecido;
- [ ] teste de prompt injection vindo de descrição de tool MCP.

---

## F06 — Revisão, validação e publicação versionada

**Objetivo:** transformar um ChangeSet aprovado em novas versões OKF, com revisão humana legível e
sem atalho entre proposta e publicação.

**Dependências:** F05.

### TODO

- [ ] Criar tela de diff multi-documento com resumo, versão base e dependências.
- [ ] Mostrar para cada operação: antes/depois, fontes, justificativa, lifecycle e impacto.
- [ ] Mostrar tools de escrita, payload previsto, policy e papel exigido.
- [ ] Exigir motivo em rejeição e registrar edição antes da aprovação.
- [ ] Revalidar schema, referências, catálogo, RBAC e conflito de versão no momento da publicação.
- [ ] Publicar novas versões sem sobrescrever as anteriores.
- [ ] Registrar autor da proposta, editor, aprovador e hashes; nunca registrar segredo/conteúdo
  sensível desnecessário.
- [ ] Pré-validar o conjunto e publicar como saga compensável com journal; nunca prometer
  atomicidade entre serviços e sempre mostrar estado incompleto explicitamente.
- [ ] Manter publicador em módulo separado e exigir Admin para publicação de recurso; Approver/Admin
  aplica-se somente à aprovação de tool durante execução.
- [ ] Atualizar listagens a partir da fonte publicada, sem cache/catalogação paralela permanente.

### Critérios de aceite

- [ ] O usuário entende “o que será criado”, “o que será executável” e “o que ainda falta”.
- [ ] ChangeSet stale não publica sem nova revisão.
- [ ] A aprovação no chat não substitui a aprovação de publicação de recurso.
- [ ] A versão anterior permanece consultável e não é editada.
- [ ] Falha parcial não aparece como sucesso integral.

### Testes mínimos

- [ ] usuário sem Admin não publica;
- [ ] aprovador não pode aprovar mudança fora do seu tenant/área;
- [ ] conflito otimista de versão;
- [ ] rollback/compensação de falha parcial;
- [ ] diff/payload exibido é exatamente o que será persistido.

---

## F07 — UX FormFlow para autoria de documentos

**Objetivo:** evoluir a tela de “campo em foco” para autoria assistida de um conjunto de documentos,
sem perder a ergonomia do `propose_field`.

**Dependências:** F02 e F05.

### TODO

- [ ] Adicionar modo `campo` e modo `documentos` no dock do Builder.
- [ ] Tornar ações de IA sempre descobríveis, não apenas no hover.
- [ ] Renderizar árvore do ChangeSet: documento, operação, validação e pendências.
- [ ] Permitir editar proposta antes de aceitar, preservando autoria/procedência.
- [ ] Exibir diff antes/depois para revisões e documento inteiro para criações.
- [ ] Exibir catálogo selecionado e motivo de cada recomendação.
- [ ] Diferenciar visualmente: existente, binding novo, contrato proposto, implementação ausente.
- [ ] Mostrar validação em tempo real e impedir publicação com erro.
- [ ] Preservar revisão resumida para negócio e documento técnico em abas distintas.
- [ ] Validar responsividade, acessibilidade, teclado, foco e ausência de sobreposição.
- [ ] Usar CURA e atualizar protótipos para refletir apenas comportamento implementado.

### Critérios de aceite

- [ ] A pessoa consegue criar o cenário de tickets sem editar YAML manualmente.
- [ ] Nenhuma lacuna é apresentada como capacidade pronta.
- [ ] O dock mantém o documento/operacão em foco visível.
- [ ] A revisão mostra todas as operações do ChangeSet antes do gesto final.
- [ ] Screenshots Playwright desktop/mobile não apresentam cortes ou sobreposição.

---

## F08 — Execução MCP com política de tool de escrita

**Objetivo:** materializar o binding aprovado no runtime e executar tools de leitura/escrita com
governança correta.

**Dependências:** F03 e F06.

### TODO

- [ ] Criar cliente MCP remoto usando biblioteca oficial confirmada em F00.
- [ ] Resolver identidade por OBO ou connection do Foundry, sem copiar credenciais.
- [ ] Aplicar timeout, retry seguro, circuit breaker oficial quando disponível e teto de custo.
- [ ] Executar tools de leitura conforme contrato e ACL do chamador.
- [ ] Configurar `approval_mode`/`require_approval` nativo por tool de escrita e traduzir seu evento
  para a UI; código próprio limita-se ao role gate e à decisão de assurance.
- [ ] Aplicar “mais restritivo vence” entre classificação da tool, policy e RBAC.
- [ ] Revalidar payload após edição humana e antes da execução.
- [ ] Associar execução à versão exata dos documentos OKF.
- [ ] Registrar resultado, latência, custo e decisão sem persistir segredo ou dado excessivo.
- [ ] Garantir idempotência para retries de escrita quando a tool oferecer chave idempotente.

### Critérios de aceite

- [ ] `check_existing_ticket` roda como leitura e fundamenta a próxima decisão.
- [ ] `create_ticket` não é chamada antes de aprovação válida.
- [ ] Payload aprovado é o payload executado.
- [ ] Recusa encerra o caminho de escrita sem efeitos colaterais.
- [ ] Falha de auth/timeout não degrada para execução sem policy.

### Testes mínimos

- [ ] leitura, escrita aprovada e escrita recusada;
- [ ] payload adulterado após aprovação;
- [ ] papel ausente/expirado;
- [ ] retry não duplica ticket;
- [ ] isolamento de identidade entre tenants.

---

## F09 — Middleware: registro, compatibilidade e sombra

**Objetivo:** permitir reuso de middleware existente e declarar lacuna de novo middleware, mantendo
implementação separada do contrato.

**Dependências:** F04 e F06.

### TODO

- [ ] Definir contrato: `accepts`, `emits`, schemas, `stage`, `role`, `requires`, `never` e custo.
- [ ] Registrar pacote/endpoint por referência; nunca armazenar implementação no binding.
- [ ] Implementar verificador de compatibilidade determinístico.
- [ ] Exigir `pre-persist` + caminho único de escrita para `emits: block`.
- [ ] Exigir papel e revisão Owner para `emits: approval`.
- [ ] Criar lifecycle `quarantined → shadow → active → deprecated`.
- [ ] Em sombra, executar/avaliar sem bloquear, aprovar ou gravar.
- [ ] Definir métricas e período mínimo para promoção, sem promoção automática no MVP.
- [ ] Permitir scaffold de contrato quando não houver middleware compatível.
- [ ] Marcar scaffold como `implementation: missing` e bloquear binding ativo.
- [ ] Implementar o caso `duplicate-ticket-check` ou reutilizar capacidade oficial encontrada.

### Critérios de aceite

- [ ] O Builder reutiliza middleware compatível antes de sugerir criação.
- [ ] Middleware ausente vira trabalho de desenvolvimento explícito.
- [ ] Sombra nunca produz efeito externo.
- [ ] Middleware incompatível não pode ser anexado ao copiloto.
- [ ] Promoção exige evidência e gesto Owner.

### Testes mínimos

- [ ] compatibilidade de entrada/saída;
- [ ] block fora de `pre-persist` recusado;
- [ ] approval sem papel recusado;
- [ ] sombra sem efeito colateral;
- [ ] implementação ausente não ativa.

---

## F10 — Adapter/connection: referência, identidade e custo

**Objetivo:** modelar ligações externas sem reinventar connection management nem guardar segredos.

**Dependências:** F04 e F06.

### TODO

- [ ] Mapear adapter para connections/identidades oficiais encontradas em F00.
- [ ] Definir contrato: provider, capability, region, identity reference, billing, cap, onExceed.
- [ ] Proibir valor de segredo em documento, API, log e frontend.
- [ ] Validar residência/região e disponibilidade por tenant/área.
- [ ] Aplicar teto antes da chamada; definir `stop`, `degrade` ou `warn` conforme policy.
- [ ] Mostrar owner/rotação somente quando uma integração legada exigir segredo referenciado.
- [ ] Resolver dependências de middleware/MCP contra adapters disponíveis.
- [ ] Diferenciar “connection existe” de “usuário tem autorização para usá-la”.

### Critérios de aceite

- [ ] MCP de tickets usa uma referência de connection/identidade, nunca credencial copiada.
- [ ] Região/custo incompatível impede ativação.
- [ ] Teto é aplicado antes da execução.
- [ ] Builder recomenda adapter somente quando necessário e existente.

### Testes mínimos

- [ ] segredo inline recusado;
- [ ] connection inexistente ou cross-tenant recusada;
- [ ] estouro de teto respeita policy;
- [ ] usuário sem entitlement não usa connection válida.

---

## F11 — Operação do copiloto e catálogo de recursos

**Objetivo:** tornar copiloto um recurso operável: estado, versões, dependências, atividade, custo e
fim de vida.

**Dependências:** F09 e F10.

### TODO

- [ ] Criar catálogo derivado da fonte publicada, com filtros por área, lifecycle e runtime.
- [ ] Criar página do copiloto com versões, ChangeSets, dependências e health.
- [ ] Exibir runtime real (`foundry` ou `backend`) sem mascarar execução.
- [ ] Exibir recursos em sombra, incompatíveis, ausentes ou depreciados.
- [ ] Exibir custo por área e por componente sem contador paralelo.
- [ ] Exibir permissões efetivas e origem das policies.
- [ ] Implementar depreciação sem apagar versões citadas por evidência.
- [ ] Alertar quando mudança de MCP/middleware invalida uma versão ativa.

### Critérios de aceite

- [ ] Toda capacidade mostrada é derivada de recurso real/publicado.
- [ ] A tela não declara “ativo” quando dependência está em sombra ou ausente.
- [ ] Versão utilizada numa execução pode ser reconstruída.
- [ ] Depreciação não quebra evidência histórica.

---

## F12 — Evidência, cadeia e dossiê

**Objetivo:** implementar a camada avançada de prova sem misturá-la ao MVP de tickets.

**Dependências:** F08, F09 e F10.

### TODO

- [ ] Definir quais eventos entram na trilha e quais dados devem ser minimizados.
- [ ] Encadear eventos por hash com algoritmo e canonicalização definidos.
- [ ] Criar âncora diária write-once e política de retenção.
- [ ] Pesquisar e integrar serviço oficial de carimbo RFC 3161; não implementar TSA própria.
- [ ] Associar proposta, diff, aprovação, versão, execução e resultado.
- [ ] Implementar espécies de citação `blob`, `dispositivo` e `trecho` com resolução verificável.
- [ ] Implementar lacuna declarada com motivo, dispositivo e destino.
- [ ] Implementar assinatura com step-up no ato quando a policy exigir.
- [ ] Gerar dossiê exportável com lacunas e desvios explícitos.
- [ ] Validar tenancy hierárquica `rede → unidade` em ADR próprio antes de implementar.
- [ ] Definir rollup `worst-link` apenas após confirmar o modelo regulatório do produto.

### Critérios de aceite

- [ ] Alteração retroativa em evento é detectável.
- [ ] Âncora e carimbo podem ser verificados fora do sistema.
- [ ] O dossiê resolve documentos, versões e decisões citados.
- [ ] Lacuna não é convertida em conformidade positiva.
- [ ] Unidade assina somente se a arquitetura hierárquica tiver sido aprovada.

---

## 6. Backlog transversal

### Segurança e privacidade

- [x] Threat model do fluxo “descrição → catálogo → modelo → ChangeSet → publicação → execução”.
  - Fronteira Azure DevOps: token OBO existe somente durante o egress TLS e solicita o recurso
    `499b84ac-1321-427f-aa17-267ca6975798/.default`; a app registration concede apenas a permissão
    delegada `vso.code_write`. Token, headers e resposta externa bruta não entram em estado ou log.
  - Elevação/confusão de identidade: a rota exige App Role `Approver`, usa o access token validado
    do próprio request como `user_assertion` e revalida tenant, área, revisão e hash antes de cada
    operação. Não há fallback para PAT, app-only ou identidade do processo quando auth está ativa.
  - Tampering/replay: organização, projeto, repositório, refs, caminhos, conteúdo e limites são
    validados; branch e chave são derivadas da revisão aprovada; replay concluído retorna o mesmo PR.
  - Corrida/resultado ambíguo: push usa compare-and-swap por `oldObjectId`; conflito de ref, 4xx e
    decisão humana não recebem retry. Falha após escrita entra em `intervention_required`.
  - Disponibilidade: timeout de 30 s; retry com `Retry-After`/backoff somente em leituras idempotentes
    para transporte, 408, 429 e 5xx. Respostas persistidas são projeções mínimas de commit, PR e merge.
- [ ] Tratar descrição de tool/documento externo como dado não confiável contra prompt injection.
- [ ] SSRF e egress policy para MCP remoto e redirects.
- [ ] Least privilege para OBO/connections e separação Admin/Approver/Owner.
- [ ] Redação de logs, retenção e classificação de payloads de tickets.
- [ ] Idempotência e replay protection para aprovações e tools de escrita.
- [ ] Garantir que aprovação expirada ou de outro ChangeSet não possa ser reutilizada.

### Observabilidade e custo

- [ ] Trace correlacionando tenant, copiloto, versão, ChangeSet, tool e aprovação.
- [ ] Métricas de propostas aceitas/editadas/descartadas/parciais.
- [ ] Métricas de reuso vs criação de novos componentes.
- [ ] Métricas de sombra, promoção, incompatibilidade e falha de dependência.
- [ ] Custo atribuído por tenant/área/copiloto/componente.
- [ ] Alertas para teto, drift de catálogo e dependência degradada.

### Migração e compatibilidade

- [ ] Inventariar documentos atuais em `agents/assured/flows/` e `copilots/`.
- [ ] Criar migrador/versionador, não reescrever silenciosamente documentos existentes.
- [ ] Manter `propose_field` durante a transição.
- [ ] Definir como domínios fixos atuais aparecem no novo catálogo sem duplicação.
- [ ] Definir como AgentSchema publicado é referenciado por `agent-binding`.
- [ ] Testar rollback para versão anterior de schema e de copiloto.

### Produto e linguagem

- [ ] Padronizar termos: copiloto, agente, caso de uso, tool, middleware, adapter e binding.
- [ ] Explicar na UI “pronto”, “em sombra”, “contrato sem implementação” e “lacuna”.
- [ ] Evitar afirmar que o sistema “criou middleware” quando criou apenas contrato/scaffold.
- [ ] Tornar impacto e limitações legíveis para usuário não técnico.
- [ ] Validar o fluxo com um usuário de negócio e um desenvolvedor antes de ampliar domínios.

## 7. Fora do primeiro MVP

- [ ] Não gerar implementação arbitrária de middleware por IA e ativá-la automaticamente.
- [ ] Não criar/rotacionar credenciais ou connections por proposta do Builder.
- [ ] Não permitir que copiloto altere policy, RBAC ou configuração global do tenant.
- [ ] Não normalizar frameworks diferentes por abstração própria; usar o idioma de interrupção de
  cada runtime, conforme ADR-020.
- [ ] Não promover automaticamente componente após período em sombra.
- [ ] Não implementar tenancy hierárquica/regulatória dentro da fatia de tickets.
- [ ] Não implementar RFC 3161, TSA ou mecanismo criptográfico próprio.
- [ ] Não manter catálogo paralelo ao Foundry/registries publicados.

## 8. Ordem recomendada de entrega

### Release 1 — autoria segura de OKF

- [ ] F00: pesquisa oficial e ADR.
- [ ] F01: contrato OKF.
- [x] F02: ChangeSet multi-documento.
- [ ] F03: registry MCP.
- [ ] F04: catálogo e recomendação.
- [ ] F05: Builder autor.
- [ ] F06: revisão/publicação.
- [ ] Demo: gerar e publicar o copiloto de tickets, ainda sem executar tool externa.

### Release 2 — execução governada

- [ ] F08: cliente MCP e HITL de escrita.
- [ ] F09: middleware de duplicidade e sombra.
- [ ] F10: adapter/connection e custo.
- [ ] Demo: consultar ticket existente e criar somente após aprovação.

### Release 3 — operação e prova

- [ ] F07: UX completa do FormFlow/Builder.
- [ ] F11: catálogo operacional.
- [ ] F12: evidência avançada e dossiê.

## 9. Decisões fechadas na F00

Estas decisões bloqueiam fases específicas e não devem ser escondidas dentro da implementação:

- [x] **D01 — Fonte de verdade de agente:** AgentSchema; OKF usa `agent-binding`.
- [x] **D02 — Snapshot das tools MCP:** observação imutável para evidência; servidor continua fonte
  operacional e escrita redescobre para detectar drift.
- [x] **D03 — Classificação leitura/escrita:** combinação mais restritiva; metadata remota é apenas
  sinal, classificação administrativa autoriza e desconhecido falha fechado.
- [x] **D04 — Atomicidade do ChangeSet:** pré-validação integral e publicação compensável com
  journal; não simular transação distribuída.
- [x] **D05 — Granularidade de aprovação:** revisão por documento e aprovação final do conjunto;
  qualquer edição invalida a aprovação.
- [x] **D06 — Política organizacional:** projeção administrativa das fontes de enforcement
  oficiais, sem motor universal e fora do domínio de escrita dos copilotos.
- [x] **D07 — Middleware runtime:** implementação concreta no módulo dono, usando idioma nativo do
  runtime; `middleware-binding` referencia, não uniformiza.
- [x] **D08 — Tenancy hierárquica:** cenário exploratório da F12, fora do MVP.

## 10. Próxima ação

- [x] Executar **F00** e produzir a matriz de capacidades oficiais + ADR.
- [x] Iniciar **F01** pelo envelope e pelas referências de `agent-binding`, `mcp-binding` e
  `middleware-binding`, seguindo ADR-032.
- [ ] Reestimar F02–F10 durante F01 usando a lacuna medida, sem antecipar UI ou registry.
