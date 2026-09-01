# PRD — Binding MCP, Toolbox e snapshot de descoberta

> Arquivo: `.smart-coding/20260831-1229-mcp-binding-discovery/02-prd.md`
> Artefato gerado pela skill `sc-formalizar` (Rede Dor Smart Coding).
> Próxima fase obrigatória: `sc-detalhar`.
> Baseado em: `.smart-coding/20260831-1229-mcp-binding-discovery/01-entendimento.md`

## Problema

O Builder já consegue propor ChangeSets OKF coerentes, mas um `mcp-binding` ainda não prova que o Toolbox, servidor e tools referenciados existem no tenant nem que seus schemas e permissões continuam iguais aos revisados. Sem essa ligação, o usuário pode revisar uma composição baseada em nomes inventados, metadata remota maliciosa ou contrato desatualizado.

Uma URL MCP direta também cria uma nova fronteira de confiança. Fazer `tools/list` sem aprovação e política de egress pode causar SSRF; confiar em annotations do servidor pode liberar escrita; guardar payload remoto sem saneamento pode persistir segredo ou dado pessoal; resolver connection fora do tenant pode vazar capacidade entre clientes.

## Solução

O Builder passa a consumir uma projeção tenant-safe dos Toolboxes, connections e servidores MCP reais. Um `mcp-binding` referencia um Toolbox oficial por versão/default version ou, quando não houver Toolbox aplicável, registra uma URL proposta que permanece sem acesso à rede até validação de egress e aprovação Admin.

A descoberta usa o protocolo oficial MCP `tools/list` e nunca executa tools. Cada observação gera um snapshot de descoberta com resposta sanitizada, limitada e criptografada na evidence layer, além de uma projeção normalizada para revisão e diff. A classificação efetiva combina decisão administrativa, sinais remotos, papel/policy e aprovação nativa pelo resultado mais restritivo.

Antes de promoção e de chamada de escrita, o sistema compara a descoberta atual com o snapshot revisado. Tool nova, não classificada ou com schema/permissão alterado fica indisponível ou em quarentena até nova revisão Admin. As demais tools do binding permanecem utilizáveis quando não sofreram drift.

## User stories

### US-001 — Selecionar Toolbox oficial

Como **Builder**, eu quero **selecionar um Toolbox existente no projeto Foundry do tenant, com versão fixa ou default version**, para **compor um binding sem copiar o catálogo operacional**.

**Critérios de aceite:**
- A projeção lista somente Toolboxes visíveis no projeto Foundry do tenant atual.
- Cada item informa identidade oficial, default version e versões disponíveis conforme a API oficial.
- Um nome ou versão inexistente é recusado antes da revisão do ChangeSet.
- O backend não mantém lista paralela de Toolboxes.

### US-002 — Propor servidor MCP direto

Como **Builder**, eu quero **propor uma URL MCP direta quando não houver Toolbox aplicável**, para **representar integrações que ainda não possuem Toolbox no Foundry**.

**Critérios de aceite:**
- A proposta nasce em estado não executável e não dispara requisição de rede.
- Somente Admin pode aprovar o endpoint para a primeira descoberta.
- Esquema, host, DNS, IP de destino e redirects são avaliados pela política de egress antes de cada conexão.
- Destino privado, loopback, link-local, metadata ou redirect para esses destinos é recusado.

### US-003 — Descobrir tools sem executá-las

Como **Admin**, eu quero **descobrir nomes, schemas e annotations pelo `tools/list` oficial**, para **revisar o contrato real sem causar efeitos no sistema externo**.

**Critérios de aceite:**
- O fluxo executa somente inicialização MCP e `tools/list`.
- Nenhuma chamada `tools/call` ocorre durante descoberta ou health check.
- Timeout, falha de autenticação, resposta inválida e schema excessivo geram erro de domínio controlado.
- O erro apresentado ao cliente não contém token, credencial, stack trace ou payload remoto bruto.

### US-004 — Classificar tools administrativamente

Como **Admin**, eu quero **classificar cada tool por `server + tool` como leitura ou escrita**, para **não depender da declaração não confiável do servidor**.

**Critérios de aceite:**
- Apenas Admin cria, altera ou confirma a classificação administrativa.
- Builder e Author conseguem consultar a classificação efetiva, mas não alterá-la.
- Tool nova ou sem classificação confiável não entra em allowlist automática.
- O resultado mais restritivo entre classificação administrativa, sinal remoto, policy/papel e aprovação nativa prevalece.
- Tool de escrita nunca é marcada para execução automática.

### US-005 — Autenticar sem transportar segredo

Como **administrador do tenant**, eu quero **ligar o binding a uma Foundry connection, OBO do usuário ou endpoint público aprovado**, para **usar a identidade correta sem armazenar credencial no OKF**.

**Critérios de aceite:**
- O binding persiste somente referência tenant-local de connection ou modo de identidade.
- Token OBO e credencial resolvida existem somente em memória durante a chamada.
- Endpoint público não recebe header de autenticação.
- Qualquer chave com semântica de segredo é recusada pelo schema e ausente de logs, erros, snapshots e respostas.

### US-006 — Isolar projeção por tenant

Como **usuário de um tenant**, eu quero **ver apenas servidores, Toolboxes, connections, tools e snapshots do meu tenant**, para **não expor integrações de outros clientes**.

**Critérios de aceite:**
- Toda resolução parte do tenant autenticado no request e do projeto Foundry correspondente.
- Mesmo nome de Toolbox, connection ou servidor em tenants diferentes não mistura dados.
- Referência explícita a recurso de outro tenant falha fechada.
- Cache, snapshot e logs técnicos usam chave tenant-local sem conteúdo sensível.

### US-007 — Detectar drift por tool

Como **Admin**, eu quero **comparar uma nova descoberta com o snapshot revisado**, para **bloquear somente capacidades cujo contrato mudou**.

**Critérios de aceite:**
- Tool removida, adicionada, schema alterado ou classificação efetiva alterada aparece no diff.
- Tool nova fica indisponível até classificação e revisão Admin.
- Tool existente com schema ou permissão alterado recusa a chamada e entra em quarentena.
- Tools não alteradas permanecem disponíveis quando seus contratos continuam válidos.
- Apenas Admin libera uma tool quarentenada após nova revisão.

### US-008 — Expor indisponibilidade sem apagar contexto

Como **Builder**, eu quero **ver o último snapshot marcado como `stale` quando discovery/health falhar**, para **diagnosticar a composição sem confundir histórico com disponibilidade atual**.

**Critérios de aceite:**
- Falha de auth, timeout ou servidor indisponível preserva a última projeção como evidência histórica.
- Estado `stale` bloqueia promoção e execução até verificação atual bem-sucedida.
- O lifecycle operacional continua vindo da fonte; o produto não cria estado concorrente de disponibilidade.

### US-009 — Preservar evidência sanitizada

Como **operação e segurança**, eu quero **reter a descoberta sanitizada, limitada e criptografada**, para **investigar drift e provar o que foi revisado sem guardar conteúdo sensível desnecessário**.

**Critérios de aceite:**
- Redaction e limites são aplicados antes da primeira escrita durável.
- Snapshot contém identidade, instante, versão MCP, tools, schemas/annotations permitidas e hash canônico.
- Resultado de tool nunca integra o snapshot.
- O payload protegido herda retenção, imutabilidade e controle de acesso da evidence layer do tenant.
- A projeção normalizada, e não o payload protegido, é a superfície usada pelo Builder.

### US-010 — Promover somente contrato atual e revisado

Como **responsável pela composição**, eu quero **bloquear promoção quando a descoberta estiver ausente, stale ou incompatível**, para **não ativar binding diferente daquele que foi revisado**.

**Critérios de aceite:**
- Binding novo fica em `shadow` ou `quarantined` conforme o risco definido no detalhamento.
- Promoção exige snapshot atual, classificação administrativa completa e ausência de drift bloqueante.
- Aprovação de endpoint, classificação e aprovação de execução são decisões distintas e não reutilizáveis entre si.
- A F03 apenas entrega a decisão de conformidade; qualquer escrita compensável permanece responsabilidade da F06.

## Decisões de implementação

1. **Impacto estrutural.** A mudança altera schema versionado, contratos de API e fronteiras entre OKF, Foundry, MCP, tenancy e evidence layer. Exige validação de tech lead/arquiteto, testes de integração e decisão arquitetural aceita antes da implementação.

2. **ADRs existentes como base.** ADR-009 governa connection/aprovação nativa; ADR-011 governa Toolbox por tenant; ADR-017 governa fronteiras modulares; ADR-023 governa evidence layer; ADR-032 governa projeções, bindings, drift e classificação mais restritiva. O detalhamento deve decidir se ADR-032 será aceita ou se precisa de decisão complementar, sem duplicá-la.

3. **Módulo OKF.** Evoluir o schema de `mcp-binding` e suas validações: origem exclusiva Toolbox/servidor, versão fixa/default version, modo de autenticação, referência de connection, estado de revisão e ausência estrutural de segredo. Classificação administrativa não será autoridade gravada pelo Builder.

4. **Módulo Foundry.** Reutilizar a superfície oficial de listagem/get/versões de Toolbox e resolução tenant-local de connections. A projeção expõe dados oficiais necessários ao Builder e não publica recursos nesta fatia.

5. **Módulo platform ops.** Encapsular descoberta MCP, classificação efetiva, comparação de snapshots, estado por tool e construção runtime. Essa é a fronteira profunda: recebe binding + contexto autorizado e devolve projeção/diff/decisão de conformidade sem expor detalhes voláteis do SDK.

6. **Módulo tenancy.** Continuar resolvendo tenant, projeto e connection a partir do request. A localização exata da classificação administrativa será fechada no detalhamento, preservando isolamento e evitando transformar o registry estático atual em catálogo global para dados de tenant.

7. **Módulo audit.** Reutilizar redaction, evento hash-chained e store imutável da evidence layer. O envelope de criptografia do payload sanitizado deve usar primitiva Azure existente e ficar atrás da superfície pública do módulo dono.

8. **Descoberta oficial.** Usar `MCPTool.load_tools()`/`tools/list` conforme assinaturas instaladas. Não implementar parser ou protocolo MCP próprio e não usar `tools/call` para inferir comportamento.

9. **Classificação fail-closed.** Somente Admin mantém classificação administrativa. Metadata remota é evidência, nunca autorização. Tool desconhecida não é automaticamente executável, mesmo quando o servidor declara leitura.

10. **Quarentena por tool.** Drift bloqueante afeta a tool alterada. O binding inteiro só perde promoção quando possui pendência bloqueante; tools comprovadamente inalteradas podem permanecer disponíveis conforme a decisão detalhada.

11. **URL não confiável.** URL proposta não causa rede antes de egress + Admin. A defesa cobre parse, DNS, IP, redirects e revalidação no momento da conexão para reduzir DNS rebinding/TOCTOU.

12. **Separação de fases.** F03 não publica, compensa ou implementa UI. Ela produz projeção, snapshot, diff e decisão de conformidade consumíveis pelas fatias posteriores.

13. **Threat model obrigatório.** O detalhamento deve criar `.smart-coding/_threat-models/2026-08-31-mcp-binding-discovery.md`, cobrindo ao menos spoofing de endpoint, tampering de schema, repudiation de aprovação, disclosure cross-tenant/segredo, DoS por payload e elevação por classificação.

## Decisões de teste

1. Testar comportamento externo dos módulos, sem acoplar testes a classes geradas dos SDKs. Clientes Foundry/MCP/evidence devem ser substituídos por fakes nas suítes offline.

2. Manter testes de contrato do `mcp-binding` para origem exclusiva, versão/default version, modos de auth, referência tenant-local, campos desconhecidos e detecção recursiva de segredo.

3. Criar testes de integração do fluxo Toolbox/connection → descoberta → snapshot → projeção → diff → conformidade, incluindo versão fixa e default version.

4. Provar que descoberta e health nunca chamam `tools/call`, inclusive com servidor malicioso que anuncia side effects em metadata.

5. Cobrir erros de autenticação, timeout, protocolo/schema inválido, payload acima do limite, quantidade/profundidade excessiva e indisponibilidade com último snapshot `stale`.

6. Cobrir SSRF com loopback, RFC1918, link-local, metadata, IPv6 local, DNS rebinding e redirects entre origem permitida e destino proibido.

7. Cobrir classificação ausente, duplicada, maliciosa e conflitante; o resultado deve ser sempre o mais restritivo e escrita nunca automática.

8. Cobrir isolamento com dois tenants que usam os mesmos nomes de servidor/Toolbox/connection e snapshots diferentes.

9. Cobrir drift de adição, remoção, schema e classificação; somente a tool afetada entra em quarentena e a execução é recusada antes da chamada remota.

10. Cobrir redaction antes da persistência, criptografia em repouso por contrato, limites, ausência de segredo em logs/erros/respostas e retenção pela evidence layer.

11. Adicionar testes de integração por se tratar de mudança estrutural e testes de segurança/e2e proporcionais aos riscos críticos. Lógica crítica nova deve atingir cobertura mínima de 80%, sem substituir testes comportamentais.

12. Registrar os novos gates na fonte de verdade da CI e executar os gates existentes de OKF, tenancy, approval parity, evidence layer, import-linter e grafo modular.

## Fora do escopo

- Publicação, journal, idempotência e compensação do ChangeSet (F06).
- UI de revisão, diff visual e gesto final (F08).
- Motor universal de policy ou aprovação própria em substituição ao runtime oficial.
- Criação automática de connection e persistência de credencial.
- Catálogo operacional paralelo ao Foundry/MCP.
- Execução de tool durante descoberta/health.
- Hierarquia regulatória entre áreas, delegação cross-tenant e outros cenários F12.
- Compatibilidade semântica automática de JSON Schema.

## Pendências herdadas

- [ ] Definir contrato exato do `mcp-binding`, snapshot, classificação e projeção — impacto: crítico · bloqueia `sc-fatiar`? sim
- [ ] Definir limites de payload, quantidade de tools, profundidade de schema, timeout, redirect e concorrência — impacto: crítico · bloqueia `sc-fatiar`? sim
- [ ] Definir formato do hash canônico e matriz de drift bloqueante — impacto: crítico · bloqueia `sc-fatiar`? sim
- [ ] Definir onde a classificação administrativa tenant-local será mantida sem virar catálogo operacional — impacto: crítico · bloqueia `sc-fatiar`? sim
- [ ] Definir envelope de criptografia e controle de acesso ao payload sanitizado com primitivas Azure existentes — impacto: crítico · bloqueia `sc-fatiar`? sim
- [ ] Definir contratos HTTP, erros de domínio, códigos e observabilidade sem conteúdo sensível — impacto: médio · bloqueia `sc-fatiar`? sim
- [ ] Produzir threat model STRIDE/NORDOR-122 — impacto: crítico · bloqueia `sc-fatiar`? sim
- [ ] Obter validação de tech lead/arquiteto para a mudança estrutural e destino da ADR-032 (`Proposed`) — impacto: crítico · bloqueia `sc-fatiar`? sim

## Notas adicionais

A pesquisa F00 já confirmou as versões e superfícies oficiais relevantes. Antes de escrever chamadas SDK, o detalhamento deve repetir a verificação pontual contra pacote instalado, Microsoft Learn e samples, especialmente para `MCPTool.load_tools()`, Toolboxes e superfícies preview.

A escolha de guardar payload sanitizado e criptografado não autoriza conteúdo literalmente bruto. Redaction e limites acontecem antes da persistência; somente a projeção normalizada chega ao Builder.

---

## Histórico

Log cronológico de revisões deste PRD (mais antigo primeiro). Mantido por `sc-revisar`.

- (sem revisões ainda)
