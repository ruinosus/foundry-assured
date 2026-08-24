# ADR-027 — O MCP vira app separado para alcançar o FastMCP 4; o núcleo limpo é o que ele importa

- **Status:** Proposed
- **Date:** 2026-08-24
- **Context:** [ADR-017](./ADR-017-module-boundaries.md) (as fronteiras que tornam isto possível),
  [ADR-020](./ADR-020-canonical-frameworks-modular-organization.md) (usar cada framework do jeito
  mais canônico), [ADR-023](./ADR-023-evidence-layer.md) (a camada de evidência que o T6 publica),
  [`docs/superpowers/specs/2026-08-24-mcp-server-fastmcp-design.md`](../superpowers/specs/2026-08-24-mcp-server-fastmcp-design.md)

## Contexto

O servidor MCP shipou dentro do monolito, sobre `fastmcp==3.4.7`, e funciona. A camada que **não**
shipou é a que justifica o produto: o **T6** — o selo de assurance (citação resolvível,
groundedness, id do evento na trilha) como **extensão de protocolo negociada**, no lugar do
protocolo reservado para exatamente isso.

`ServerExtension` e `add_extension` não existem no 3.4.7. Verificado por introspecção do pacote
instalado, não pela documentação:

```
fastmcp.server.extensions  → ModuleNotFoundError
FastMCP.add_extension      → AUSENTE
FastMCP.completion         → AUSENTE
fastmcp.server.sessions    → ModuleNotFoundError
```

E o 4 não entra neste venv:

```
fastmcp 4.0.0b3                    → mcp>=2.0,<3  +  httpx2>=2.5
agent-framework-core 1.14.0        → mcp>=1.24.0,<2      ← teto
agent-framework-core 1.15.0        → mcp>=1.24.0,<2      ← ainda, na mais nova publicada
agent-framework-foundry-hosting    → mcp>=1.24.0,<2
```

**O bloqueio não é o SDK do MCP.** O `mcp` 2.0.0 e 2.1.0 estão publicados e estáveis no PyPI. O
bloqueio é um teto de terceiro, sobre o qual não temos data — medido na versão mais recente que
existe no dia desta ADR.

### O fato que abre a porta

Os módulos de que o MCP precisa **já não tocam** o `agent_framework`. Medido importando cada um
num interpretador limpo e checando `sys.modules`:

| Módulo | Puxa framework de agente? |
|---|---|
| `app.shared.auth` · `app.shared.settings` | **limpo** |
| `app.modules.knowledge.public` | **limpo** |
| `app.modules.audit.public` | **limpo** |
| `app.modules.tenancy.public` | **limpo** |
| `app.modules.hitl.public` | `langchain`, `langgraph` |
| `app.modules.tickets.public` | `agent_framework` |

Isso não foi planejado — é consequência da ADR-017. As fronteiras que existiam para organizar o
código produziram, de graça, um **núcleo instalável sem framework de agente**.

Duas condições materiais também já estão satisfeitas, e foram verificadas: `apps/backend` **é
empacotável** (`[build-system]` + `[tool.hatch.build.targets.wheel] packages = ["app"]`), então
outro app pode depender dele por path; e os `apps/hosted-*` já estabelecem que este repositório
comporta mais de uma unidade de deploy — embora sejam standalone e não sirvam de precedente para
importar o monolito.

O obstáculo real, portanto, não é o import: é o **empacotamento**. `apps/backend/pyproject.toml`
declara `agent-framework` como dependência **dura**. Instalar o pacote como biblioteca puxa o
teto de volta, mesmo com o grafo de import limpo. O código não precisa; a instalação diz que
precisa.

## Decisão

**1. Nasce `apps/mcp/`** — unidade de deploy própria, sobre **FastMCP 4**, servindo o endpoint MCP.
Ele importa do monolito o que já é limpo (`knowledge`, `audit`, `tenancy`, `shared`) e **não**
importa `agent_framework`.

**2. O framework de agente vira extra do backend.** `agent-framework*`, `langchain*`, `langgraph`,
`deepagents` e `ag-ui-*` saem de `dependencies` e entram em
`[project.optional-dependencies] agents`. O backend passa a se instalar como `.[agents]`; o app do
MCP instala o pacote base sem o extra.

**3. A limpeza do núcleo vira contrato verificado, não convenção.** Um contrato `forbidden` no
`importlinter.toml` proíbe `agent_framework`, `langchain`, `langgraph` e `deepagents` dentro de
`knowledge`, `audit`, `tenancy` e `shared`.

**4. E vira também gate de instalação.** Um job de CI instala o pacote **base sem o extra**, mais
FastMCP 4, e importa `app.modules.knowledge.public`. O `import-linter` prova o grafo de import; só
a instalação prova a instalabilidade — e é a instalabilidade que quebra.

**5. A leitura migra; a escrita fica.** `search_docs` e as camadas de leitura (T5 resources/prompts,
T6 selo) vão para o app novo. `create_ticket` e o HITL continuam no monolito enquanto `tickets` e
`hitl` importarem os frameworks pesados. Essa fronteira é **declarada**, não descoberta.

## Consequências

### O que isto compra

- **T6 nativo** — a extensão de protocolo com identificador reverse-DNS, negociada por capacidade.
  É o diferencial do produto ocupando o lugar que o protocolo reserva para ele, em vez de uma ponte
  via `meta` que existia só para contornar o bloqueio.
- `UserSession`, `require_roles` de biblioteca (elimina a ponte escrita à mão em `authz.py`),
  `@mcp.completion`, cache de resposta, e `InputRequiredResult` para quando a escrita atravessar.
- Isolamento de blast radius: um upgrade de FastMCP deixa de poder derrubar o backend inteiro.

### O que isto custa, dito antes de alguém descobrir

- **Todo lugar que instala o backend passa a precisar pedir o extra:** `Dockerfile`, `compose.yaml`,
  o workflow do CI, o `scripts/gates.py`, as instruções de dev. Esquecer um faz o backend subir sem
  `agent_framework` e morrer no import — falha **alta**, não silenciosa, que é a única coisa boa
  desta classe de mudança.
- **Duas unidades de deploy** para operar, com identidade e configuração próprias.
- **O produto fica partido em leitura e escrita** até `tickets` e `hitl` serem limpos. Duas
  superfícies MCP, ou nenhuma escrita por MCP — e a escolha entre as duas é decisão de produto,
  não de engenharia.
- O `httpx` → `httpx2` do FastMCP 4 vale para o app novo, e os `except httpx.` viram código morto
  **silencioso** onde houver.

### O que torna isto seguro

O par (3) + (4). Sem eles, a separação repousaria numa propriedade que ninguém vigia — e um
`from agent_framework import ...` acrescentado ao `knowledge` amanhã quebraria a instalação do
outro app sem nada ficar vermelho. É a mesma classe de falha que a série T0–T2 passou consertando:
gate verde que não prova nada. **Sem os dois gates, esta ADR não deve ser executada.**

## Alternativas consideradas

**Fronteira HTTP em vez de import.** O app do MCP não importaria nada e chamaria o backend por HTTP
com o token do chamador. Zero acoplamento de pacote, mas exige um endpoint de busca que não existe
(os endpoints de domínio são SSE de chat) e acrescenta um salto de rede no caminho mais sensível a
identidade do produto. Rejeitada por custo desproporcional ao ganho.

**Duplicar os módulos no app novo.** Rejeitada pela doutrina do próprio repositório: duas listas da
mesma coisa divergem no primeiro item novo, e a divergência não dá erro — aqui, faria as duas
superfícies discordarem sobre **o que o usuário pode ver**.

**Esperar o `agent-framework` subir o teto.** Sem data, e medido como ainda travado na versão mais
nova publicada. Esperar é uma decisão válida; esperar sem prazo, tratando como se tivesse, não é.

**Ficar no FastMCP 3 indefinidamente.** É a opção de menor custo hoje e perde o T6 nativo, que é a
única parte do MCP que o mercado não tem. Rejeitada por isso.

## Gatilho de reavaliação

**Se o `agent-framework` publicar uma versão com `mcp<3`**, a razão de VERSÃO desta ADR desaparece
— o FastMCP 4 passaria a caber no monolito. As razões de **isolamento** e **blast radius**
sobrevivem, mas não são as que motivaram a decisão. Nesse dia, reavaliar explicitamente em vez de
herdar: manter o app separado por inércia seria pagar duas unidades de deploy por um problema que
deixou de existir.

Verificação: `pip index versions agent-framework-core` e conferir o `Requires-Dist: mcp`.
