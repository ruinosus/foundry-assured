## Agentes e Fluxos de Trabalho

Visão geral
- Este módulo define agentes conversacionais (concierge, cockpit, selfwiki) e constrói um workflow de quatro nós encadeados: triage → retrieve → resolve → escalate. (app/workflow/graph.py:build_helpdesk_workflow)  
- O nó de escalonamento (EscalationExecutor) pausa para aprovação humana quando o resolve sinaliza um ticket e só cria o ticket após aprovação. (app/workflow/escalation.py:EscalationExecutor)

Sumário rápido
| Componente | Responsabilidade / observação | Ponto de construção | Fonte |
|---|---:|---|---|
| Helpdesk Concierge | Agente "concierge"; quando a KB de runbooks está configurada, é associado a um AzureAISearchContextProvider em modo agentic; caso contrário, usa instruções sem KB. | `build_concierge_agent()` | (app/agents/concierge.py:build_concierge_agent, app/agents/concierge.py:_knowledge_configured) |
| CockpitExpert | Agente Q&A fundamentado na base de conhecimento do Cockpit; criado com `SecureAzureAISearchProvider` e `COCKPIT_INSTRUCTIONS`. | `build_cockpit_agent()` | (app/agents/cockpit.py:build_cockpit_agent, app/agents/prompts.py:COCKPIT_INSTRUCTIONS) |
| SelfWikiExpert | Agente Q&A sobre o repositório (deep-wiki); criado com `AzureAISearchContextProvider` e `SELFWIKI_INSTRUCTIONS`. | `build_selfwiki_agent()` | (app/agents/selfwiki.py:build_selfwiki_agent, app/agents/prompts.py:SELFWIKI_INSTRUCTIONS) |
| Workflow triage→retrieve→resolve→escalate | Constrói a cadeia de executores por requisição. | `build_helpdesk_workflow()` | (app/workflow/graph.py:build_helpdesk_workflow) |
| Secure agentic retrieval | Provider que injeta o token do chamador e aplica trimming por componentes autorizados antes que o modelo veja o contexto. | `SecureAzureAISearchProvider` | (app/agents/secure_search.py:SecureAzureAISearchProvider) |

Arquitetura — três domínios de agente (alto nível)
1. Concierge — Agente de helpdesk. Código indica comportamento em "Phase 0/1": funciona sem KB e, quando a KB está configurada, é associado a um provider de busca em modo agentic. (app/agents/concierge.py:_knowledge_configured, app/agents/concierge.py:build_concierge_agent)  
2. CockpitExpert — Domínio separado, criado por build_cockpit_agent usando `SecureAzureAISearchProvider` em modo agentic e `COCKPIT_INSTRUCTIONS`. (app/agents/cockpit.py:build_cockpit_agent, app/agents/prompts.py:COCKPIT_INSTRUCTIONS)  
3. SelfWikiExpert — Agente sobre a deep-wiki gerada a partir deste repositório; usa o provider agentic sem a camada de trim por componente. (app/agents/selfwiki.py:build_selfwiki_agent, app/agents/selfwiki.py docstring)

Componentes detalhados (resumo)
| Nome | Tipo / comportamento | Ponto(s) chave no código | Fonte |
|---|---|---:|---|
| `FoundryChatClient.as_agent(...)` | Factory que cria um Agent a partir de um cliente FoundryChatClient. | Chamado em vários builders de agente (`client.as_agent(...)`). | (app/agents/cockpit.py:build_cockpit_agent), (app/agents/selfwiki.py:build_selfwiki_agent), (app/agents/concierge.py:build_concierge_agent) |
| `AzureAISearchContextProvider` | Provider de contexto usado em modo agentic nos agentes que consultam uma KB. | Usado em concierge e no nó retrieve do workflow. | (app/agents/concierge.py:build_concierge_agent), (app/workflow/agents.py:build_retrieve_agent) |
| `SecureAzureAISearchProvider` | Subclasse que injeta o token do chamador e aplica trimming por componente autorizado após o agentic retrieve. | Implementa `_ensure_knowledge_base()` e `_agentic_search(...)` com wrapping e trimming. | (app/agents/secure_search.py:SecureAzureAISearchProvider) |
| `FoundryMemoryProvider` | Provider de memória por escopo; costruído quando a memória está habilitada; `update_delay=0`. | `build_memory_provider()` retorna `FoundryMemoryProvider` ou `None`. | (app/workflow/memory.py:build_memory_provider) |
| `EscalationExecutor` | Executor que transforma um sinal textual de ticket em uma pausa de aprovação humana e só cria o ticket após aprovação. | `EscalationExecutor.on_resolve()` e `on_decision()`. | (app/workflow/escalation.py:EscalationExecutor) |

Componentes — explicação e evidências
- build_cockpit_agent():
  - Cria um `FoundryChatClient` com `DefaultAzureCredential`, instancia um `SecureAzureAISearchProvider` em `mode="agentic"` e retorna `client.as_agent(...)` com `COCKPIT_INSTRUCTIONS`. (app/agents/cockpit.py:build_cockpit_agent, app/agents/prompts.py:COCKPIT_INSTRUCTIONS)
- SecureAzureAISearchProvider (comportamento):
  - `_ensure_knowledge_base()` envolve o cliente de retrieval para injetar o token do chamador como `x_ms_query_source_authorization` quando disponível. `_agentic_search()` chama o super, obtém o token do chamador, consulta `authorized_components()` e aplica `trim_agentic_content()` aos conteúdos retornados, retornando mensagens com conteúdo filtrado. (app/agents/secure_search.py:SecureAzureAISearchProvider, app/agents/secure_search.py:_ensure_knowledge_base, app/agents/secure_search.py:_agentic_search)
- Workflow por requisição:
  - `build_helpdesk_workflow()` é uma factory per-request que chama `credential_for_request()` e `memory_scope()`, cria providers/agentes com essas credenciais/escopo, e monta a cadeia triage → retrieve → resolve → escalate. (app/workflow/graph.py:build_helpdesk_workflow)
- Memória por usuário:
  - `build_memory_provider()` retorna um `FoundryMemoryProvider` configurado com `update_delay=0` quando `memory_enabled()` é verdadeiro. Esse memory provider é passado como `context_providers` ao agente `resolve` quando presente. (app/workflow/memory.py:build_memory_provider, app/workflow/graph.py:build_helpdesk_workflow)
- Escalonamento / tickets:
  - `EscalationExecutor.on_resolve()` inspeciona `response.agent_response.text`; se começar com `"TICKET:"`, chama `ctx.request_info(...)` para pausar e aguardar decisão. Em `on_decision()`, quando `approved` é True, chama `create_ticket()` e `yield_output(...)`. (app/workflow/escalation.py:EscalationExecutor, app/workflow/escalation.py:on_decision)

Segurança e trimming de resultados agentic
- Objetivo e mecanismo (conforme o código):
  - O provider seguro passa o token do chamador ao cliente de retrieval (injeção do header `x-ms-query-source-authorization`) e, depois do agentic retrieve, determina o conjunto de componentes autorizados chamando `authorized_components(caller_token)`; em seguida remove qualquer chunk cujo componente não esteja nesse conjunto antes de expor o contexto ao modelo. (app/agents/secure_search.py:SecureAzureAISearchProvider, app/agents/secure_search.py:authorized_components, app/agents/secure_search.py:trim_agentic_content)
  - `authorized_components()` realiza chamadas HTTP ao endpoint de busca com um token de serviço e o token do chamador no header `x-ms-query-source-authorization`, percorre páginas via `@odata.nextLink` e devolve o conjunto de componentes encontrados; em caso de erro, retorna conjunto vazio. (app/agents/secure_search.py:authorized_components)
  - `trim_agentic_content()` tenta interpretar o texto como um array JSON de chunks e mantém apenas os chunks cujo componente, extraído por `_chunk_component()`, esteja no conjunto `allowed`. (app/agents/secure_search.py:trim_agentic_content, app/agents/secure_search.py:_chunk_component)

Fluxo de trimming — pseudocódigo (reflete a implementação)
```python
result_messages = await super()._agentic_search(messages)
token = _caller_search_token()
if not token:
    return result_messages
allowed = authorized_components(token)
for m in result_messages:
    new_contents = [trim_agentic_content(c, allowed) for c in m.contents]
    emit Message(role=m.role, contents=new_contents)
```
(Fonte: app/agents/secure_search.py:SecureAzureAISearchProvider, authorized_components, trim_agentic_content)

Detalhes de implementação relevantes (por arquivo)
- app/agents/cockpit.py
  - `cockpit_configured()` verifica `settings.azure_search_endpoint` e `settings.cockpit_search_knowledge_base`. `build_cockpit_agent()` usa `DefaultAzureCredential`, `FoundryChatClient` e `SecureAzureAISearchProvider` em `mode="agentic"`. (app/agents/cockpit.py:cockpit_configured, app/agents/cockpit.py:build_cockpit_agent)
- app/agents/concierge.py
  - `build_concierge_agent()` retorna um agente com `AzureAISearchContextProvider(mode="agentic")` quando `_knowledge_configured()` é True; caso contrário, retorna um agente sem context provider e com instruções não-grounded. (app/agents/concierge.py:build_concierge_agent, app/agents/concierge.py:_knowledge_configured)
- app/agents/prompts.py
  - `RESOLVE_INSTRUCTIONS` define o contrato que sinaliza um ticket com a linha exata `TICKET: <one-line summary>`. (app/agents/prompts.py:RESOLVE_INSTRUCTIONS)
- app/workflow/escalation.py
  - `EscalationExecutor.on_resolve()` e `on_decision()` implementam a pausa para aprovação e a criação do ticket somente após aprovação. (app/workflow/escalation.py:EscalationExecutor)
- app/workflow/stream_fix.py
  - `OrderedAgentFrameworkWorkflow.run()` reordena/suprime eventos para garantir que mensagens de texto abertas sejam encerradas antes de eventos terminais e suprime o trio de eventos de tool-call para `request_info`. (app/workflow/stream_fix.py:OrderedAgentFrameworkWorkflow)

Diagrama de decisão (fluxo de ticket — reflete EscalationExecutor)
```mermaid
flowchart TD
  A[Resolve output] --> B{Texto começa com "TICKET:"?}
  B -- sim --> C[EscalationExecutor.request_info -> pausa para aprovação]
  C --> D{Aprovado?}
  D -- sim --> E[create_ticket() -> yield_output(confirmacao)]
  D -- não --> F[yield_output("No ticket opened")]
  B -- não --> G[yield_output(resposta do resolve)]
```
(Fonte: app/workflow/escalation.py:EscalationExecutor, app/agents/prompts.py:RESOLVE_INSTRUCTIONS)

Operacionais e observações (fatos lidos no código)
- O workflow é construído por requisição por `build_helpdesk_workflow()`, que chama `credential_for_request()` e `memory_scope()` e monta triage → retrieve → resolve → escalate. (app/workflow/graph.py:build_helpdesk_workflow)  
- O sinal de ticket textual exigido/inspetado é `TICKET: <one-line summary>`. (app/agents/prompts.py:RESOLVE_INSTRUCTIONS) (app/workflow/escalation.py:EscalationExecutor)  
- `SecureAzureAISearchProvider` injeta o token do chamador em retrieval e aplica trimming por componentes autorizados via `authorized_components()` + `trim_agentic_content()`. Em caso de erro ao obter autorizações, `authorized_components()` retorna conjunto vazio. (app/agents/secure_search.py:SecureAzureAISearchProvider, app/agents/secure_search.py:authorized_components, app/agents/secure_search.py:trim_agentic_content)

Referências (arquivos citados)
| Arquivo | Elemento citado |
|---|---|
| app/agents/cockpit.py | build_cockpit_agent, cockpit_configured |
| app/agents/concierge.py | build_concierge_agent, _knowledge_configured |
| app/agents/selfwiki.py | build_selfwiki_agent |
| app/agents/prompts.py | TRIAGE_INSTRUCTIONS, RETRIEVE_INSTRUCTIONS, RESOLVE_INSTRUCTIONS, CONCIERGE_*, COCKPIT_INSTRUCTIONS, SELFWIKI_INSTRUCTIONS |
| app/agents/secure_search.py | SecureAzureAISearchProvider, authorized_components, trim_agentic_content, _chunk_component |
| app/workflow/agents.py | build_triage_agent, build_retrieve_agent, build_resolve_agent |
| app/workflow/graph.py | build_helpdesk_workflow |
| app/workflow/memory.py | build_memory_provider |
| app/workflow/escalation.py | EscalationExecutor, TicketApprovalRequest |
| app/workflow/stream_fix.py | OrderedAgentFrameworkWorkflow