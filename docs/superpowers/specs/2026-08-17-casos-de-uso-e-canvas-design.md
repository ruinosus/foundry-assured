---
title: 'Design: casos de uso, canvas de montagem e o retorno que o negócio pergunta'
description: Uma camada acima dos agentes, em linguagem de negócio, com canvas que monta o fluxo. A pesquisa resolveu a incógnita central — o canvas emite YAML declarativo do Agent Framework (formato Microsoft, GA) e o nosso hosted agent executa. Os workflows do portal do Foundry são aposentados em 01/12/2026, então construir sobre eles seria construir sobre superfície morta.
type: design
audience: contributor
status: draft
updated: 2026-08-17
---

# Casos de uso, canvas e ROI

## O problema, dito como o dono do projeto disse

> "ninguém de negócio consegue ler essa lista imensa de agents"

E está certo. A tela mostra `triage`, `retrieve`, `resolve`, `concierge-grounded` — **peças de
máquina**. Quem é de negócio abre e não encontra *"o helpdesk"*, porque o helpdesk foi dissolvido
em cinco linhas técnicas. O produto mostra as peças e esconde a coisa.

O problema não é a quantidade. É que **o nível de abstração está errado para o público**.

## A incógnita central, resolvida

A pergunta que travava tudo: *um canvas de montagem produz algo que EXECUTA, ou seria um editor
decorativo?*

**Executa — e o formato não deve ser nosso.**

O Microsoft Agent Framework tem uma **linguagem declarativa de workflow em YAML**, GA desde
23/07/2026, com `WorkflowFactory` que a carrega e executa. Está **instalado neste repositório**
(`agent-framework-declarative 1.0.2`), e há um sample oficial do fluxo exato que precisamos
(`foundry-samples/…/09-declarative-customer-support`): triagem → roteamento → resposta.

```
canvas  →  YAML declarativo (Microsoft)  →  WorkflowFactory  →  hosted agent  →  executa
                   ↑ formato de 1ª parte      ↑ runtime de 1ª parte
```

### E o caminho óbvio está morrendo

O portal do Foundry TEM um designer visual de workflow, em preview. **A Microsoft o aposenta em
1º de dezembro de 2026**, junto com a execução in-portal:

> "Microsoft Foundry is retiring workflows on December 1, 2026. If you're looking to build new
> workflows, use Microsoft Agent Framework."

O YAML sobrevive — rodando dentro de um container que se deploya. Construir sobre o designer do
portal seria construir sobre superfície com data de morte anunciada. Além disso: *"Hosted agents
aren't supported in the workflow designer"* — os nossos quatro domínios não caberiam nele.

### Onde isso deixa a MÁXIMA MAIOR

| Peça | Quem escreve |
|---|---|
| Linguagem do workflow | **Microsoft** (declarative YAML) |
| Interpretador, checkpointing, HITL | **Microsoft** (`WorkflowFactory`, `ctx.request_info`) |
| Hosting, protocolo Responses | **Microsoft** (`ResponsesHostServer`) |
| **Canvas + serializador + validador** | **nós** ← a lacuna |

É literalmente *"preencher lacunas e trazer outros perfis de usuário para consumir recursos
Microsoft"*: o usuário de negócio ganha o designer que o portal só dá a quem tem RBAC no Azure, e
o artefato que ele produz é formato Microsoft, executado por runtime Microsoft.

## O que o schema permite — e o que o canvas NÃO pode prometer

A linguagem **não tem "nós e arestas"**. É uma **lista aninhada de ações**, com o grafo emergindo
de `ConditionGroup` + `GotoAction`. Um DAG arbitrário desenhado livremente **não mapeia 1:1**.

**Consequência de desenho, e ela é dura:** o canvas precisa restringir o que se pode desenhar.
Cinco restrições que ele deve impor, ou gera YAML inválido:

1. todo nó tem `id` único — é a chave de `GotoAction`;
2. aresta condicional só sai de `ConditionGroup`/`If` — não há aresta condicional livre;
3. aresta "para trás" vira `GotoAction`, nunca uma seta arbitrária;
4. expressões passam por Power Fx com prefixo `=` e escopo (`Local.`, `System.`, `Workflow.Inputs.`);
5. `InvokeMcpTool` e `HttpRequestAction` exigem handler registrado, senão o **build falha**.

Um canvas que deixe desenhar livremente e falhe na publicação seria pior que um canvas com menos
liberdade. **A restrição é a funcionalidade.**

### As primitivas que viram nós

| Nó no canvas | Ação | O que a pessoa preenche |
|---|---|---|
| Agente | `InvokeAzureAgent` | qual agente (lista real), onde guarda a saída |
| Ferramenta | `InvokeFunctionTool` / `InvokeMcpTool` | qual, argumentos, **exige aprovação?** |
| Decisão | `ConditionGroup` | condições e o que fazer em cada |
| Perguntar | `Question` | o texto, onde guarda |
| **Aprovação** | `RequestExternalInput` | o texto — pausa o fluxo de verdade |
| Mensagem | `SendActivity` | o texto |
| Fim / salto | `EndWorkflow` / `GotoAction` | para onde |

**O HITL é nativo e é o mesmo que já usamos.** `RequestExternalInput` e `requireApproval` emitem
`request_info`, que é exatamente o mecanismo por trás do approval card de hoje. O card não muda.

## A estrutura proposta

### Caso de uso é entidade, e o registro dele é `metadata`

Decisão do dono: entidade que se cria e edita, não visão. E ele fica **no Foundry**, pela SEGUNDA
MÁXIMA — mas o SDK não expõe o agrupador (`accounts/projects/applications`), então o registro vai
onde já existe superfície: **`metadata` do agente publicado**.

```
agente `helpdesk-concierge`
  metadata.use_case      = "helpdesk"
  metadata.use_case_name = "Atendimento a desenvolvedores"
  metadata.runtime       = "backend"
```

Cada caso de uso é um **agente do tipo workflow** publicado, cujo YAML é o fluxo montado. As
peças que ele invoca são os agentes que já existem. Sem store novo, sem segunda verdade — o que a
SEGUNDA MÁXIMA exige.

### A tela que o negócio abre

```
CASOS DE USO

  💬 Atendimento a desenvolvedores          ativo
     4 passos · base: helpdesk-kb · 127 conversas no mês
     ▸ ver fluxo   ▸ editar conteúdo   ▸ resultados

  🧪 Triagem de plantão                     ativo
     3 passos · aprovação humana na escalação

  [ + Novo caso de uso ]
```

Os agentes continuam existindo em "Meus agentes" — para quem quiser a peça. O que muda é qual das
duas telas é a porta de entrada.

## O ROI — e por que ele é o item mais arriscado

O dono acrescentou "medir ROI ou algo similar, note, ela é de NEGÓCIO". É o que ela mais vai
olhar, e é onde é mais fácil produzir um número bonito e falso.

**O que temos hoje, de verdade:**

| Dado | Onde | Confiável? |
|---|---|---|
| conversas por caso de uso | sessões do agente (`list_sessions`) | ✅ |
| escalações abertas | `tickets.jsonl` | ✅ |
| respostas com citação | gate de eval | ✅ |
| aprovação/edição/recusa em HITL | eventos do interrupt | ✅ (não persistido hoje) |
| custo em tokens | telemetria OTEL | ⚠️ precisa agregação |

**O que NÃO temos, e sem o que "ROI" vira ficção:** a linha de base. Quanto tempo levava antes,
quantos desses atendimentos teriam virado ticket sem o assistente, quanto custa uma hora da pessoa
que foi poupada.

**Proposta honesta:** a tela mostra **taxa de resolução sem escalação** (conversas ÷ tickets
abertos) e **volume atendido**, com a linha de base como **campo que a empresa preenche** — "um
atendimento manual custa X minutos". Aí o número é aritmética explícita sobre um parâmetro que
alguém assumiu, não uma medida inventada. **Um ROI cuja premissa está visível é útil; um que
esconde a premissa é propaganda.**

## Fases

| # | Entrega | Risco |
|---|---|---|
| **1** | Casos de uso como VISÃO: agrupa os agentes por domínio, em linguagem de negócio | baixo — só apresentação |
| **2** | Ler o fluxo: diagrama gerado do YAML (o repo já renderiza Mermaid) | baixo |
| **3** | Executar um workflow declarativo: um domínio migrado para YAML + `WorkflowFactory` | **médio — prova o runtime** |
| **4** | Canvas de montagem, com as 5 restrições, emitindo YAML | alto |
| **5** | Publicar o caso de uso como agente workflow com `metadata.use_case` | médio |
| **6** | Painel de resultados: volume, taxa de resolução, premissa editável | médio |

**A fase 3 é o gate de realidade.** Antes de construir editor, um fluxo real precisa rodar pelo
`WorkflowFactory` neste backend. Se isso não funcionar, as fases 4–5 não fazem sentido — e é
barato descobrir agora.

### Fase 3 — o que já foi PROVADO, contra o serviço real

Três camadas, cada uma verificada antes da seguinte:

| # | Verificação | Resultado |
|---|---|---|
| 1 | YAML mínimo carrega pelo `WorkflowFactory` | ✅ devolve `Workflow`, com `as_agent` |
| 2 | O workflow EXECUTA | ✅ `WorkflowAgent.run()` devolveu a resposta |
| 3 | `InvokeAzureAgent` com agente REAL do repo | ✅ o `TriageAgent`, com o prompt do AgentSchema, classificou de verdade |

A camada 3 é a que importa: o agente veio do **mesmo documento AgentSchema** que o resto do
produto usa, montado com o **mesmo `FoundryChatClient`** que o helpdesk monta hoje. O YAML declara
a ORDEM; o conteúdo continua vindo de onde sempre veio.

**A DESCOBERTA MAIS IMPORTANTE: Power Fx exige .NET, e sem ele o fluxo TRAVA EM SILÊNCIO.**

O fluxo de três passos com `input.arguments: {pergunta: =Local.Triagem}` **não completa**: nenhuma
exceção, nenhuma mensagem, apenas nunca responde. O mesmo fluxo **sem as expressões** executa
inteiro e devolve resposta real. O log traz `Microsoft.NETCore.App, version '8.0.0'` não
encontrado — o avaliador de Power Fx é .NET, carregado por `clr_loader`.

Isto muda o desenho de duas formas, e as duas são duras:

1. **O container que executar workflows declarativos precisa de .NET.** Não é opcional: passar
   dado de um nó para outro é a razão de existir do canvas, e passar dado é Power Fx.
2. **A falha é silenciosa, que é a pior classe.** Um fluxo publicado num ambiente sem .NET não
   dá erro — apenas nunca responde. Ninguém olharia o runtime .NET ao investigar "o assistente
   não responde".

O gate de round-trip (`YAML → WorkflowFactory.build`) NÃO pega isso: o build passa, a execução é
que trava. Então o gate precisa ser de **execução**, não de build — um fluxo mínimo com uma
expressão Power Fx, executado no CI, que falha se a resposta não vier.

Isto ecoa a nota do `CLAUDE.md` sobre o reader de prompts recusar PowerFx quando falta .NET. O
mesmo runtime, o mesmo buraco, agora numa superfície onde ele custa mais.

**Duas descobertas do caminho:**

`responseObject` espera JSON. O `TriageAgent` devolve texto (`Intent: … / Urgency: …`), e o runtime
avisa e guarda como string — degradação limpa, não erro. Mas significa que um passo cujo resultado
alimenta uma CONDIÇÃO precisa de saída estruturada: o canvas terá de exigir isso do agente
escolhido, ou a decisão que vier depois não terá o que comparar.

O nome da classe do cliente não é o que a documentação de outros contextos sugere — é
`FoundryChatClient`, com `model=` e `credential=`, exatamente como `modules/helpdesk` já faz. Ler
o repositório foi mais rápido que ler a documentação.

## O gate que transforma "editor decorativo" em invariante

O serializador canvas→YAML é nosso e não tem equivalente de primeira parte. Sem verificação, ele
produziria YAML plausível e inválido, e o erro apareceria na publicação.

```
canvas JSON  →  YAML  →  WorkflowFactory.create_workflow_from_yaml()  →  build sem exceção
```

Offline, no CI. O build valida ações, alvos de `GotoAction` e handlers obrigatórios — ele já é o
validador, e usá-lo é mais barato e mais fiel que escrever um nosso.

## O que NÃO vamos fazer

- inventar formato de workflow — a linguagem é da Microsoft, GA e documentada;
- construir sobre o designer do portal — aposentado em 01/12/2026, e não aceita hosted agents;
- usar Prompt flow — aposentado em 20/04/2027;
- store próprio para caso de uso — `metadata` do agente publicado basta, e não cria segunda verdade;
- **prometer ROI sem premissa visível.**

## Referências

- [Declarative Workflows — Agent Framework](https://learn.microsoft.com/en-us/agent-framework/workflows/declarative) — schema, ações, Power Fx
- [Build a workflow in Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/workflow) — retirement 01/12/2026 e guia de migração
- `foundry-samples/…/09-declarative-customer-support` — o fluxo triagem→roteamento→resposta
- Instalado aqui: `agent-framework-declarative 1.0.2` (`WorkflowFactory.create_workflow_from_yaml`)
- SEGUNDA MÁXIMA e MÁXIMA MAIOR em `CLAUDE.md`
