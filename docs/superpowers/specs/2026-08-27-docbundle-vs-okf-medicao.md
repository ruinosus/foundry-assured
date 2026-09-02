# docbundle vs. OKF v0.2 — medição

**Data:** 2026-08-27 · **Pedido:** medir o `docbundle.schema.json` contra a spec do OKF e dizer
o tamanho da lacuna. **Nada foi alterado.**

**Fontes lidas:**
- `apps/backend/app/modules/knowledge/internal/docbundle.schema.json` (13 campos de topo)
- `apps/backend/app/modules/knowledge/internal/ingest_docbundles.py:227-255` (leitor)
- `apps/backend/app/modules/knowledge/internal/wiki_builder.py:395-416` (escritor)
- `apps/backend/eval/wiki_freshness_test.py:137-140` (segundo leitor)
- `apps/backend/eval/docbundle_contract_test.py` (o gate de contrato)
- OKF v0.2 SPEC.md, `GoogleCloudPlatform/open-knowledge-format@ad30107c31c06aec8a7d5636e0d1058118604e6f` (1006 linhas, lida por inteiro)

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

### 2.2 OKF não especifica manifest — e isso NÃO é bloqueio

**Correção de uma afirmação anterior desta medição.** A primeira redação tratou "OKF não tem
manifest" como impedimento. Está errado: não especificar ≠ proibir.

§11 (Conformance) constrange **apenas arquivos `.md`**: "Every non-reserved `.md` file in the
tree contains a parseable YAML frontmatter block". Busca por `json|non-markdown|other files|
sidecar` nas 1006 linhas da spec devolve **zero ocorrências**. Um `manifest.json` ao lado das
páginas é invisível para o OKF e não quebra conformidade.

O que resta é custo real, e é pequeno: nossas páginas hoje **não têm frontmatter nenhum** (o
bundle é `pages/page-N.md` com markdown puro). Conformidade exige um bloco com `type` não-vazio
por página.

### 2.3 OKF não recusa controle de acesso — eu li um aviso como proibição

**Correção da afirmação mais errada desta medição.** §5.3 diz "trust tiers are advisory signals,
not access control". Isso é um aviso contra **usar trust tier como ACL** — não uma proibição de
carregar metadado de acesso.

O oposto é o que a spec diz. §4.1: "Producers MAY include **any** additional keys." §11:
consumidores "MUST NOT reject a bundle because of… unknown additional frontmatter keys". Extensão
é comportamento **abençoado**, não tolerado.

Ou seja: `groups` (Regra #6) cabe no OKF como chave de produtor, e o consumidor conformante é
obrigado a preservá-la. O bloqueio que eu descrevi não existe.

---

## 2.4 O que sobra de bloqueio: um só

Apenas §2.1 — o contrato cross-repo com o projeto produtor. E ele não é "nunca": é "precisa de
acordo com o produtor", que é o caminho certo de qualquer forma.

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

**A MÁXIMA MAIOR se aplica, sim — e mais forte do que eu supus.** OKF é **formato**, não runtime:
sem SDK, sem serviço, sem pin de versão. Se o OKF morrer amanhã, sobra markdown com frontmatter
YAML — o custo de errar é perto de zero. É justamente onde o ônus da prova para escrever formato
próprio deveria ser **maior**, não menor, do que para capacidade de plataforma.

**Tamanho real da lacuna, revisado:** os três "bloqueios" viram um. Adotar OKF como formato de
página e manter o `manifest.json` ao lado é **legal pela spec** e custa: frontmatter por página
(que o OpenWiki já escreve — 19 de 20 páginas em `openwiki/` já têm) mais acordo com o produtor
para campos novos no manifest.

**O achado que muda a conta:** `adapt_openwiki.py:22` **descarta** o frontmatter OKF que já chega
("Front matter is stripped"), levantando só o `title`. A justificativa está meio certa — YAML não
pode entrar no corpus de retrieval — mas tirar do **corpo** não obriga a **jogar fora**: dá para
levantar para o manifest, exatamente como o `title` já é. Os campos que esta medição recomendava
"roubar do OKF" **já chegam no nosso pipeline e são descartados**.

**Recomendação revisada:** OKF como formato das páginas + `manifest.json` por cima para o que o
OKF não tem lugar (`groups`, `component`, `componentVersion`, ordenação). Primeiro passo, e ele
não toca o contrato do docbundle: **parar de descartar** `generated`/`verified`/`sources`/`tags`
e levantá-los para o manifest.

**Antes de qualquer coisa:** definir `DOCBUNDLE_SCHEMA_REF` no CI, ou assumir por escrito que a
cópia não é verificada. Discutir mudar um contrato cujo estado atual ninguém mede é discutir no
escuro.
