# docbundle vs. OKF v0.2 — medição

**Data:** 2026-08-27 · **Pedido:** medir o `docbundle.schema.json` contra a spec do OKF e dizer
o tamanho da lacuna. **Nada foi alterado.**

**Fontes lidas:**
- `apps/backend/app/modules/knowledge/internal/docbundle.schema.json` (13 campos de topo)
- `apps/backend/app/modules/knowledge/internal/ingest_docbundles.py:227-255` (leitor)
- `apps/backend/app/modules/knowledge/internal/wiki_builder.py:395-416` (escritor)
- `apps/backend/eval/wiki_freshness_test.py:137-140` (segundo leitor)
- `apps/backend/eval/docbundle_contract_test.py` (o gate de contrato)
- OKF v0.2 SPEC.md, `GoogleCloudPlatform/knowledge-catalog` (1006 linhas, lida por inteiro)

---

## 1. A lacuna, campo a campo

Dos **13 campos de topo** do nosso manifest:

**OKF cobre nativamente — 5**

| nosso | OKF | observação |
|---|---|---|
| `title` | `title` | idêntico |
| `source: {type, ref, commit}` | `sources: [{id, resource, title, author, last_modified}]` | OKF é **lista** e mais rico |
| `model` | `generated.by` (ator, §7) | OKF estrutura o ator; nós guardamos string livre |
| `generatedAt` | `generated.at` | idêntico em semântica, ISO 8601 com offset |
| `origin: "gerado"` | presença de `generated` | OKF infere do campo, não declara |

**OKF não tem equivalente — 8** (viram chave livre de produtor, §4.1 "Extensions")

`key`, `language`, `kind`, `component`, `componentVersion`, `releaseVersion`, `pages`, `groups`

**OKF tem e nós não — 7**

`type` (**obrigatório**), `status`, `stale_after`, `verified`, `tags`, `resource`, `description`

---

## 2. Três bloqueios, em ordem de peso

### 2.1 O docbundle não é nosso para trocar

O `$comment` do schema:

> "GERADO de `apps/agent/src/services/docbundle.py` **no projeto de origem** — não edite à mão…
> Cópias em outros projetos devem ser idênticas byte a byte."

`docbundle_contract_test` existe justamente porque a divergência já aconteceu uma vez (o ingest
passou a ler `groups`, o produtor não tinha o campo, e ninguém percebeu). **Adotar OKF aqui é
mudar unilateralmente um contrato entre repositórios** — decisão que não é deste repo.

**Achado colateral, e ele é real:** o check (0), que compara byte a byte com o produtor, depende
de `DOCBUNDLE_SCHEMA_REF` apontar para um checkout local. Essa variável **não é definida em lugar
nenhum** do repo nem do CI — grep em tudo devolve só as três menções que a documentam. Ou seja: a
identidade byte a byte com o produtor está **afirmada em prosa e nunca verificada**. O gate
reporta como *skipped* (não passa em silêncio, o que está certo), mas na prática ninguém sabe se
já divergimos. Isso não autoriza quebrar o contrato — significa que não sabemos o estado dele.

### 2.2 OKF não tem manifest — e essa é a diferença estrutural

OKF é "um diretório de markdown com frontmatter YAML". **Não existe documento de metadados de
bundle.** Todo metadado é por conceito, no frontmatter de cada `.md`. O `index.md` é listagem
para *progressive disclosure*, explicitamente sem frontmatter — com uma única exceção, `okf_version`
na raiz, que declara a versão **do formato**, não do conteúdo.

Nosso `manifest.json` existe para carregar identidade, versão e ACL **do bundle inteiro**.
Traduzir isso para OKF tem duas saídas, ambas ruins:

- replicar `component`/`componentVersion`/`groups` no frontmatter de **cada página** — 19 cópias
  do mesmo dado, que é a divergência silenciosa que este projeto mais teme; ou
- inventar uma extensão de bundle — que é o formato nosso de volta, com outro nome.

### 2.3 OKF recusa controle de acesso por desenho

Literal, §5.3: *"Trust tiers are advisory signals, **not access control**."* Grep por
`access control|permission|acl|authoriz|entitle|visibility|audience` nas 1006 linhas devolve
**essa única ocorrência, que é a negação**.

Nosso `groups` é a Regra #6 — controle de acesso é DADO, herdado da fonte, fail-closed, com
`null ≠ []`. É o campo mais importante do manifest e **continua sendo extensão nossa em qualquer
cenário de adoção**.

---

## 3. O que o OKF tem que nós não temos — o achado que vale

Independente de adotar o formato, três campos descrevem coisas que nós hoje **calculamos** ou
**não temos**:

- **`stale_after`** — instante absoluto de obsolescência, declarado. Nós temos o
  `wiki_freshness_test`, que *deriva* frescor comparando `generatedAt` com o último commit que
  tocou a área. Derivar funciona; declarar sobrevive a mudança de heurística.
- **`verified: [{by, at}]`** — separa quem **escreveu** de quem **confirmou**, com múltiplas
  confirmações independentes (humano + processo). Nós temos `origin: "gerado"` e mais nada. Isto
  é exatamente o vocabulário que falta ao nosso `wiki_fidelity`/Claims.
- **`status: draft|stable|deprecated`** — hoje inferimos "corrente" por poda de prateleira no
  workflow.

---

## 4. Veredito

**A MÁXIMA MAIOR não se aplica aqui, e o motivo é preciso:** OKF não é capacidade da Microsoft
nem infraestrutura que substitua código nosso — é um **formato de intercâmbio** do Google Cloud,
sem runtime, sem SDK, sem serviço. A máxima manda não reimplementar capacidade de plataforma;
ela não manda trocar um contrato de dados vigente por outro equivalente.

**Tamanho da lacuna:** 5 de 13 campos mapeiam; 8 viram extensão; o manifest inteiro não tem
lugar na spec; e o campo que mais importa (`groups`) é explicitamente fora de escopo do OKF.
**Não é um "ser OKF" — é reescrever o formato e quebrar um contrato cross-repo para ganhar
compatibilidade com um ecossistema que hoje não nos consome.**

**Recomendação — não adotar o formato; roubar três campos.** `stale_after`, `verified` e
`status` resolvem lacunas reais nossas, cabem como campos novos e opcionais no docbundle
(compatíveis para trás: ausência tem significado), e **exigem acordo com o projeto produtor** —
que é o caminho certo de qualquer forma, e é onde a conversa deveria começar.

**Antes de qualquer coisa:** definir `DOCBUNDLE_SCHEMA_REF` no CI, ou assumir por escrito que a
cópia não é verificada. Discutir mudar um contrato cujo estado atual ninguém mede é discutir no
escuro.
