# Customização e Expansão de Domínio

Abaixo estão apenas afirmações extraídas dos arquivos fornecidos (CUSTOMIZE.md, SECOND-DOMAIN-WIKI-PLAN.md). Cada item indica o arquivo-fonte entre parênteses.

## Visão geral (padrão do projeto)

O projeto é apresentado como um padrão "ask → ground → resolve → escalate": um desenvolvedor faz uma pergunta, o sistema fundamenta a resposta num knowledge base e pode escalar para uma ação humana-aprovada quando necessário (CUSTOMIZE.md).

## Pontos a trocar ao adaptar o domínio

As partes específicas do domínio que se substituem são listadas no repositório; os caminhos indicados são esses (CUSTOMIZE.md):

- 1 — Knowledge corpus: arquivos em `apps/backend/app/knowledge/corpus/*.md` (drop-in). (CUSTOMIZE.md)  
- 2 — Agent prompts: `apps/backend/app/agents/prompts.py` (reescrever). (CUSTOMIZE.md)  
- 3 — The action (ex.: ticket → sua ação): `apps/backend/app/tools/`, `apps/backend/app/workflow/escalation.py`, e a convenção `TICKET:` (reescrever). (CUSTOMIZE.md)  
- 4 — Identity / labels: `apps/frontend/lib/branding.ts`, `app/page.tsx` (ajustar). (CUSTOMIZE.md)  
- 5 — Eval datasets: `apps/backend/eval/datasets/*.jsonl` (dados a substituir). (CUSTOMIZE.md)  
- 6 — Access (quem vê cada doc): grupos Entra + `COCKPIT_ACL_GROUP_MAP`; cada fonte tem `groups` no manifest de bundle (ou um mapa externo via `COCKPIT_ACL_CLASSIFICATION`) (dados a configurar). (CUSTOMIZE.md)

Regra prática indicada: #1, #4, #5, #6 são configurados; #2 e #3 são reescritos (CUSTOMIZE.md).

## 1 — Knowledge corpus (instruções extraídas)

- O KB fundamentado é construído a partir de markdown; cada tópico é um arquivo `.md` e o título H1/filename é o que é citado (CUSTOMIZE.md).  
- Para fontes não-Markdown, recomendam converter para Markdown com uma ferramenta (ex.: MarkItDown) e há um helper sugerido: `./scripts/to-markdown.sh -o apps/backend/app/knowledge/corpus *.pdf` (CUSTOMIZE.md).  
- Procedimento de ingestão sugerido:  
  ```bash
  cd apps/backend && uv run python -m app.knowledge.ingest
  ```
  (CUSTOMIZE.md)

## 2 — Agent prompts (instruções)

- Todas as instruções de agente residem em um arquivo: `apps/backend/app/agents/prompts.py`. Dois consumidores leem dele: o workflow (`TRIAGE_/RETRIEVE_/RESOLVE_INSTRUCTIONS`) e o concierge (`CONCIERGE_*_INSTRUCTIONS`) (CUSTOMIZE.md).  
- Invariantes a preservar (descritas no arquivo):  
  - RETRIEVE deve emitir `NO_MATCH` quando nada for encontrado; RESOLVE deve recusar (dizer "I don't know") em `NO_MATCH`. (CUSTOMIZE.md)  
  - RESOLVE deve emitir uma linha única `TICKET: <summary>` quando uma ação for necessária; se renomear esse sinal, deve-se atualizar ambos os lugares que o consomem. (CUSTOMIZE.md)  
- Observação sobre o hosted agent: `apps/hosted-agent/main.py` é autocontido e não importa este arquivo; ele replica prompts inline — se usar o hosted-agent, mantê-los sincronizados. (CUSTOMIZE.md)

## 3 — A ação / escalonamento (fluxo e arquivos)

- Fluxo documentado: RESOLVE emite `TICKET: <summary>` → `workflow/escalation.py` (EscalationExecutor) detecta → `request_info` (aprovação humana) → em aprovação → `app/tools/tickets.py` `create_ticket()` persiste e retorna (CUSTOMIZE.md).  
- Para trocar a ação: substituir o conteúdo de `apps/backend/app/tools/tickets.py` (manter a forma: função + `tool(...)` wrapper para o hosted agent), ajustar o trigger em `apps/backend/app/workflow/escalation.py` para analisar o prefixo correspondente e adaptar/renomear as views (`app/api/tickets.py`, `components/tickets/TicketsView.tsx`, rota `/tickets`) conforme necessário. (CUSTOMIZE.md)  
- Se não houver ação (assistente só Q&A), é possível remover o nó `escalate` da cadeia em `apps/backend/app/workflow/graph.py` (substituir `.add_chain([triage, retrieve, resolve])`) e instruir RESOLVE a nunca emitir `TICKET:`. (CUSTOMIZE.md)

## 4 — Identity / labels (onde alterar)

- Identidade UI centralizada: alterar quatro strings em `apps/frontend/lib/branding.ts` (`product`, `tagline`, `description`, `assistant`) para re-skin da UI; conteúdo está em `apps/frontend/app/page.tsx` (herói Overview e cartões de "Capabilities") (CUSTOMIZE.md). (CUSTOMIZE.md)  
- Nomes de recursos em `apps/backend/app/core/settings.py` (`azure_search_knowledge_base`, `foundry_memory_store`, `hosted_agent_name`) são strings de recurso Azure e só devem ser alteradas se for provisionar recursos novos. (CUSTOMIZE.md)

## 5 — Datasets de avaliação (formato e comandos)

- Os datasets estão em `apps/backend/eval/datasets/` — `golden.jsonl` e `adversarial.jsonl` (CUSTOMIZE.md). (CUSTOMIZE.md)  
- Formato `golden.jsonl` (um objeto por linha, três campos):  
  ```json
  {"query": "<pergunta real>",
   "source": "<H1 title do doc de corpus>",
   "expected_output": "<síntese do acerto>"}
  ```
  O `source` deve corresponder a um título H1 dos `.md` do corpus; a verificação de citação deriva automaticamente os títulos do corpus. (CUSTOMIZE.md)  
- `adversarial.jsonl` tem forma similar; prompts de jailbreak/secret-leak usam `"source": ""` (CUSTOMIZE.md).  
- Comandos de validação sugeridos:  
  ```bash
  cd apps/backend
  uv run python -m eval.run_eval
  uv run python -m eval.run_eval --cloud
  uv run python -m eval.run_eval --safety
  uv run python -m eval.run_eval --self-test
  ```
  (CUSTOMIZE.md)

## Material do segundo domínio (resumo das seções do plano)

Trechos do plano para um segundo domínio (Cockpit expert) e o padrão LLM Wiki constam em SECOND-DOMAIN-WIKI-PLAN.md. Pontos extraídos:

- Objetivo: adicionar um segundo domínio — um agente especialista em Cockpit — que demonstra o padrão LLM Wiki (generate + consume) na Foundry, e usar o padrão aberto de Agent Skills e o conjunto `deep-wiki` (SECOND-DOMAIN-WIKI-PLAN.md).  
- Consumo/retrieval: usar Foundry IQ via `AzureAISearchContextProvider` para retorno de contexto com citações; a disciplina de citar/recusar é parte das instruções do agente (SECOND-DOMAIN-WIKI-PLAN.md).  
- Geração (Wiki Builder): um agente Wiki Builder lê a fonte real (ferramentas de arquivo) e escreve um wiki fiel no formato que a ingestão consome; dois caminhos de geração são descritos (um via Foundry workflow usando `agent-framework` + `FoundryChatClient` e outro via Copilot CLI / deep-wiki). (SECOND-DOMAIN-WIKI-PLAN.md)  
- Arquivo/funcionalidade referida: `app/knowledge/wiki_builder.py` gera um bundle fiel a partir de um repositório no Foundry (plano descrito em SECOND-DOMAIN-WIKI-PLAN.md). (SECOND-DOMAIN-WIKI-PLAN.md)  
- A documentação inclui um quadro de "Status" com vários itens e checagens (SECOND-DOMAIN-WIKI-PLAN.md).

--- 

Referências: CUSTOMIZE.md; SECOND-DOMAIN-WIKI-PLAN.md.