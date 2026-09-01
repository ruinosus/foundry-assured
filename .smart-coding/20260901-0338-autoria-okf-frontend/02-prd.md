# PRD — Autoria OKF e evolução completa do frontend

> Arquivo: `.smart-coding/20260901-0338-autoria-okf-frontend/02-prd.md`
> Artefato gerado pela skill `sc-formalizar`.
> Próxima fase obrigatória: `sc-detalhar`.
> Baseado em: `.smart-coding/20260901-0338-autoria-okf-frontend/01-entendimento.md`

## Revisão 2026-09-01 — fundação visual independente

Removidos CURA, pacotes `@rededor/*` e qualquer identidade visual da Rede D'Or. O frontend redesenhado passa a usar o Assured UI, fundação própria baseada nos tokens e componentes React/CSS do produto, preservando os mesmos requisitos de paridade, acessibilidade e ativação controlada.

**Seções afetadas:** Problema, Solução, US-001, decisões de implementação, pendências e notas

## Problema

O produto já expõe agentes, casos de uso, conhecimento, skills, copilotos, auditoria e administração, mas essas capacidades aparecem em jornadas e padrões visuais diferentes. A pessoa que não opera diretamente o portal do Foundry ainda não dispõe de uma experiência única para descobrir recursos reais do seu contexto, compor documentos OKF, validar relações, revisar mudanças, obter aprovação, versionar em Git e materializar o resultado no Foundry.

Os protótipos descrevem essa plataforma de autoria, porém são referências conceituais com dados embutidos e não contratos executáveis. A implementação atual também possui partes relevantes da solução, como FormFlow, Builder, proposer, perfil estrito de autoria OKF, `OkfChangeSet`, projeções do Foundry e auditoria, mas não as reúne em uma jornada completa. Sem essa consolidação, há risco de criar catálogos paralelos, apresentar capacidades inexistentes, perder isolamento entre tenant e área ou deixar repositório e Foundry divergirem após uma falha parcial.

Além disso, o frontend atual precisa consolidar uma linguagem visual própria e consistente. A substituição integral escolhida exige preservar as capacidades de todas as rotas existentes, redesenhar as novas jornadas e provar equivalência funcional, responsividade e acessibilidade antes de ativar o novo conjunto.

## Solução

Entregar uma aplicação de gestão e autoria integralmente redesenhada no Assured UI, sem dependências ou identidade visual da Rede D'Or, com navegação, estados globais e conteúdo de todas as rotas atuais consistentes. A mesma aplicação oferecerá catálogo, detalhe de recurso, Builder, FormFlow, casos de uso, registries, bundles, Bundle Editor, conformidade e publicação ponta a ponta.

A autoria terá três rotas: agente declarativo no Foundry, workflow declarativo executável por um harness existente e agente com container próprio. Neste desafio, a aplicação cria, edita, valida, versiona e publica os contratos dessas rotas; interpretar ou executar um workflow declarado permanece fora do escopo.

Sem Azure provisionado, uma API local persistida em SQLite implementará o mesmo contrato consumido pela interface conectada. Ela permitirá operar as jornadas de gestão, executará validações determinísticas reais e mostrará como pendentes os checks que exigem Azure. Um indicador global no shell deixará claro quando a aplicação estiver nesse ambiente.

O ciclo de publicação será explícito e retomável: `Author` cria e submete; `Approver` revisa e autoriza; a aplicação abre branch e pull request no GitHub ou Azure DevOps usando a identidade delegada do usuário; após confirmar o merge, materializa as projeções oficiais no Foundry. Cada etapa terá estado persistido, idempotência, auditoria e compensação ou intervenção declarada quando não for possível restaurar automaticamente.

## User stories

### US-001 — Shell Assured UI unificado

Como **usuário autenticado**, eu quero **navegar por um shell integralmente construído com a linguagem visual própria do produto**, para **usar todas as áreas com padrões visuais, de interação e acessibilidade consistentes**.

**Critérios de aceite:**
- O shell carrega os tokens, estilos e componentes compartilhados do Assured UI antes de renderizar as rotas, sem dependências `@rededor/*`.
- Navegação, cabeçalhos, contexto de tenant e área, identidade, idioma, estados globais e feedback usam componentes e tokens próprios compartilhados quando houver equivalente.
- O shell mantém autenticação, internacionalização, temas suportados e integrações CopilotKit/AG-UI funcionais.
- Nenhum conteúdo, controle ou estado global se sobrepõe ou fica inacessível nos viewports de aceite.

### US-002 — Preservação das rotas existentes

Como **usuário atual do produto**, eu quero **encontrar no frontend redesenhado todas as capacidades que já utilizo**, para **não sofrer regressão funcional na substituição da interface**.

**Critérios de aceite:**
- Existe uma matriz versionada que relaciona cada rota atual, seus estados e ações com a superfície correspondente no frontend novo.
- Assistentes, chats por domínio, agentes, conhecimento, skills, avaliações, chamados, casos de uso, copilotos, auditoria, conexões e usuários preservam suas capacidades autorizadas.
- Redirecionamentos e links profundos existentes continuam levando a um destino válido ou possuem migração explícita.
- A substituição só é habilitada quando os gates comparativos de todas as rotas estiverem verdes.

### US-003 — Ambiente local inequívoco

Como **usuário sem ambiente Azure provisionado**, eu quero **operar a gestão contra uma API local durável**, para **criar e revisar conteúdo sem confundir dados locais com recursos materializados**.

**Critérios de aceite:**
- Um indicador global persistente identifica o uso do adapter local em todas as rotas.
- O estado local sobrevive a reinícios por meio de SQLite e permanece isolado pelo par tenant e área.
- A interface consome o mesmo contrato de API nos adapters local e conectado.
- Tokens, segredos e credenciais delegadas não são gravados no SQLite.

### US-004 — Catálogo factual de recursos

Como **Reader ou Author**, eu quero **consultar os recursos disponíveis no tenant e na área ativos com origem e estado claros**, para **reutilizar capacidades reais em vez de inventar referências**.

**Critérios de aceite:**
- O catálogo projeta agentes, knowledge bases, skills, toolboxes, connections permitidas, bindings, casos de uso, FormFlows e demais recursos a partir das fontes donas.
- Cada item distingue recurso disponível, compatível, dependente de configuração, em sombra, em quarentena ou ausente.
- A interface não mantém uma lista operacional paralela ao Foundry, Search ou servidor MCP.
- Um identificador inexistente aparece como lacuna e não pode ser usado como referência válida.

### US-005 — Detalhe e ciclo de vida do recurso

Como **Reader**, eu quero **consultar definição, versões, atividade, custo, permissões, dependências e estado de publicação de um recurso**, para **entender seu uso e impacto antes de alterá-lo**.

**Critérios de aceite:**
- A tela identifica a fonte de cada informação e diferencia dado medido, estimado, indisponível e pendente.
- Versões publicadas permanecem imutáveis e consultáveis; uma alteração cria nova revisão.
- Custo desconhecido não recebe valor plausível inventado.
- Ações exibidas e habilitadas refletem o papel do usuário e o escopo tenant e área.

### US-006 — Escolha da rota de autoria

Como **Author**, eu quero **iniciar um recurso por uma das três rotas de autoria**, para **representar corretamente seu modelo de execução sem precisar conhecer os detalhes do portal**.

**Critérios de aceite:**
- A aplicação oferece agente declarativo no Foundry, workflow declarativo executado por harness e agente com container próprio.
- Cada rota explica de forma operacional onde executa, o que pode declarar e quais capacidades adicionais exige.
- A escolha gera somente tipos e bindings admitidos pelo perfil de autoria OKF.
- Um workflow declarado pode ser criado e publicado como contrato, mas não é apresentado como executável por este desafio.

### US-007 — FormFlow declarativo

Como **Author**, eu quero **editar recursos por formulários derivados de documentos FormFlow**, para **usar uma interface orientada ao domínio sem editar YAML manualmente**.

**Critérios de aceite:**
- Campos, validações, regras, lacunas permitidas e ações assistidas são derivados do documento, não codificados por tipo de tela.
- Erros de schema, referência e autorização aparecem junto ao contexto editável e impedem submissão quando bloqueadores.
- Alterar o FormFlow válido altera a experiência sem exigir um componente exclusivo para cada recurso.
- O documento técnico permanece acessível para inspeção e revisão especializada.

### US-008 — Builder com proposta multi-documento

Como **Author**, eu quero **descrever uma necessidade e receber uma proposta de `OkfChangeSet` fundamentada no catálogo real**, para **compor vários documentos coerentes com menos trabalho manual**.

**Critérios de aceite:**
- A proposta pode criar ou revisar vários documentos e mostra dependências, procedência, justificativas e lacunas por operação.
- O Builder só referencia identificadores presentes no snapshot de catálogo usado na proposta.
- O Author pode aceitar, editar ou descartar cada documento antes de confirmar o conjunto.
- O Builder não publica, não provisiona, não cria policy e não inventa credenciais ou implementações ausentes.

### US-009 — Registries e bindings

Como **Admin**, eu quero **configurar registries e bindings para capacidades externas ou de runtime**, para **tornar referências disponíveis à autoria sem copiar código nem segredo para documentos OKF**.

**Critérios de aceite:**
- Bindings referenciam implementações, connections e versões concretas; não incorporam código ou credenciais.
- Recursos novos entram em estado não ativo compatível com sua classificação de risco até revisão.
- Drift, incompatibilidade ou ausência de implementação ficam visíveis e bloqueiam ativação indevida.
- Apenas o tenant e a área proprietários conseguem consultar ou alterar a configuração.

### US-010 — Bundle Editor e versionamento

Como **Author**, eu quero **editar e revisar um bundle como conjunto de documentos versionados**, para **manter relações consistentes e produzir uma mudança rastreável**.

**Critérios de aceite:**
- O editor apresenta árvore do bundle, documento em foco, validações, dependências e diferenças entre a base e a proposta.
- Referências internas ao mesmo `OkfChangeSet` resolvem antes da publicação; referências externas são conferidas na fonte dona.
- Conflito com uma revisão mais recente impede sobrescrita e exige rebase ou nova revisão.
- A versão submetida é imutável; novas mudanças geram outra revisão.

### US-011 — Conformidade honesta

Como **Author ou Approver**, eu quero **executar validações de conformidade e readiness com estados explícitos**, para **distinguir evidência comprovada de verificação ainda não executada**.

**Critérios de aceite:**
- Schema, referências, autorização declarada, invariantes e políticas determinísticas são avaliados localmente de verdade.
- Cada check possui estado `aprovado`, `reprovado` ou `pendente`, evidência e motivo observáveis.
- Checks dependentes de Azure ficam `pendente` no adapter local e nunca são simulados como aprovados.
- Um check bloqueador reprovado impede submissão ou publicação conforme a fase definida pelo contrato.

### US-012 — Revisão e separação de responsabilidades

Como **Approver**, eu quero **revisar o conjunto exato que será publicado e autorizar ou rejeitar com contexto**, para **impedir que uma proposta se transforme em escrita externa sem decisão humana válida**.

**Critérios de aceite:**
- A revisão mostra diff por documento, resumo do conjunto, dependências, impacto, fontes, lacunas, papel exigido e plano de compensação.
- `Author` pode criar e submeter, `Approver` pode autorizar ou rejeitar a publicação, `Admin` pode configurar registries e políticas e `Reader` apenas consultar.
- Qualquer edição posterior invalida a aprovação anterior.
- Usuário sem papel ou fora do tenant e área da proposta não consegue aprová-la.

### US-013 — Publicação em GitHub e Azure DevOps

Como **Approver**, eu quero **publicar a revisão aprovada como branch e pull request no provedor configurado**, para **submeter a mudança ao processo de versionamento e revisão do repositório**.

**Critérios de aceite:**
- GitHub e Azure DevOps são suportados por adapters que obedecem ao mesmo contrato de publicação.
- A operação usa identidade delegada do usuário conectado e solicita somente os escopos necessários.
- O conteúdo do pull request corresponde byte a byte ou por canonicalização declarada ao conjunto aprovado.
- Repetir a requisição com a mesma chave de idempotência não cria outra branch nem outro pull request.
- Falhas de autenticação, autorização, conflito, limite de uso e indisponibilidade geram estados e mensagens explícitos sem expor detalhes sensíveis.

### US-014 — Materialização pós-merge no Foundry

Como **Approver**, eu quero **materializar no Foundry somente uma revisão cujo pull request foi integrado**, para **manter o repositório como fonte versionada anterior ao recurso operacional**.

**Critérios de aceite:**
- O provisionamento permanece bloqueado enquanto o merge não estiver confirmado pelo provedor.
- Cada tipo autorável é projetado pela capacidade oficial correspondente; AgentSchema continua sendo a fonte de verdade do agente.
- A revisão no repositório e o recurso materializado possuem vínculo de identidade e versão verificável.
- Repetir a materialização não cria versões ou recursos duplicados.
- A aplicação não declara sucesso integral enquanto alguma operação obrigatória estiver incompleta.

### US-015 — Retomada, compensação e reconciliação

Como **operador da plataforma**, eu quero **retomar e reconciliar publicações interrompidas**, para **corrigir falhas parciais sem perder evidência nem repetir efeitos externos**.

**Critérios de aceite:**
- A publicação mantém journal por operação com estado, tentativa, idempotência, resultado e compensação prevista.
- Uma retomada continua da primeira operação elegível e não repete as concluídas.
- Quando a API oficial permitir, a compensação remove a versão recém-criada ou restaura a referência anterior.
- Quando a restauração automática não for possível, o fluxo termina em estado de intervenção explícito e auditável.

### US-016 — Isolamento por tenant e área

Como **responsável por uma área**, eu quero **que meus recursos, rascunhos, versões, registries e publicações permaneçam no meu contexto**, para **não expor nem alterar dados de outra área ou tenant**.

**Critérios de aceite:**
- O par tenant e área vem do contexto autenticado e não é aceito como autoridade apenas por parâmetro enviado pelo cliente.
- Chaves, consultas, autorização, cache, journal, auditoria e adapters externos aplicam o mesmo escopo.
- Tentativas de leitura, aprovação, alteração ou retomada fora do contexto falham fechadas.
- Referências de connection ou credencial de outro contexto não são resolvidas.

### US-017 — Auditoria e proteção de dados

Como **auditor ou operador autorizado**, eu quero **consultar uma trilha correlacionada de autoria e publicação**, para **reconstruir decisões e falhas sem expor segredo ou conteúdo pessoal desnecessário**.

**Critérios de aceite:**
- A trilha correlaciona autor, editor, aprovador, revisão, pull request, merge, materialização, compensações e identificadores externos.
- Eventos registram tenant, área, operação e request/correlation id no ponto estrutural de escrita.
- Tokens, segredos, payloads sensíveis e detalhes internos de erro não aparecem em logs, auditoria, fixtures ou documentos OKF.
- Mensagens ao usuário são claras; logs internos preservam contexto técnico autorizado para investigação.

### US-018 — Paridade responsiva e acessível

Como **usuário em desktop ou dispositivo móvel**, eu quero **concluir todas as jornadas de consulta, autoria, revisão e publicação**, para **não depender de um viewport específico**.

**Critérios de aceite:**
- Tabelas, canvas, editores, diffs e painéis laterais possuem composição responsiva que preserva todas as ações.
- Fluxos são operáveis por teclado, mantêm foco perceptível e fornecem nome e estado acessíveis aos controles.
- Texto, feedback, menus, dialogs e conteúdo dinâmico não se sobrepõem nem redimensionam a estrutura de forma incoerente.
- Screenshots e testes de interação cobrem viewports desktop e mobile definidos no detalhamento.

## Decisões de implementação

1. **Classificação de impacto:** a mudança é `estrutural`, pois altera contratos, persistência, versionamento, autenticação delegada, múltiplas integrações e todas as superfícies do frontend. Exige validação de tech lead ou arquiteto, testes de integração e ADR antes de `sc-fatiar`.
2. **Arquitetura de produto:** o frontend novo será ativado como substituição única após equivalência comprovada, mas o plano de implementação deve permitir desenvolver e validar slices independentes sem desativar o frontend atual.
3. **Fundação Assured UI:** os tokens e componentes React/CSS próprios existentes serão consolidados numa fundação compartilhada, sem dependências `@rededor/*`, fontes institucionais externas ou custom elements. Inicialização, estilos, assets, eventos e integração com Next.js não serão repetidos por rota.
4. **Preservação funcional:** a matriz de rotas e estados será um contrato verificável da migração. O redesign pode reorganizar informação, mas não remover capacidade existente sem decisão explícita de produto.
5. **Contratos antes das telas:** catálogo, detalhe, versões, atividade, custo, permissões, conformidade e publicação terão contratos canônicos independentes do adapter. A UI não deduzirá estados por texto ou por presença acidental de campos.
6. **Adapter local:** SQLite será uma implementação backend do mesmo contrato da API conectada. Regras de produto ficarão nos módulos donos e serão compartilhadas; o adapter não ganhará semântica exclusiva.
7. **Módulos profundos existentes:** `okf` permanece dono do perfil de autoria e `OkfChangeSet`; `formflow` permanece dono dos formulários declarativos; `builder` e `proposer` permanecem separados de publicação; `foundry` permanece a projeção fina das APIs oficiais; `tenancy`, `audit`, `pricing`, `admin` e `usecases` continuam donos de seus conceitos.
8. **Orquestração de publicação:** o detalhamento definirá um módulo profundo com interface pequena para submissão, acompanhamento, retomada e reconciliação. Ele dependerá de contratos dos adapters Git e das projeções oficiais, sem permitir que proposer ou Builder escrevam externamente.
9. **Git providers:** GitHub e Azure DevOps implementarão o mesmo contrato de branch, pull request e consulta de merge, mantendo erros e capacidades específicos traduzidos para estados de domínio comuns somente onde forem semanticamente equivalentes.
10. **Identidade e autorização:** operações Git usarão identidade delegada do usuário. O contexto de tenant e área será resolvido no servidor; App Roles continuarão sendo a fonte dos papéis, com a matriz confirmada no entendimento.
11. **Publicação compensável:** a aplicação não simulará transação distribuída. Pré-validação, journal, idempotência, compensação e estado de intervenção seguirão a saga definida pela ADR-032.
12. **Fontes de verdade:** AgentSchema continua sendo a fonte única de agente; Foundry, Search e MCP continuam catálogos operacionais; OKF representa intenção, composição, bindings, revisão e procedência.
13. **Conformidade:** `policy` será uma visão composta das fontes de enforcement, não um motor universal. Checks determinísticos e checks dependentes de serviço terão estados distintos e evidência explícita.
14. **Conflitos arquiteturais:** o `sc-detalhar` deverá revisar a ADR-032 antes do fatiamento. A decisão D08, que deixa áreas fora do MVP, conflita com o isolamento por tenant e área confirmado neste desafio; o papel de publicação `Admin` do plano anterior conflita com o `Approver` confirmado aqui.
15. **ADR obrigatória:** antes de `sc-fatiar`, o detalhamento deverá produzir a decisão arquitetural aceita que cubra a estratégia de substituição integral, o contrato de coexistência até a ativação, o isolamento por área e a atualização da governança de publicação. Pode revisar/superseder a ADR-032 e/ou criar ADR complementar, sem manter decisões contraditórias.
16. **Erros e observabilidade:** integrações mapearão falhas conhecidas para erros de domínio e HTTP apropriados, com mensagens sem detalhe sensível e logs `error` correlacionados. Retry somente ocorrerá quando seguro e idempotente.
17. **MÁXIMA MAIOR:** chamadas a Foundry, Agent Framework, Entra e serviços Microsoft só serão definidas depois de verificar Learn, samples e fonte dos pacotes instalados. A aplicação expõe e orquestra capacidades oficiais; não as reimplementa.

## Decisões de teste

1. Testes devem observar contratos e comportamento externo; estrutura interna de componentes, chamadas privadas e detalhes de ORM não são critério de aceite.
2. A lógica crítica de autorização, isolamento, validação, publicação, idempotência, compensação e reconciliação terá cobertura mínima de 80%, sem usar o número como substituto de cenários comportamentais.
3. A mesma suíte contratual será executada contra o adapter SQLite e os adapters conectados substituíveis. Fixtures não poderão exigir segredo nem conter token real.
4. O perfil OKF e `OkfChangeSet` terão testes de round-trip, referência, conflito de revisão, autorização negativa, lacuna declarada e imutabilidade de versão.
5. A orquestração de publicação terá testes de máquina de estados para sucesso, retry, conflito, rejeição, merge ausente, falha parcial, compensação completa e intervenção manual.
6. GitHub e Azure DevOps terão testes contratuais offline com respostas representativas e um smoke autenticado por provedor quando o ambiente estiver disponível. O smoke prova branch, pull request, consulta de merge e idempotência sem ser requisito de todo CI offline.
7. Foundry terá testes offline nas projeções e smoke autenticado para cada tipo realmente materializado. Nenhuma assinatura de SDK será mockada antes de ser verificada na versão instalada.
8. Isolamento terá testes negativos entre tenant A/área A, tenant A/área B e tenant B, incluindo leitura, referência, aprovação, publicação, retomada, cache e auditoria.
9. Papéis terão matriz de testes para `Reader`, `Author`, `Approver` e `Admin`, cobrindo ausência de papel, papel expirado quando aplicável e tentativa fora do contexto.
10. Conformidade terá testes que provem execução real dos checks determinísticos e estado `pendente` dos checks externos no modo local; pendência nunca poderá ser convertida em aprovação por fallback.
11. O frontend terá testes de componente e integração para estados vazio, carregando, erro, parcial, conflito, sem permissão, pendente, compensação e sucesso, além dos verificadores estáticos já existentes.
12. A matriz de preservação terá um gate por rota e fluxo crítico. Redirecionamentos, links profundos, internacionalização, autenticação, CopilotKit/AG-UI e troca de tema serão cobertos.
13. Playwright validará jornadas ponta a ponta, screenshots e interação em desktop e mobile, incluindo teclado, foco, dialogs, tabelas, canvas, editores e ausência de sobreposição.
14. O build, typecheck, lint, verificadores frontend, gates backend e import-linter existentes permanecerão verdes. A suíte completa derivada do CI será executada antes da substituição.
15. Como mudança estrutural e crítica, o fechamento exigirá teste de integração, evidência e2e e triagem de findings novos de segurança antes do merge.

## Fora do escopo

- Interpretar ou executar no runtime o workflow declarado produzido pela interface.
- Criar um runtime, middleware universal, motor universal de policy ou catálogo operacional paralelo ao Foundry, Search ou MCP.
- Reproduzir literalmente os protótipos HTML/JSX ou promover todos os controles neles presentes a requisito.
- Armazenar token, segredo ou credencial de GitHub, Azure DevOps, Entra ou Foundry em SQLite, documento OKF, fixture, log ou trilha de auditoria.
- Declarar check Azure aprovado sem executá-lo.
- Materializar recurso antes de o pull request correspondente estar integrado.
- Prometer atomicidade distribuída entre Git, Foundry, Search e storage.
- Remover ou substituir uma capacidade existente sem decisão explícita registrada na matriz de migração.

## Pendências herdadas

- [ ] Definir os contratos canônicos dos documentos OKF e dos recursos de catálogo, versões, custos, atividade e conformidade — impacto: crítico · bloqueia `sc-fatiar`? sim
- [ ] Confirmar nas APIs oficiais o fluxo exato de identidade delegada e criação de branch/pull request para GitHub e Azure DevOps — impacto: crítico · bloqueia `sc-fatiar`? sim
- [ ] Confirmar nas APIs e SDKs oficiais quais tipos podem ser materializados pela aplicação no Foundry e qual metadado liga a revisão Git ao recurso — impacto: crítico · bloqueia `sc-fatiar`? sim
- [ ] Definir a máquina de estados, chaves de idempotência e estratégia de reconciliação da publicação — impacto: crítico · bloqueia `sc-fatiar`? sim
- [ ] Definir a matriz completa de rotas, capacidades preservadas e gates comparativos para a troca única — impacto: crítico · bloqueia `sc-fatiar`? sim
- [ ] Definir a convivência técnica do frontend novo com o atual até a substituição — impacto: crítico · bloqueia `sc-fatiar`? sim
- [ ] Definir padrões responsivos do Assured UI para canvas, tabelas densas e editores — impacto: médio · bloqueia `sc-fatiar`? sim
- [ ] Definir retenção, minimização e auditoria dos dados pessoais e executar o threat modeling aplicável do NORDOR-122 — impacto: crítico · bloqueia `sc-fatiar`? sim
- [ ] Resolver no registro arquitetural o conflito entre isolamento por área e a D08 da ADR-032 proposta — impacto: crítico · bloqueia `sc-fatiar`? sim
- [ ] Resolver no registro arquitetural o conflito entre `Approver` como autorizador da publicação e `Admin` como publicador no plano anterior — impacto: crítico · bloqueia `sc-fatiar`? sim

## Notas adicionais

- O levantamento atual encontrou 21 arquivos de rota/layout no App Router, incluindo redirecionamentos, e 23 módulos públicos no backend. A matriz definitiva deve ser gerada no detalhamento, pois quantidade de arquivos não equivale a quantidade de jornadas.
- A ADR-032 e o plano anterior já registram pesquisa de capacidades oficiais e implementações concluídas do perfil de autoria e `OkfChangeSet`. O detalhamento deve partir desse estado real e não reabrir decisões já comprovadas, exceto onde o entendimento mais recente criou conflito explícito.
- Os protótipos organizam a visão em entender, criar, registrar, operar e provar. Essa estrutura pode orientar a arquitetura de informação, mas acessibilidade, identidade própria e ergonomia das tarefas densas governam a composição final.
- O frontend já possui tokens e componentes próprios que serão consolidados, não substituídos por pacotes ou identidade visual da Rede D'Or.

---

## Histórico

Log cronológico de revisões deste PRD (mais antigo primeiro). Mantido por `sc-revisar`.

- 2026-09-01 — patch — removida dependência e identidade visual da Rede D'Or; adotado Assured UI próprio