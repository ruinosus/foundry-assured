---
workflow: critico
branch: feat/wizard-decisao-com-contexto
---

# Entendimento — Binding MCP, Toolbox e snapshot de descoberta

> Arquivo: `.smart-coding/20260831-1229-mcp-binding-discovery/01-entendimento.md`
> Artefato gerado pela skill `sc-entender` (Rede Dor Smart Coding).
> Input para a próxima fase: `sc-formalizar`.

## Escopo

- Tipo: `integration`
- Skipped: `false`

## Workflow

`critico` — escolha confirmada pelo desenvolvedor porque a F03 introduz integração MCP externa, autenticação por Foundry connection/OBO, isolamento multi-tenant, conteúdo remoto não confiável e risco de SSRF. O detalhamento e o threat model são obrigatórios antes do fatiamento.

## Objetivo

Permitir que o Builder componha `mcp-binding` a partir de Toolboxes e servidores MCP reais, com descoberta confiável de tools e schemas, sem criar catálogo operacional paralelo nem permitir execução de capacidade não revisada.

## Contexto e motivação

As fatias F00–F02 verificaram as capacidades oficiais, definiram o perfil estrito de autoria OKF e implementaram o ChangeSet multi-documento. A F03 é o próximo passo do plano: transformar referências MCP em projeções tenant-safe dos recursos oficiais, com evidência de descoberta e detecção de drift.

O Foundry e cada servidor MCP continuam sendo as fontes operacionais. O produto armazena somente o binding, a classificação administrativa e evidências necessárias para revisão, comparação e auditoria.

## Usuários e atores

- **Builder/Author:** propõe bindings usando o catálogo permitido ao tenant e pode sugerir URL MCP direta.
- **Admin:** aprova endpoint direto antes da primeira conexão, classifica tools e libera tools quarentenadas.
- **Usuário do copiloto:** executa apenas tools visíveis e autorizadas para seu papel.
- **Operação e segurança:** investigam drift, falhas de autenticação, tentativas de SSRF e evidências sanitizadas.
- **Foundry, Entra e servidor MCP:** fontes externas de recursos, identidade e descoberta.

## Dentro do escopo

- Definir `mcp-binding` para Toolbox com versão fixa ou default version.
- Admitir servidor MCP direto quando não houver Toolbox aplicável, inclusive URL proposta pelo Builder para revisão Admin.
- Impedir qualquer chamada ao endpoint direto antes de validação de egress e aprovação Admin.
- Projetar URL, connection e identidade a partir das fontes oficiais, sem segredo no OKF.
- Suportar autenticação por Foundry connection existente, OBO do usuário e endpoint público aprovado.
- Descobrir tools e schemas pelo protocolo oficial MCP `tools/list`, sem executar tools.
- Combinar classificação administrativa, sinais remotos, política e aprovação nativa pelo resultado mais restritivo.
- Tratar tool nova ou sem classificação confiável como indisponível até revisão Admin.
- Capturar snapshot sanitizado, limitado e criptografado na evidence layer do tenant.
- Detectar remoção de tool, alteração de schema e mudança de classificação.
- Recusar a chamada e quarentenar somente a tool alterada; preservar tools não afetadas.
- Expor o último snapshot como `stale` quando health/discovery falhar, bloqueando promoção e execução.
- Garantir isolamento de servidor, tool, connection e evidência por tenant.
- Cobrir auth, timeout, schema inválido, SSRF, redirecionamento, conteúdo malicioso, segredo, logs e isolamento.

## Fora do escopo

- Publicação compensável e journal de materialização do ChangeSet, tratados na F06.
- Interface visual de revisão e árvore do ChangeSet, tratadas na F08.
- Motor próprio de policy ou substituição do `approval_mode`/`require_approval` oficial.
- Catálogo local concorrente ao Foundry ou ao servidor MCP.
- Criação automática de connection ou armazenamento de credencial no binding.
- Execução de tool durante descoberta ou health check.
- Hierarquia regulatória entre áreas e delegação cross-tenant.
- Análise própria de compatibilidade semântica de JSON Schema; qualquer schema alterado exige revisão.

## Dados envolvidos

- **Lidos:** metadados de Toolbox e connection do Foundry; identidade/tenant do request; resposta MCP de `tools/list`; política administrativa por `server + tool`.
- **Transformados:** nomes de tools, schemas de entrada/saída, annotations, versão de protocolo, classificação efetiva, hash canônico e diff de descoberta.
- **Escritos:** `mcp-binding`, classificação administrativa, decisão Admin e snapshot de evidência sanitizado/limitado/criptografado.
- **Nunca persistidos:** segredo, token OBO, credencial de connection, resultado de tool ou payload remoto sem redaction e limite.
- **Sensibilidade:** conteúdo MCP é entrada arbitrária e não confiável. Pode conter segredo ou dado pessoal; redaction ocorre antes de qualquer escrita durável.

## Integrações

- Microsoft Foundry `AIProjectClient.toolboxes` e connections do projeto.
- Agent Framework `MCPStreamableHTTPTool`/`MCPTool.load_tools()` e aprovação nativa.
- Servidores MCP via `tools/list`.
- Microsoft Entra ID para identidade e OBO.
- Evidence layer da ADR-023 em Azure Storage imutável e, quando habilitado, Azure Confidential Ledger.

## Restrições conhecidas

- Usar apenas assinaturas verificadas dos SDKs instalados e documentação oficial; superfícies beta/preview ficam confinadas ao módulo dono.
- Auth por `DefaultAzureCredential`, OBO ou referência de connection; nunca API key no documento.
- Imports entre módulos somente pelas superfícies `public.py`.
- O endpoint MCP remoto não autoriza escrita por description ou annotation.
- O resultado mais restritivo entre classificação, política, papel e aprovação nativa prevalece.
- URL, resolução DNS e cada redirect obedecem à política de egress; destinos privados, link-local e metadata são recusados.
- Disponibilidade operacional é consultada na fonte e não vira lifecycle local concorrente.

## Riscos identificados

| Risco | Impacto | Mitigação |
|---|---|---|
| SSRF por URL, DNS rebinding ou redirect | Acesso a metadata, rede privada ou serviços internos | Aprovação Admin antes da primeira conexão; validação de esquema/host/IP/DNS e de cada redirect; política de egress fail-closed |
| Segredo ou dado pessoal em metadata MCP | Persistência indevida em evidência imutável | Limite estrutural e de tamanho, redaction determinística antes da escrita, criptografia em repouso e ausência em logs |
| Annotation/description maliciosa | Reclassificação indevida ou prompt injection | Tratar metadata como dado não confiável; classificação somente Admin; não usar texto remoto como instrução |
| Vazamento cross-tenant | Exposição de tools, connections ou snapshots | Resolver tudo pelo tenant do request e projeto correspondente; testes negativos entre tenants |
| Drift entre revisão e execução | Chamada com contrato ou risco diferente do aprovado | Redescobrir antes de escrita, comparar hash/schema/classificação e quarentenar a tool alterada |
| Timeout, auth inválida ou servidor indisponível | Builder toma decisão com estado antigo | Marcar último snapshot como `stale`; bloquear promoção e execução até verificação atual |
| Payload MCP excessivo ou recursivo | DoS e custo de armazenamento/processamento | Limites de bytes, quantidade de tools, profundidade de schema, tempo e concorrência |
| Retenção imutável de dado escrito por engano | Dado inadequado permanece pelo prazo WORM | Redaction antes da persistência; snapshot herda a política da evidence layer do tenant |

Pode acionar threat modeling do NORDOR-122 — confirmar em `sc-detalhar`. A nova fronteira externa, SSRF, autenticação e conteúdo não confiável tornam o threat model obrigatório para este desafio.

## Decisões resolvidas

1. **Somente Admin cria ou altera classificação administrativa de tools.**
   - **Alternativas consideradas:** permitir Author; exigir somente configuração versionada no repositório.
   - **Porquê:** classificação governa escrita e precisa permanecer fora da autoridade do Builder.

2. **O Builder pode propor URL MCP direta quando não houver Toolbox aplicável.**
   - **Alternativas consideradas:** somente allowlist prévia; proibir MCP direto no MVP.
   - **Porquê:** mantém cobertura para integrações sem Toolbox, mas sujeita a revisão administrativa.

3. **Nenhuma descoberta ocorre antes de egress e aprovação Admin.**
   - **Alternativas consideradas:** descoberta automática prévia; sandbox dedicada.
   - **Porquê:** uma simples chamada `tools/list` já cruza a fronteira de confiança e pode explorar SSRF.

4. **O MVP suporta Foundry connection, OBO e endpoint público aprovado.**
   - **Alternativas consideradas:** restringir a um único modo.
   - **Porquê:** cobre Toolboxes, identidade do usuário e servidores públicos sem transportar segredos.

5. **Drift é isolado por tool.**
   - **Alternativas consideradas:** quarentenar o binding inteiro; tratar tool nova automaticamente como escrita.
   - **Porquê:** preserva capacidades não alteradas sem expor capacidade nova não revisada.

6. **Schema alterado recusa a chamada e quarentena a tool.**
   - **Alternativas consideradas:** bloquear o binding inteiro; aceitar mudança considerada compatível.
   - **Porquê:** evita construir um analisador próprio de compatibilidade e exige revisão do contrato real.

7. **A evidence layer recebe payload sanitizado, limitado e criptografado.**
   - **Alternativas consideradas:** somente projeção normalizada; payload bruto sem redaction; somente hash.
   - **Porquê:** mantém fidelidade suficiente para auditoria sem guardar segredo detectado ou conteúdo ilimitado. A projeção normalizada continua sendo a superfície do Builder.

8. **A retenção do snapshot herda a política da evidence layer do tenant.**
   - **Alternativas consideradas:** 90 dias fixos; somente snapshot atual.
   - **Porquê:** evita política concorrente e preserva histórico de drift conforme a obrigação do tenant.

9. **Somente Admin libera tool quarentenada.**
   - **Alternativas consideradas:** Admin ou Approver; Author propõe e Approver libera.
   - **Porquê:** a reativação depende da mesma autoridade que classifica a tool.

10. **Falha de health/discovery expõe o último snapshot como `stale`.**
    - **Alternativas consideradas:** esconder todas as tools; tratar snapshot anterior como disponível.
    - **Porquê:** preserva contexto para diagnóstico sem confundir evidência histórica com disponibilidade atual.

## Decisões pendentes

- [ ] Definir no detalhamento o contrato exato do `mcp-binding`, snapshot, classificação e projeção.
- [ ] Definir limites de payload, quantidade de tools, profundidade de schema, timeout, redirect e concorrência.
- [ ] Definir formato do hash canônico e quais mudanças geram drift bloqueante.
- [ ] Definir onde a classificação administrativa tenant-local será mantida sem virar catálogo operacional.
- [ ] Definir envelope de criptografia e controle de acesso ao payload sanitizado usando primitivas Azure existentes.
- [ ] Definir contratos HTTP, códigos de erro e observabilidade sem conteúdo sensível.
- [ ] Produzir threat model STRIDE/NORDOR-122 antes do fatiamento.

## Próximo passo sugerido

Rodar `sc-formalizar` para transformar este entendimento em PRD. Como o workflow é crítico, o PRD deve marcar detalhamento obrigatório; depois dele, `sc-detalhar` fecha contratos, threat model e assinaturas oficiais antes do fatiamento.

---

## Histórico

Log cronológico de revisões deste artefato (mais antigo primeiro). Mantido por `sc-revisar`.

- (sem revisões ainda)
