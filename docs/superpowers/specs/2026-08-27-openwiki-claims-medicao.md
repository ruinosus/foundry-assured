# Medição — OpenWiki "Grounded Claims" (0.4.3) vs. a nossa exceção calibrada

**Data:** 2026-08-27 · **Método:** ADR-016 *Phase A — read the tool, spend nothing*
(`docs/adr/ADR-016-openwiki-closes-the-freshness-loop.md:171`)
**Instalado e lido:** `openwiki@0.4.3` (npm, MIT). O pacote publica só `dist/` (JS compilado, com
JSDoc preservado). Todas as referências abaixo são **`node_modules/openwiki/dist/<arquivo>:<linha>`**
da versão 0.4.3; as do nosso lado são do worktree em `feat/auditoria-dentro-da-aplicacao`
(HEAD `96fe57f`).

Nada foi commitado. Nenhuma chamada de modelo foi feita. Nenhum código de produto foi alterado.

---

## 1. Como o Claims funciona, lido no código

### 1.1 A representação da evidência

Uma `Claim` é `{ id, statement, evidence[] }` e cada `Evidence` é **`{ resource, version }`**
(`claims/core/types.d.ts:4-30`). Só isso é persistido — não há trecho de código guardado.

O `resource` é uma URI canônica `repo://<caminho-relativo>[#Lx-Ly]`
(`claims/evidence/repository/resource.js:6`, parser em `:39-93`, faixa em `:104-118`).
`#L8` é aceito na entrada e canonizado para `#L8-L8` (`resource.js:96-98`).

O `version` é **opaco** e tem duas formas, escolhidas pela presença ou ausência da faixa
(`claims/evidence/repository/resolver.js:85-94`):

| forma | quando | conteúdo |
|---|---|---|
| `repo-file-v1:sha256:<hex>` | evidência **de arquivo inteiro** (sem `#L`) | SHA-256 do arquivo inteiro (`resolver.js:422-430`, `:452-454`) |
| `repo-lines-v1:sha256:<hex>:<base64url>` | evidência **de faixa de linhas** | SHA-256 **só do trecho selecionado** + metadado de relocação (`resolver.js:14`, `:333-349`) |

**Resposta direta a "o hash é do arquivo inteiro ou do trecho": os dois, e a escolha é do autor
da claim.** Sem `#L`, hash do arquivo inteiro; com `#L`, hash do trecho — e o arquivo inteiro
deixa de ser observado.

### 1.2 O "relocation metadata"

É o `<base64url>` no fim da versão de faixa. São exatamente 7 campos
(`resolver.js:18`, `:336-347`, validados em `:387-400`):

```
selectedLineCount            nº de linhas do trecho
firstSelectedLineHash        sha256 da 1ª linha do trecho
lastSelectedLineHash         sha256 da última linha do trecho
precedingContextLineCount    0..3   (RANGE_CONTEXT_LINE_COUNT = 3, resolver.js:10)
precedingContextHash         sha256 das até-3 linhas ANTES do trecho
followingContextLineCount    0..3
followingContextHash         sha256 das até-3 linhas DEPOIS do trecho
```

Como ele acha o trecho que se moveu, em duas passadas:

1. **`locateUnchangedLineRange` (`resolver.js:213-241`)** — trecho **inalterado** que mudou de
   posição. Tenta primeiro a posição da URI; falhando, varre o arquivo inteiro procurando
   janelas de `selectedLineCount` linhas cuja 1ª e última linha batem por hash e cujo conteúdo
   completo bate com `contentHash`. **Uma única correspondência** → relocado. Havendo mais de
   uma, desempata exigindo os dois contextos exteriores (`:239-240`, `hasMatchingRangeContext`
   em `:299-314`). Ainda ambíguo → `null`.
2. **`locateChangedLineRange` (`resolver.js:250-265`)** — trecho **alterado**, achado *entre* as
   âncoras exteriores (3 linhas antes, 3 depois). Se o par de âncoras produzir mais de um span
   candidato, devolve `null` **de propósito** (`:258-260`).

### 1.3 O que conta como "stale" — e a distinção que importa

A checagem determinística é `runClaimsPreflight` (`claims/brains/code/preflight.js:12-61`).
Para cada evidência de cada claim de cada página, chama `resolver.resolve(resource, version)` e
classifica (`preflight.js:28-51`):

| resultado do resolver | classificação | significado |
|---|---|---|
| `null` | **`unresolved`** | arquivo sumiu (ENOENT, `resolver.js:77`), não é arquivo regular (`:64-66`), ou a faixa não pôde ser localizada com segurança |
| versão **diferente** da persistida | **`stale`** | o alvo mudou |
| versão **igual** | nenhum | intacto |

`stale` **não** é "a faixa deslocou". Deslocamento puro não gera stale: o relocador devolve a
**mesma versão** (`resolver.js:141-150` devolve `previousVersion` literalmente). Medido — §3.2.

`unresolved` cobre também um caso não óbvio: faixa **deletada** com contexto intacto. A âncora
anterior e a seguinte colidem, o span fica vazio, e `locateChangedLineRange` devolve `null`.

Há ainda um terceiro sinal, mais fraco: **órfãos** — sidecar cujo `.md` sumiu
(`preflight.js:16`, limpo em `session.js:208-220`). E o `pageVersion` (hash do Markdown da
página) existe mas é **informativo em schema v1**: "Hash drift is informational in schema v1 and
does not create agent work" (`claims/brains/code/types.d.ts:28-32`).

### 1.4 O formato do sidecar em `openwiki/.claims`

`ClaimsStore` fixa `wikiDir = <root>/openwiki` e `claimsDir = <wiki>/.claims`
(`claims/brains/code/store.js:83-84`, `claims/brains/code/paths.js:6`). O caminho do sidecar é o
caminho da página **relativo a `openwiki/`, com `.json`** (`paths.js:117-120`) — a árvore de
`.claims/` espelha a do wiki. Escrita atômica (tmp + rename, `store.js:242-250`).

Schema Zod estrito (`store.js:48-55`), `schemaVersion` literal `1` (`types.d.ts:5`):

```json
{
  "schemaVersion": 1,
  "pageVersion": "sha256:<64 hex>",
  "claims": [
    { "id": "claim_<hex>", "statement": "...",
      "evidence": [ { "resource": "repo://apps/backend/app/main.py",
                      "version": "repo-file-v1:sha256:47b485a8…" } ] }
  ],
  "verification": { "by": "openwiki/0.4.3", "at": "2026-08-27T…Z" }
}
```

(o sidecar acima é **real** — gerado pelo próprio `ClaimsStore.writePage` no experimento §3.3.)

Páginas reservadas não têm sidecar: `index.md`, `log.md`, `instructions.md` (`paths.js:10-14`).

Além do sidecar, o Claims projeta duas coisas no front matter da página:
`verified: [{by, at}]` (`okf/claims-verification.js:15-32`) e `sources:` — a lista de arquivos de
evidência **reduzida a arquivo inteiro**, com id determinístico (`okf/claim-sources.js:22-43`,
`:63-66`, `:92-97`).

### 1.5 Escopo: só wiki gerada pelo OpenWiki. Confirmado no código.

Esta é a pergunta central do pedido, e a resposta é **sim, é fechado sobre o `openwiki/` do
próprio OpenWiki** — por quatro travas independentes:

1. **Diretório fixo, não configurável.** `store.js:83` monta `path.join(rootDir, "openwiki")`.
   Não há parâmetro.
2. **Caminho de página validado.** `normalizeWikiPagePath` (`paths.js:21-34`) recusa qualquer
   coisa que não comece com `/openwiki/` e termine em `.md`. `isGroundedWikiPage` (`:77-90`)
   repete a regra.
3. **Só roda em geração de repositório.** `prepareClaimsRuntime` devolve `undefined` se
   `outputMode !== "repository"` ou o comando é `chat` (`claims/brains/code/runtime.js:19-22`).
   O modo `personal` (local-wiki) **não tem Claims**.
4. **A evidência não pode apontar para documentação.** `resource.js:79-85` recusa
   `repo://openwiki/...` e `repo://.git/...` — logo o Claims não consegue fundamentar
   documentação *sobre* documentação, nem um wiki de terceiro que more dentro do repositório.

E não há porta de entrada nem por CLI nem programática:

- `openwiki --help` (rodado, 0.4.3) **não lista nenhum subcomando de claims**. Comandos: `code`,
  `personal`, `auth`, `ingest`, `cron`, `ngrok`, `visualize`, `integrations`. O preflight só roda
  dentro de `--init`/`--update` (`generation/repository-run.js:49`, `:202`, `:399`).
- O `package.json` do pacote tem **só `bin`** — sem `main`, sem `exports`. Não há API pública.
  Para rodar o preflight eu importei `openwiki/dist/claims/...` por caminho profundo (§3):
  funciona, é `dist/` privado, sem contrato de versão.

**Não confirmado — e o enunciado do pedido está desatualizado aqui:** as ferramentas
`resolve_claims` / `inspect_claims` **não existem** como ferramentas em 0.4.3. `resolveClaims` e
`inspectClaims` são métodos internos de `ClaimSession` (`session.js:77`, `:124`), chamados por
`replacePageClaims` (`generation/page-jobs.js:225-283`). A superfície voltada ao modelo é o ciclo
de página — `openwiki_begin`, `openwiki_submit_plan`, `openwiki_next_page`, `openwiki_submit_page`,
`openwiki_finish` (`integrations/mcp/server.js:9-23`, README:104) — onde o conjunto **completo**
de claims da página viaja no `submit_page`. Procurei `resolve_claims`/`inspect_claims` como
string literal em todo o `dist/`: zero ocorrências.

---

## 2. A tabela, mecanismo a mecanismo

Nosso lado: `apps/backend/app/modules/knowledge/internal/wiki_builder.py::_fidelity_report`
(`:113-150`), consumido por `apps/backend/eval/wiki_fidelity_test.py` (bundle externo) e
`apps/backend/eval/wiki_shelf_test.py:127` (prateleira inteira).

| # | Situação | Nosso `_fidelity_report` | OpenWiki Claims 0.4.3 | Quem é mais forte |
|---|---|---|---|---|
| 1 | Citação para arquivo **que nunca existiu** (alucinação de caminho) | **Detecta** — conta como não-resolvida e derruba o score (`wiki_builder.py:137-146`) | **Impede na escrita**, não detecta na leitura: `resolveEvidence` lança `Evidence does not resolve` (`claims/core/mutations.js:90-95`). Mas só para o que virou claim; prosa não coberta por claim não é olhada | Empate com escopos diferentes — ver linha 9 |
| 2 | Arquivo citado **foi apagado** | **Detecta** (idem) | **Detecta** — `unresolved` (`preflight.js:36-43`, `resolver.js:77`) | Empate |
| 3 | Arquivo **existe e mudou** | **NÃO detecta.** O teste é só de caminho: igualdade, sufixo ou basename único (`wiki_builder.py:137-141`). O conteúdo nunca é comparado | **Detecta** — `stale` por hash (`resolver.js:426`, `preflight.js:32-34`) | **Deles, decisivamente.** Confirmado no código E medido (§3.2, §3.3) |
| 4 | Arquivo **renomeado/movido** | Detecta como não-resolvido se o basename deixou de ser único; **falso sucesso** se o basename continua único em outro caminho (`wiki_builder.py:140`) | `unresolved`. Não persegue rename | Deles (menos frouxo) |
| 5 | Trecho citado **deslocou** (código inserido acima) | Irrelevante — não usamos faixa | **Tolera** e mantém a mesma versão (`resolver.js:213-241`) | Deles — é a linha que o nosso modelo não tem |
| 6 | Trecho citado **mudou por dentro** | Irrelevante | `stale` (relocado + versão nova, `resolver.js:151-154`) | Deles |
| 7 | Citação apontando para `.worktrees/` | **Detecta** e é **falha dura**, não desconto (`wiki_builder.py:134-136`; `wiki_fidelity_test.py` retorna 1) | Não tem esse conceito. Recusa `.git/` e `openwiki/` (`resource.js:79-85`) | Nosso (regra local, nascida de defeito real) |
| 8 | Bundle **gerado por outra ferramenta** (deep-wiki/Copilot, `adapt_deepwiki`) | **Funciona** — normaliza blob URL do GitHub para caminho (`wiki_builder.py:105`) e mede | **Não roda.** Exige `openwiki/` + sidecar próprio (§1.5) | Nosso |
| 9 | **Cobertura**: toda citação do texto é medida? | **Sim, por construção** — varre a prosa inteira com regex (`wiki_builder.py:98`); nada escapa por omissão | **Não.** Só o que o modelo declarou como claim é rastreado. `claims/guidance.js:13` pede completude, mas é *prompt*, não gate. O único validador de página é `agent/wiki-link-validator.js:29-45`, que checa link `.md` interno e âncora — **não** citação de fonte | Nosso |
| 10 | **Frase ao redor da citação envelheceu** ("Next.js 15" quando é 16) | Não detecta (documentado em `wiki_shelf_test.py:19-25`) | Não detecta. Um claim `stale` **sinaliza** que a frase precisa ser reconferida; quem julga é o modelo | Deles marginalmente: dá o gatilho, não o veredito |
| 11 | Roda **offline, determinístico, sem modelo, em CI** | **Sim** — é o desenho (`wiki_shelf_test.py:27`) | O preflight é determinístico, **mas** só existe dentro de um run que precisa de modelo; produzir/atualizar claims **exige modelo** (`generation/page-jobs.js:225-283`) | Nosso |
| 12 | Precisa de **estado persistido** | Não. Só páginas + árvore | **Sim** — sidecars em `openwiki/.claims/`, versionados no git | — |
| 13 | Emite um **número gateável** | Sim: `score = resolved/total`, piso `build.fidelity_min` (`wiki_builder.py:152-163`, `eval/assurance.yaml`) | Não. Emite lista de issues e um carimbo `verified:` (`okf/claims-verification.js:15-32`). Sem score, sem piso | Nosso |
| 14 | **Segurança de caminho** (symlink, escape de raiz) | Não é objetivo | Forte: `lstat` + `realpath` + contenção (`resolver.js:60-73`, `store.js:389-404`) | Deles |

---

## 3. O que rodei — determinístico, custo zero

### 3.1 `openwiki --help` (0.4.3)

Rodado. Nenhum subcomando de claims — §1.5.

### 3.2 Semântica do resolver, caso a caso

Script `e1.mjs`: repositório temporário de 10 linhas, `RepositoryEvidenceResolver` importado
direto. Saída literal:

```
whole-file, base:                              repo-file-v1:sha256:e6a8a596…
whole-file, after edit anywhere:               repo-file-v1:sha256:f40596f7…
   -> version changed (=> STALE)? true
range L3-L5, base:                             repo-lines-v1:sha256:4ad1fca8…
   content: "TARGET_A\nTARGET_B\nTARGET_C\n"
range, edit OUTSIDE range:                     same version? true
range, 5 lines inserted above (relocation):    same version? true | content: "TARGET_A\nTARGET_B\nTARGET_C\n"
range, edit INSIDE range:                      same version? false | content: "TARGET_A\nTARGET_B_CHANGED\nTARGET_C\n"
range, selected lines DELETED:                 NULL (unresolved)
file deleted:                                  NULL (unresolved)
path never existed:                            NULL (unresolved)
rejected repo://openwiki/index.md              EvidenceResourceError: Evidence cannot reference Git metadata or generated OpenWiki output
rejected repo://.git/config                    EvidenceResourceError: Evidence cannot reference Git metadata or generated OpenWiki output
rejected repo://../escape.txt                  EvidenceResourceError: Evidence path must remain inside the repository
```

Confirma, sem interpretação: hash de arquivo inteiro é **rigor máximo** (qualquer byte →
`stale`); faixa de linhas é **deliberadamente tolerante** a deslocamento e a edição fora do
trecho, e sensível a edição dentro dele.

### 3.3 A medição que interessa: mesmo corpus, dois mecanismos

Script `e2.mjs`. Desenho:

1. `git archive 8e5fef8 | tar -x` → árvore **antiga** (o commit que `openwiki/.last-update.json`
   diz documentar). `git archive HEAD` → árvore **nova**. 31 commits, **283 arquivos alterados**
   entre as duas.
2. Nas 19 páginas *grounded* do `openwiki/` da árvore antiga, extraí as citações com **a mesma
   regra do `_fidelity_report`** (mesma alternação de extensões, mesma normalização de blob URL,
   mais o achatamento de link wiki→wiki que o `adapt_openwiki.py:125-144` faz).
3. Cada citação distinta que resolve virou **um claim com evidência de arquivo inteiro**,
   versionada pelo `RepositoryEvidenceResolver` na árvore **antiga**, persistida por
   `ClaimsStore.writePage`.
4. Transplantei `openwiki/` + `.claims/` inalterados para a árvore **nova** e rodei
   `runClaimsPreflight`. Só a fonte mudou.

Resultado:

```
páginas do wiki (grounded): 19
citações extraídas:         479
recursos distintos:         106
claims escritos:            167
evidências recusadas na árvore antiga: 17 (todas repo://openwiki/**.md)

=== PREFLIGHT contra a árvore NOVA ===
claims com problema : 43 / 167  (25,7%)
  stale (arquivo existe, MUDOU) : 43
  unresolved (sumiu/não resolve): 0
  recursos distintos stale      : 17 de 106  (16,0%)

=== NOSSO _fidelity_report, mesmas páginas, mesma árvore ===
citações: 479 | resolvem: 469 | score: 97,9%
```

**Este é o número do relatório.** Sobre o mesmo corpus e a mesma deriva de 31 commits: o nosso
gate diz **97,9% fiel** e passa; o mecanismo deles marcaria **25,7% dos claims para
reconferência**, por 17 arquivos que continuam existindo e mudaram. Nenhum desses 17 aparece
para nós, porque o nosso teste é de caminho.

No bundle **realmente commitado** (`knowledge/wiki-bundle/foundry-assured/v0.20260819`) o
`_fidelity_report` devolve:

```
{'total': 676, 'resolved': 659, 'line_ranged': 0, 'worktree': 0, 'distinct': 211, 'score': 0.9748…}
```

→ `eval.wiki_shelf_test` **passa em 97,5%** (piso 80%), com o aviso de freshness (não bloqueante)
dizendo que o wiki é de 2026-08-19 e a fonte mudou em 2026-08-26.

Duas observações que caem da mesma medição:

- **`line_ranged: 0` de 676.** Nenhuma citação do nosso wiki carrega faixa de linha. Rodei o
  `e2.mjs` também com `--ranges` (converte `path:12-20` → `repo://path#L12-L20`): números
  **idênticos**, porque não há o que converter. Toda a maquinaria de relocação do OpenWiki (§1.2)
  é inerte sobre o estilo de citação que este wiki produz hoje. Ela só liga porque o prompt do
  Claims **manda** citar `repo://path#L20-L48` (`claims/guidance.js:11`).
- **As 17 evidências recusadas** são a página citando **outra página do wiki**
  (`repo://openwiki/backend/helpdesk-workflow.md` etc.). O OpenWiki recusa por política
  (`resource.js:79-85`). **Nós contamos como citação que resolve** — o arquivo existe na árvore.
  O `_flatten_internal_links` (`adapt_openwiki.py:125`) já mata o formato *link*; menções em prosa
  nua sobrevivem e inflam o score. Achado lateral desta medição, não um pedido.

### 3.4 O A/B do `.claims` sobre o nosso gate

Ver §5.2 — `delta score: 0.0`.

### 3.5 O que exigiria gastar (e não gastei)

Gerar claims **de verdade** (não sintéticos) sobre este repositório exige um run
`openwiki code --init|--update`, que exige modelo. O `.last-update.json` atual registra
`model: gpt-5.4`; o run que gerou este wiki produziu 19 páginas. **Não rodei.** Duas rotas, em
ordem de custo:

1. `openwiki integrations install claude` + `--project .` — o run usa o modelo já autenticado do
   coding agent, sem chave de provider (README:74, :100-106). Ainda consome modelo; não consome
   `OPENWIKI_API_KEY` nem budget de CI.
2. O caminho do CI atual: `OPENWIKI_PROVIDER=openai-compatible` + `vars.OPENWIKI_BASE_URL` +
   `secrets.OPENWIKI_API_KEY` (`.github/workflows/wiki-regen.yml:69-76`).

---

## 4. VEREDITO

**O Claims não é equivalente de primeira parte ao que a nossa exceção calibrada faz. Ele resolve
um problema vizinho, com escopo de entrada estritamente menor e poder de detecção estritamente
maior.**

Em três eixos:

- **Mais forte exatamente onde a frase do `CLAUDE.md` dói.** Em "arquivo existe mas mudou", eles
  detectam e nós não — confirmado no código (`resolver.js:426` + `preflight.js:32-34`) e medido
  em 43/167 claims / 17 de 106 arquivos sobre o nosso próprio corpus. Somam ainda relocação de
  faixa, contenção de symlink e uma garantia de escrita (claim com evidência inexistente **não
  pode ser criado**, `mutations.js:90-95`). Nessa dimensão específica **a nossa medição é a mais
  fraca das duas**, e a frase "não há equivalente de primeira parte" não sobrevive como está.
- **Mais fraco em cobertura.** Eles rastreiam **o que o modelo escolheu declarar**; nós medimos
  **cada caminho de arquivo que aparece no texto**. Uma página OpenWiki pode citar um arquivo
  inexistente em prosa, sem claim, e atravessar todo o pipeline — o único validador de página
  (`wiki-link-validator.js`) só olha link interno `.md`. Não há score, não há piso, não há gate;
  a ausência de claim não gera alarme algum.
- **Escopo de entrada diferente — e é aí que a exceção sobrevive.** O `_fidelity_report` recebe
  *qualquer* lista de páginas × *qualquer* árvore de arquivos: é como ele já grada bundles do
  deep-wiki/Copilot (`adapt_deepwiki`) e do OpenWiki com o mesmo código, e é o que a spec propõe
  como produto — apontar para o repositório de terceiro e medir a documentação **que já existe**.
  O Claims não faz isso, e não é questão de configuração: quatro travas independentes o prendem
  ao `openwiki/` que o próprio OpenWiki gerou, com sidecars que ele mantém, dentro de um run de
  geração dele (§1.5) — e a evidência é proibida de apontar para documentação
  (`resource.js:79-85`). Não existe `openwiki claims check`, não existe API pública; para
  reutilizá-lo tive de importar `dist/` privado.

**Conclusão prática, sem meio-termo:** a exceção calibrada sobrevive, **mas o motivo escrito hoje
no `CLAUDE.md` está errado e precisa ser trocado.** Não é mais "não há equivalente de primeira
parte" — há, para *um* dos mecanismos, e ele é melhor que o nosso. É:

> A resolubilidade de citações é nossa porque mede **documentação que não pedimos para ninguém
> gerar** — qualquer conjunto de páginas contra qualquer árvore, sem sidecar, sem estado, sem
> cooperação do produtor, com um número e um piso que barram merge. O Claims do OpenWiki é o
> mecanismo de frescor **do próprio OpenWiki sobre o próprio wiki dele**, e não atende esse perfil.

E há um caminho de encolhimento honesto, que não viola a MÁXIMA MAIOR e **não é escopo deste
relatório executar**: a detecção de "arquivo mudou" deveria sair da nossa lista de coisas a
inventar. Ou (a) adotamos o Claims para o caminho OpenWiki e paramos de deixar implícito que o
nosso score cobre isso; ou (b) se quisermos o sinal sobre bundles de qualquer origem, o que falta
no nosso lado é uma linha, não um mecanismo: `gather_source` já lê o conteúdo dos arquivos
(`wiki_builder.py:165-176`); gravar `sha256` por caminho citado no `manifest.json` na geração e
comparar na prateleira dá o item 3 da tabela sem faixa de linha e sem sidecar. **Decisão sua.**

---

## 5. OKF v0.2 — o que quebra nos nossos gates de bundle

Verificado sem alterar nenhum gate.

**O que a v0.2 muda de fato, no código 0.4.3:**

| mudança | onde | alcance |
|---|---|---|
| `okf_version: "0.2"` | `okf/index-sync.js:137` | **só no `index.md` da raiz** do bundle. Índices de subdiretório não têm front matter |
| `generated: { by, at }` substitui `timestamp` | `okf/generated-provenance.js:85` (`setGeneratedEvent` + `removeFrontmatterField(…, "timestamp")`) | front matter **de cada página conceito**, não do índice. `timestamp` segue *tolerado* na validação (`okf/frontmatter.js:3-4`) |
| `verified: [{by, at}]` | `okf/claims-verification.js:15-32` | idem, campo novo |
| `sources: [{id, resource}]` | `okf/claim-sources.js:22-43` | idem, campo novo (projeção do Claims) |
| `openwiki/.claims/**.json` | `store.js:83-84` | diretório novo dentro de `openwiki/` |

**Correção ao enunciado do pedido:** `generated: {by, at}` **não** é do índice — o índice raiz só
ganha `okf_version`. Não confirmei nenhuma escrita de `generated` em `index.md`; procurei em
`okf/index-sync.js` (único escritor de índice) e em `okf/generated-provenance.js` (que opera
sobre `listWikiConceptPaths`, e `index.md` está no `EXCLUDED_FILES` de `index-sync.js:6`).

### 5.1 `apps/backend/eval/docbundle_contract_test.py` — **não quebra, e não pode quebrar**

Rodado agora: **passa** — 4 checagens verdes + 1 skip (`DOCBUNDLE_SCHEMA_REF` ausente). Ele lê
`docbundle.schema.json`, deriva por `ast` os campos lidos/escritos em `ingest_docbundles.py`,
`wiki_freshness_test.py`, `wiki_builder.py` e `adapt_deepwiki.py`, e valida os bundles
commitados. **Nenhum desses caminhos toca o front matter OKF nem o `openwiki/`.** A v0.2 é
invisível para ele por construção.

Nota de manutenção, não efeito da v0.2: `_WRITERS` (`docbundle_contract_test.py:53-56`) lista
`wiki_builder.py` e `adapt_deepwiki.py` — **`adapt_openwiki.py` não está lá**, embora escreva um
`manifest` (`adapt_openwiki.py:183-203`). O gate que existe para impedir "um gerador local
inventar um dialeto" não vigia o gerador do caminho OpenWiki. Pré-existente e ortogonal.

### 5.2 `apps/backend/eval/wiki_shelf_test.py` — **não quebra**

Rodado agora: **passa**, `foundry-assured/v0.20260819 → 97,5%` (piso 80%).

Ele lê `manifest.json` + `pages/*.md` do bundle e `gather_source(REPO_ROOT)`. O único vetor da
v0.2 é o novo diretório `openwiki/.claims/`, que `gather_source` **enxerga** (`.json` está em
`_SOURCE_EXT` e `.claims` não está em `_IGNORE`, `wiki_builder.py:79-91`). Medi o efeito com um
A/B sobre a árvore de HEAD, com e sem os 19 sidecars:

```
SEM .claims : 785 arquivos | score 0.97485…
COM .claims : 804 arquivos | score 0.97485…
delta score : 0.0
basenames que deixaram de ser únicos: []
```

**Efeito medido: nenhum.** O risco teórico existe (um sidecar poderia tornar ambíguo um basename
antes único e derrubar uma citação nua) mas não se materializa: os 19 nomes são `<página>.json` e
nenhum colide.

`apps/backend/eval/wiki_freshness_test.py` também está coberto: `_GENERATED` já exclui `openwiki`
inteiro (`:70`), então `.claims/` não conta como "fonte mudou".

### 5.3 `adapt_openwiki.py` — **não quebra**, e testei com front matter v0.2 real

Gerei uma página v0.2 chamando os **próprios formatadores do OpenWiki 0.4.3**
(`setGeneratedEvent` + `removeFrontmatterField("timestamp")` + `setOkfSources` + `setOkfVerified`
+ `repairOkfFrontmatter`) e passei pelo nosso `_split_front_matter` / `_title_of`:

```
front matter capturado: '---\ntype: concept\ntitle: "Backend overvi' … ' 2026-08-27T10:00:00.000Z\n---\n'
linhas de front matter : 16
título extraído        : 'Backend overview'
corpo começa com       : '# Backend overview\n\nO composition root vive em apps/backend/'
sobrou YAML no corpo?  : False
```

O `_FRONT_MATTER_RE` (`adapt_openwiki.py:54`) atravessa as listas em bloco de
`sources:`/`tags:`/`verified:` sem terminar cedo (item de lista nunca produz uma linha `---`), e o
`_FM_TITLE_RE` (`:55`) não colide com os campos novos. `_ordered_pages` (`:93-122`) só varre
`*.md`, então `.claims/*.json` não entra como página. E `.last-update.json` **continua existindo
com os mesmos campos** em 0.4.3 — `updatedAt`, `command`, `gitHead`, `model`, `status`, `language`
(`agent/utils.js:114-130`, `config/constants.js:2`) — que é de onde `adapt_openwiki:186-193` tira
commit e modelo. Intacto.

### 5.4 O que a v0.2 realmente pede de nós

Nada urgente, nada quebrado. Uma coisa a **decidir**, não a corrigir:

- `adapt_openwiki.py:9` e `:22` dizem "OKF v0.1". Comentário desatualizado, não bug.
- A partir da 0.4.0 o front matter das páginas passa a carregar `sources:` (os arquivos de
  evidência) e `verified:` (o carimbo). **Nós jogamos isso fora** (`_split_front_matter`). Se um
  dia quisermos aproveitar o sinal do Claims, é por ali que ele chega — hoje é descartado antes de
  virar bundle, e o `manifest.json` não tem campo para recebê-lo (o que, pelo
  `docbundle_contract_test`, exigiria mexer no contrato vendorizado).

---

## 6. O que NÃO deu para medir, e por quê

1. **Claims reais gerados pelo OpenWiki sobre este repositório.** Exige um run
   `openwiki code --init|--update`, que exige modelo (§3.5). Todo o §3.3 usa claims **sintéticos**
   construídos a partir das citações reais do wiki — o versionamento e o preflight são os deles,
   de verdade, mas *quais* proposições virariam claim e *quais* faixas de linha o modelo
   escolheria é decisão do modelo, e isso não medi.
2. **Qualidade das claims que o modelo produziria.** Consequência de (1). `claims/guidance.js`
   descreve o padrão pretendido ("materiality test", completude sobre minimização), mas nada disso
   é verificável sem rodar.
3. **A relocação de faixa em cenário real.** Medida só no sintético do §3.2, porque nosso wiki tem
   **0 de 676** citações com faixa (§3.3). Não sei como o relocador se comporta sobre refatorações
   reais deste repositório.
4. **Comparação com a v0.4.0 exata** (release onde Claims e OKF v0.2 entraram). Li a **0.4.3**, a
   mais recente publicada. Diferenças 0.4.0→0.4.3 não foram auditadas.
5. **Os PRs #638 e #581 do upstream.** Li o pacote publicado, não o repositório
   `langchain-ai/openwiki`. O npm publica só `dist/` — sem `src/`, sem testes —, então não consegui
   ler os testes do Claims, que provavelmente respondem melhor que eu sobre casos de ambiguidade
   de relocação.
6. **`pageVersion` na prática.** O schema diz que drift do hash da página é "informational in
   schema v1" (`types.d.ts:28-32`); não encontrei nenhum consumidor que aja sobre ele. Procurei em
   `preflight.js`, `session.js` e `runtime.js`. **Não confirmado** que exista qualquer efeito hoje.

---

### Artefatos do experimento

Descartáveis, fora do repositório, em `/private/tmp/claude-501/…/scratchpad/`: `ow/e1.mjs`
(semântica do resolver), `ow/e2.mjs` (medição de corpus), `ow/e4.mjs` (gerador de página OKF
v0.2), `ab_claims.py` (A/B do `.claims`), `report_bundle.py`, e as árvores `old2/` (`8e5fef8`) e
`new2`/`new3` (HEAD).
