# PROTÓTIPO — build-emit ("Terraform") adoption no foundry

> Status: **spike / protótipo — avaliar**. Território isolado (`spike/emit-adoption/`).
> **Não toca produção** (nada nos shims `*prompts*.py`, nem no `pyproject.toml`).
> Story: `s-foundry-emit-prototype` (feature `f-dna-adoption`, board `.dna/foundry-dev`).

Este spike prova, no consumidor real (o foundry-assured), o **modelo Terraform**:
autora em DNA → **emite o artefato nativo do runtime em build-time** (`dna emit`,
dna-cli v0.7.0) → o runtime carrega o **nativo** — não o DNA.

---

## Os dois modelos, lado a lado

### Modelo A — runtime-compose (o que o foundry faz HOJE)

```
authoring          deploy                         runtime (processo do backend)
─────────          ──────                         ─────────────────────────────
.dna/helpdesk  ──► COPY .dna/ + dna-sdk no img ──► import app.agents.prompts
(Soul +                                            └► dna.load_prompts("helpdesk")
 Guardrails +                                          └► COMPÕE o prompt agora
 instruction)                                             (Soul+Guardrail+instr)
                                                       └► CONCIERGE_GROUNDED_INSTRUCTIONS
```

- O **scope DNA inteiro** (`apps/backend/.dna/helpdesk/`) viaja no deploy.
- O **dna-sdk** é dependência de **runtime** (`load_prompts` roda no boot do backend).
- A composição (Soul + Guardrails wired → string única) acontece **no processo**,
  a cada boot. Fonte: `apps/backend/app/agents/prompts.py` (ADR-013).

### Modelo B — build-emit / Terraform (o que este spike prova)

```
authoring          BUILD-TIME (dna emit)               runtime (processo do backend)
─────────          ─────────────────────               ─────────────────────────────
.dna/helpdesk  ──► dna emit concierge-grounded     ──► AgentFactory
(Soul +               --target agent-framework          .create_agent_from_yaml_path(
 Guardrails +         --out concierge.agent.yaml            "concierge.agent.yaml")
 instruction)      └► PromptAgent NATIVO             └► Agent vivo (agent_framework)
                      (instructions já compostas)        SEM importar dna-sdk
```

- Só o **YAML nativo** (`concierge.agent.yaml`) viaja — não o scope DNA.
- O **dna-sdk sai do runtime**: quem carrega é o `agent_framework_declarative.AgentFactory`
  que o foundry **já usa**. `dna emit` é ferramenta de **build**, como `terraform plan/apply`.
- A composição já foi **congelada** no artefato em build-time.

---

## O que rodou (saída real)

Emissão (a partir do `.dna/helpdesk` que já existe):

```
$ DNA_BASE_DIR=apps/backend/.dna \
  dna emit concierge-grounded --target agent-framework --scope helpdesk \
    --out spike/emit-adoption/concierge.agent.yaml
Emitted concierge-grounded → agent-framework: spike/emit-adoption/concierge.agent.yaml
```

Artefato nativo emitido (`concierge.agent.yaml`) — um **PromptAgent** do
agent-framework, com a composição DNA (Soul `concierge` + Guardrail
`grounded-citation` + o delta `instruction`) **achatada** em `instructions`:

```yaml
kind: Prompt
name: ConciergeGrounded
description: Helpdesk Concierge, grounded variant — cites the runbook KB, never invents
instructions: 'You are the Helpdesk Concierge, an internal engineering support assistant...
  ...## Guardrail: grounded-citation (error) ... never invent runbooks, sources, or steps.'
```

Demo (`demo.py`) — prova a cadeia **byte-equal** transitiva, cada elo sob o venv
que tem a capability:

```
# RUNTIME link — backend venv (tem agent_framework, NÃO precisa de dna-sdk)
$ apps/backend/.venv/bin/python spike/emit-adoption/demo.py
[2] Loaded via agent_framework_declarative.AgentFactory
    -> live object: agent_framework._agents.Agent
    -> agent.name = 'ConciergeGrounded'
[3] BYTE-EQUAL GATE — runtime link  (live Agent  ==  emitted YAML)
    -> PASS ✅  (504 chars)

# BUILD link — dna venv (tem dna-sdk 0.7 / load_prompts)
$ DNA_BASE_DIR=apps/backend/.dna .venv-dna/bin/python spike/emit-adoption/demo.py
[byte-equal] BUILD link  (emitted YAML  ==  dna.load_prompts)
    -> PASS ✅  (504 chars)
```

Cadeia provada:  `dna.load_prompts`  ==  `concierge.agent.yaml`  ==  **`Agent` vivo do agent-framework**
— e o elo de runtime **não importou dna-sdk**.

### Nota sobre .NET / Azure (gate honesto)

O PromptAgent emitido **não tem bloco `model:`** (o agent DNA deixa o modelo
unbound — default do Genome). Por isso o `AgentFactory` usa um **chat client
injetado** e **nunca** resolve provider Foundry/Azure nem dispara o runtime .NET.
O demo injeta um stub `SupportsChatGetResponse` e o `Agent` constrói **100%
offline** — o que provamos é o **carregamento do artefato + fidelidade do prompt**,
não a chamada ao modelo. (Import do `agent_framework` cospe uns avisos de .NET 8
via `clr_loader`, mas eles são auto-corrigidos e inofensivos — o Agent constrói.)
Para o caminho real com `FoundryChatClient`, emita com `--model` e troque o stub
por credencial Azure (aí sim pode pedir `DOTNET_ROLL_FORWARD=Major`).

---

## Trade-offs honestos

| Eixo | runtime-compose (hoje) | build-emit (Terraform) |
|---|---|---|
| **dna-sdk no runtime** | **sim** — dep de runtime, roda no boot | **não** — só ferramenta de build |
| **O que viaja no deploy** | scope `.dna/` inteiro + dna-sdk | só o `*.agent.yaml` nativo |
| **Tamanho/superfície da imagem** | maior (sdk + scope + deps) | menor (um YAML) |
| **Empacotamento** (a crítica do dono) | precisa do `COPY .dna/` + `parents[2]` | **elimina** — nada de scope no runtime |
| **Composição (Soul/Guardrail)** | **dinâmica**, a cada boot | **congelada** no emit (estática) |
| **Tenant overlay / no-deploy** | **sim** — troca o scope, sem redeploy | **não** — reemitir + redeploy p/ mudar |
| **Eval-as-contract (EvalCases)** | vive junto do scope | fica no authoring; não viaja no artefato |
| **Fonte da verdade em produção** | o scope DNA | o artefato emitido (derivado) |
| **Auditoria "o que está rodando?"** | precisa compor mentalmente | o YAML é o que roda, literal |

O `de-para` que o próprio `dna emit` reporta (eixos DNA sem slot no target):

- **composition structure** — Soul reuse + Guardrails wired achatam numa
  `instructions` única (não há slot `soul:`/`guardrails:` num PromptAgent).
- **tenant overlay** — persona per-tenant sem fork não tem campo no PromptAgent.
- **eval-as-contract** — invariantes de prompt (EvalCases) não têm slot.
- **model unbound** — sem `--model`/`spec.model`/`default_llm`, sai sem `model:`.

Ou seja: build-emit **troca dinamismo por simplicidade de runtime**. O artefato
é um **snapshot** — perde exatamente os eixos que são "authoring-time" no DNA.

---

## Conexão com a crítica do dono (empacotamento Docker)

O dono criticou o **gap de empacotamento**: hoje o backend precisa levar o
scope `.dna/` para dentro da imagem — o `Dockerfile` faz `COPY .dna/` e o
`prompts.py` resolve o diretório com `Path(__file__).resolve().parents[2] / ".dna"`
(o famoso `parents[2]` frágil, mais o mount Azure Files `/mnt/dna` do ADR-014).
É acoplamento de **artefato de authoring** (o scope DNA) ao **runtime**.

**Build-emit elimina isso na raiz:** no modelo Terraform o runtime consome
**só o `concierge.agent.yaml` nativo**. Não há `.dna/` na imagem, não há
`parents[2]`, não há dna-sdk no `requirements`, não há mount de scope. O
`dna emit` roda no **pipeline de build** (como `terraform apply`) e o que
chega em produção é o artefato nativo — que é justamente o que o
`agent_framework` sabe carregar sozinho. O gap de empacotamento **deixa de
existir** porque o que se empacota passa a ser um artefato de primeira classe
do próprio runtime.

---

## Recomendação (honesta)

**Híbrido, com o eixo sendo "isto precisa mudar sem redeploy?".**

- **build-emit** para os agentes cuja persona é **estável** e cujo maior valor é
  **runtime enxuto / imagem limpa / auditabilidade** — tipicamente os agentes de
  produto core (o concierge grounded/ungrounded, triage/retrieve/resolve). Ganha
  a imagem menor e **mata o gap de empacotamento** que o dono apontou.
- **runtime-compose** onde o **no-deploy dinâmico** e o **tenant overlay** são o
  produto — trocar prompt por tenant sem redeploy, A/B de persona, hotfix de
  guardrail em produção via publish de scope (o valor do ADR-014 / `/mnt/dna`).

Na prática: **emitir no build por padrão** (o default vira "Terraform": o
pipeline roda `dna emit` e versiona os `*.agent.yaml`), e **manter o caminho
`load_prompts` só nos scopes/tenants que precisam de override dinâmico**. O DNA
continua a **fonte de autoria única** nos dois casos — muda só *quando* a
composição é resolvida (build-time vs boot-time). É exatamente a promessa
Terraform: uma linguagem declarativa de autoria, um artefato nativo emitido, o
runtime consome o nativo.

---

## Arquivos

- `concierge.agent.yaml` — o PromptAgent nativo emitido (`dna emit`).
- `demo.py` — carrega o nativo via `AgentFactory` e prova a cadeia byte-equal.
- `README.md` — este writeup.
- `contrast.html` — versão visual do contraste (para publicar/compartilhar).
