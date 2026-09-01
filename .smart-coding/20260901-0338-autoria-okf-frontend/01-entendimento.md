---
workflow: critico
branch: feat/wizard-decisao-com-contexto
---

# Entendimento — Autoria OKF e evolução completa do frontend

> Arquivo: `.smart-coding/20260901-0338-autoria-okf-frontend/01-entendimento.md`
> Artefato gerado pela skill `sc-entender`.
> Input para a próxima fase: `sc-formalizar`.

## Escopo

- Tipo: `app`
- Skipped: `false`

## Workflow

`critico` — escolha confirmada pelo desenvolvedor devido à substituição integral do frontend, ao provisionamento de recursos no Foundry e às escritas externas autenticadas no GitHub e Azure DevOps, com impacto em autorização, isolamento multi-tenant, auditoria e recuperação de falhas.

## Objetivo

Permitir que perfis não especialistas criem, revisem, versionem, publiquem e acompanhem recursos OKF em uma experiência coerente e completa, sem depender do portal do Foundry para operar o ciclo de autoria. Ao mesmo tempo, elevar todo o frontend existente a uma fundação visual própria do produto e preservar suas capacidades atuais.

## Contexto e motivação

Os protótipos em `Análise de wizard AG-UI/` descrevem uma experiência de produto mais ampla e detalhada do que a disponível hoje, com jornadas de catálogo, autoria, registries, bundles, conformidade e publicação. A validação Azure do desafio de descoberta de bindings está parcialmente bloqueada por infraestrutura ainda não provisionada, mas a maior parte desta evolução pode avançar por contratos e por um adapter local durável.

O trabalho ocorrerá na branch existente `feat/wizard-decisao-com-contexto`, sem criar ou trocar de branch. Os protótipos são referência conceitual: suas capacidades orientam o produto, mas a arquitetura de informação e os componentes serão redesenhados como Assured UI, sem obrigação de reproduzir cada controle visual.

## Usuários e atores

- `Reader`: consulta catálogos, recursos, versões, atividade, custos, conformidade e auditoria aos quais tenha acesso.
- `Author`: cria e edita recursos, executa validações determinísticas e submete uma versão para revisão.
- `Approver`: revisa a proposta e autoriza a publicação, incluindo a abertura de pull request.
- `Admin`: configura registries, políticas e demais parâmetros administrativos do tenant e da área.
- Usuário conectado: fornece a identidade delegada usada nas operações com GitHub e Azure DevOps.
- Equipes de plataforma, segurança e produto: validam integrações, controles de acesso, conformidade e fidelidade das jornadas existentes.

## Dentro do escopo

- Consolidar a fundação Assured UI sobre os tokens e componentes próprios da aplicação, sem dependência ou identidade visual da Rede D'Or.
- Redesenhar no Assured UI o shell e o conteúdo de todas as rotas existentes, preservando suas capacidades.
- Substituir o frontend atual de uma única vez, somente após o conjunto redesenhado passar pelos gates comparativos.
- Entregar as capacidades conceituais dos protótipos: catálogo, detalhe de recurso, Builder, FormFlow, casos de uso, registries, bundles, Bundle Editor, conformidade e jornada ponta a ponta.
- Suportar três rotas de autoria: prompt agent no Foundry, workflow declarativo executado por harness e agente com container próprio.
- Criar, validar, versionar e publicar os contratos dessas três rotas.
- Disponibilizar um adapter backend local, compatível com os contratos da API e persistido em SQLite.
- Permitir uso local das jornadas de gestão e identificar esse ambiente por um indicador global persistente no shell.
- Executar localmente validações determinísticas reais de schema, referências, políticas e readiness.
- Mostrar como pendentes as verificações de conformidade que dependam de Azure; nunca simulá-las como aprovadas.
- Exibir versões, atividade, custos, permissões e ciclo de vida por meio de contratos explícitos.
- Isolar recursos, rascunhos, versões, registries, atividade, auditoria e referências de credencial pelo par tenant e área ativa.
- Abrir branches e pull requests reais no GitHub e no Azure DevOps com identidade delegada do usuário conectado.
- Exigir o fluxo `Author` cria e submete, `Approver` autoriza publicação e `Admin` configura registries e políticas.
- Após o merge confirmado do pull request, provisionar pela UI o recurso correspondente no Foundry.
- Tornar retomáveis e idempotentes as etapas de aprovação, criação de branch, abertura de pull request, detecção de merge e provisionamento, sem duplicar artefatos ou recursos.
- Garantir paridade funcional responsiva em desktop e mobile, inclusive para tabelas, canvas e editores.
- Cobrir adapters e contratos com testes offline e exigir smoke autenticado de GitHub, Azure DevOps e Foundry quando o ambiente de integração estiver disponível.

## Fora do escopo

- Interpretar ou executar no runtime o workflow declarado criado pela interface.
- Tratar os protótipos HTML/JSX como especificação visual literal ou reproduzir todos os seus controles sem validação de produto e acessibilidade.
- Marcar como aprovada qualquer verificação dependente de Azure quando o ambiente estiver desconectado.
- Substituir capacidades oficiais de Foundry, GitHub ou Azure DevOps por implementações próprias; a aplicação deve atuar como camada de acesso e orquestração.
- Armazenar tokens, segredos ou credenciais dos provedores no SQLite ou nos documentos OKF.
- Concluir o aceite das integrações externas somente com fixtures; os smokes reais continuam necessários quando o ambiente estiver disponível.

## Dados envolvidos

- Documentos OKF de agentes, workflows, casos de uso, registries e bundles, lidos e escritos pela interface e pela API.
- Rascunhos, versões, estados de revisão, resultados de validação, atividade, custos, permissões e estado do ciclo de publicação.
- Configuração tenant-local de registries e políticas, sempre isolada pelo par tenant e área.
- Metadados de branches, pull requests, revisões e merges recebidos de GitHub e Azure DevOps.
- Identificadores e estados de recursos provisionados no Foundry.
- Referências de credenciais e conexões; segredos e tokens não devem ser persistidos pela aplicação.
- No modo local, os dados de gestão serão persistidos em SQLite por um adapter backend compatível com a API.
- Há dados pessoais de identidade e autoria, como nome, identificador do usuário e histórico de ações. Não foram identificados dados clínicos ou financeiros neste entendimento; custos são métricas operacionais do produto.

## Integrações

- Assured UI, fundação visual interna baseada em React, CSS e tokens próprios do produto.
- GitHub, para criação de branch e pull request com identidade delegada.
- Azure DevOps Repos, para criação de branch e pull request com identidade delegada.
- Microsoft Foundry, para provisionamento do recurso somente após merge confirmado.
- Microsoft Entra ID e os mecanismos existentes de autenticação, identidade delegada e App Roles.
- Backend local com SQLite para o modo sem provisionamento Azure.

## Restrições conhecidas

- Frontend obrigatório em Next.js 16 e React 19, sem pacotes ou identidade visual da Rede D'Or; integrações de chat existentes usam CopilotKit/AG-UI e devem continuar funcionando.
- Backend obrigatório em Python 3.12 e na arquitetura modular existente, respeitando fronteiras `public.py`/`internal/` e os gates de importação.
- APIs e SDKs de Microsoft Foundry devem ser verificados nas fontes oficiais e nos pacotes instalados antes da implementação; não inventar assinaturas.
- O adapter local deve implementar os mesmos contratos consumidos pela UI conectada para evitar uma segunda interface de produto.
- O modo local deve ser inequívoco no shell, mas não deve poluir cada tela com marcações repetidas de simulação.
- A troca do frontend será única, não incremental; o frontend atual deve permanecer funcional até o novo conjunto estar completo e validado.
- A publicação só pode seguir a ordem aprovação → pull request → merge confirmado → provisionamento no Foundry.
- Toda escrita externa deve respeitar papel, consentimento delegado, idempotência e auditoria.
- Nenhum segredo pode ser colocado em documento OKF, banco local, fixture ou código-fonte.
- O trabalho deve permanecer na branch `feat/wizard-decisao-com-contexto`.

## Riscos identificados

| Risco | Impacto | Mitigação |
|---|---|---|
| Troca única de todas as rotas do frontend | Regressões podem permanecer ocultas até perto da substituição | Definir inventário e gates comparativos por rota, com validação responsiva e de acessibilidade antes da troca |
| Escopo reúne redesign, autoria, persistência e três integrações externas | A entrega pode ficar longa e difícil de revisar | Fatiar tecnicamente no plano, mesmo mantendo uma única ativação final, com contratos e critérios de aceite independentes |
| PR criado, mas merge ou provisionamento falha | Repositório e Foundry podem divergir | Modelar máquina de estados persistida, idempotência, retomada e reconciliação explícita |
| Uso de identidade delegada em dois provedores Git | Consentimentos ou escopos insuficientes podem bloquear publicação | Verificar capacidades oficiais, aplicar menor privilégio, tratar reautorização e cobrir cada provedor com smoke real |
| Isolamento incorreto por tenant e área | Vazamento de configuração, documentos ou histórico entre contextos | Aplicar escopo em chaves, consultas, autorização e testes negativos desde o contrato de persistência |
| SQLite local se afastar dos contratos conectados | A UI funciona localmente, mas falha ao usar serviços reais | Executar a mesma suíte contratual contra todos os adapters e evitar regras de produto exclusivas do adapter local |
| Verificações Azure indisponíveis no modo local | Usuário pode interpretar readiness parcial como aprovação total | Representar estados `aprovado`, `reprovado` e `pendente`, com pendência explícita para checks não executados |
| Provisionamento pela UI reimplementar capacidade do Foundry | Aumenta manutenção e viola a MÁXIMA MAIOR | Usar serviços e SDKs oficiais apenas como cola e validar previamente as superfícies disponíveis |
| Dados pessoais de identidade, autorização e auditoria em integrações externas | Exposição ou uso indevido da identidade do usuário | Aplicar minimização, retenção, autorização e trilha de auditoria; pode acionar threat modeling do NORDOR-122 — confirmar em `sc-detalhar` |
| Paridade mobile para editores e canvas densos | Fluxos podem ficar impraticáveis ou inacessíveis em telas pequenas | Definir padrões responsivos do Assured UI e testes por viewport para cada jornada de autoria |

## Decisões resolvidas

1. **Estratégia visual**: migrar o shell inteiro e todas as rotas existentes para o Assured UI próprio do produto.
   - **Alternativas consideradas**: adotar um design system institucional externo; migrar somente superfícies compartilhadas.
   - **Porquê**: o desenvolvedor quer uma evolução visual e funcional integral, sem manter partes do frontend no padrão anterior.
2. **Ativação do novo frontend**: substituir o frontend atual de uma única vez quando o conjunto estiver completo.
   - **Alternativas consideradas**: ativação incremental por shell, rota ou jornada.
   - **Porquê**: escolha explícita do desenvolvedor; exige gates comparativos antes da troca.
3. **Modo sem Azure**: usar adapter backend local compatível com a API e persistido em SQLite.
   - **Alternativas consideradas**: navegação demonstrativa, IndexedDB e arquivos no workspace.
   - **Porquê**: permite jornadas operáveis e histórico durável sem acoplar a UI a uma implementação descartável.
4. **Identificação do modo local**: mostrar um indicador global persistente no shell.
   - **Alternativas consideradas**: marcar cada dado simulado ou não distinguir visualmente o ambiente.
   - **Porquê**: comunica a origem dos dados sem degradar a leitura de cada tela.
5. **Amplitude funcional**: incluir todas as capacidades conceituais dos protótipos, inclusive conformidade.
   - **Alternativas consideradas**: limitar o ciclo a copilotos ou excluir conformidade.
   - **Porquê**: o objetivo é entregar a experiência completa de autoria e gestão.
6. **Fidelidade aos protótipos**: tratá-los como referência conceitual, não como especificação visual literal.
   - **Alternativas consideradas**: transformar cada controle em requisito ou preservar apenas uma referência visual.
   - **Porquê**: permite redesenhar a experiência conforme a identidade e as necessidades reais do produto.
7. **Três rotas de autoria**: cobrir prompt agent, workflow declarado e agente com container próprio.
   - **Alternativas consideradas**: nenhuma exclusão entre as três rotas apresentadas.
   - **Porquê**: são os três modelos de criação necessários para representar recursos com diferentes runtimes.
8. **Limite do workflow declarado**: entregar autoria, validação, versionamento e publicação, sem execução runtime.
   - **Alternativas consideradas**: executar localmente ou também executar conectado ao Foundry.
   - **Porquê**: separa o contrato de autoria da evolução do harness executor.
9. **Conformidade offline**: executar regras determinísticas reais e deixar checks Azure como pendentes.
   - **Alternativas consideradas**: simular aprovação completa ou bloquear toda a análise sem Azure.
   - **Porquê**: produz evidência útil localmente sem afirmar verificações que não ocorreram.
10. **Política de papéis**: `Author` cria e submete, `Approver` autoriza publicação, `Admin` configura e `Reader` consulta.
    - **Alternativas consideradas**: permitir publicação pelo Author ou restringi-la ao Admin.
    - **Porquê**: mantém separação de responsabilidades entre autoria, aprovação e administração.
11. **Provedores Git**: suportar GitHub e Azure DevOps desde a primeira versão.
    - **Alternativas consideradas**: implementar somente um dos provedores.
    - **Porquê**: ambos são necessários para a jornada de publicação definida pelo desenvolvedor.
12. **Identidade de publicação**: usar a identidade delegada do usuário conectado.
    - **Alternativas consideradas**: identidade de serviço ou estratégia configurável por registry.
    - **Porquê**: branches e pull requests devem refletir a autoria do usuário quando o provedor permitir.
13. **Publicação e provisionamento**: abrir PR real e provisionar o recurso pela UI somente após merge confirmado.
    - **Alternativas consideradas**: apenas salvar versão, apenas gerar proposta, acionar pipeline existente, provisionar antes ou em paralelo ao PR.
    - **Porquê**: o repositório permanece fonte versionada anterior à materialização do recurso no Foundry.
14. **Isolamento**: vincular todo o estado de autoria e gestão ao par tenant e área ativa.
    - **Alternativas consideradas**: isolamento somente por tenant ou catálogo global com autoria tenant-local.
    - **Porquê**: áreas não devem compartilhar dados, credenciais ou histórico implicitamente.
15. **Responsividade**: exigir paridade funcional entre desktop e mobile.
    - **Alternativas consideradas**: mobile somente para consulta ou aceite apenas em desktop.
    - **Porquê**: todas as jornadas devem permanecer operáveis independentemente do viewport.
16. **Validação das integrações**: combinar testes contratuais offline com smoke real autenticado por provedor e Foundry.
    - **Alternativas consideradas**: somente testes offline ou E2E real obrigatório em todo CI.
    - **Porquê**: mantém o CI determinístico sem dispensar prova real das integrações.

## Decisões pendentes

- [ ] Definir no `sc-detalhar` os contratos canônicos dos documentos OKF e dos recursos de catálogo, versões, custos, atividade e conformidade.
- [ ] Confirmar nas APIs e SDKs oficiais o fluxo exato de identidade delegada e criação de branch/PR para GitHub e Azure DevOps.
- [ ] Confirmar nas APIs e SDKs oficiais quais tipos de recurso podem ser provisionados diretamente pela aplicação no Foundry e qual metadado liga a versão no repositório ao recurso materializado.
- [ ] Definir a máquina de estados, as chaves de idempotência e a estratégia de reconciliação do fluxo de publicação.
- [ ] Definir a matriz completa de rotas existentes, capacidades que devem ser preservadas e gates comparativos para a troca única.
- [ ] Definir a estratégia técnica de convivência do frontend novo com o atual até o momento da substituição.
- [ ] Definir a arquitetura responsiva do Assured UI para canvas, tabelas densas e editores.
- [ ] Definir retenção, minimização e auditoria dos dados pessoais e confirmar o threat modeling do NORDOR-122.

## Próximo passo sugerido

Rodar `sc-formalizar` para transformar este entendimento em PRD. Como o workflow é crítico e há integrações externas, identidade delegada e isolamento multi-tenant, depois do PRD será obrigatório executar `sc-detalhar` antes de fatiar a implementação.

---

## Histórico

Log cronológico de revisões deste artefato (mais antigo primeiro). Mantido por `sc-revisar`.

- 2026-09-01 — patch — removida dependência e identidade visual da Rede D'Or; adotado Assured UI próprio