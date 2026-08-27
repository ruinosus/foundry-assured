# ADR-030 — O Claims do OpenWiki é melhor que o nosso num mecanismo; a exceção calibrada sobrevive por outro motivo

- **Status:** Proposed
- **Date:** 2026-08-27
- **Context:** [ADR-016](./ADR-016-openwiki-closes-the-freshness-loop.md) (adoção do OpenWiki),
  [ADR-012](./ADR-012-reuse-upstream-deep-wiki-tooling.md),
  [`docs/superpowers/specs/2026-08-16-citation-resolvability-as-a-product-design.md`](../superpowers/specs/2026-08-16-citation-resolvability-as-a-product-design.md),
  `CLAUDE.md` (MÁXIMA MAIOR e a exceção calibrada)

## Contexto

O `CLAUDE.md` diz que a camada de assurance é nossa e sobrevive à MÁXIMA MAIOR porque
**"não há equivalente de primeira parte"**, apontando para a spec de resolubilidade de citações.

Em **2026-08-20** o OpenWiki — a ferramenta que este repositório já adotou como motor de frescor
(ADR-016) — mergeou **Grounded Claims** (PR #638, publicado na 0.4.0). A descrição do PR é quase
o nosso enunciado: *"reduz alucinações, prosa factual sem suporte e envelhecimento do
conhecimento… Git ajuda a descobrir conhecimento novo; Claims ajudam a manter o existente."*

Esta ADR existe porque aquela frase do `CLAUDE.md` pode ter deixado de ser verdade.

## O que foi medido

Não em release notes: no código da `0.4.3` instalada, e contra o corpus **deste** repositório,
com a mesma deriva de 31 commits. Relatório completo em
`.superpowers/sdd/openwiki-claims-medicao.md`.

| | `_fidelity_report` (nosso) | Grounded Claims (OpenWiki 0.4.3) |
|---|---|---|
| Citação resolve para arquivo existente | sim | sim |
| **Arquivo existe mas MUDOU** | **não vê** | **detecta, SHA-256** (`resolver.js:426`, `preflight.js:32-34`) |
| Faixa de linhas | conta, não verifica | verifica, com relocação |
| Cobertura | **toda** citação da página | só o que o modelo escolheu declarar como claim |
| Score / piso de gate | sim, e barra merge | **não existe** |
| Escopo | qualquer conjunto de páginas × qualquer árvore | **só `openwiki/` gerado pelo próprio OpenWiki** |

**O número que decide.** Sobre o nosso próprio corpus: o nosso gate marca **97,9% e passa**; o
mecanismo do Claims marcaria **43 de 167 claims (25,7%) como `stale`**, por **17 de 106 arquivos
citados que continuam existindo e mudaram**. Nós não vemos nenhum deles.

**As quatro travas que o prendem em casa**, cada uma verificada no código: diretório fixo
(`store.js:83`), caminho `/openwiki/**.md` validado (`paths.js:21-34`), só executa em run de
geração (`runtime.js:19-22`), e evidência **proibida** de apontar para documentação
(`resource.js:79-85`). Não há CLI de claims nem API pública.

## Decisão

**1. A exceção calibrada sobrevive — e o motivo escrito no `CLAUDE.md` muda.**

Deixa de ser *"não há equivalente de primeira parte"*, que é falso desde 20/08. Passa a ser: o
nosso mede **qualquer conjunto de páginas contra qualquer árvore**, sem sidecar, sem estado, sem
cooperação do produtor da documentação, com **número e piso que barram merge**. O Claims mede o
que o OpenWiki gerou, com estado que o OpenWiki mantém, e não produz score.

São ferramentas para problemas diferentes. A nossa serve ao produto que a spec propõe — apontar
para o repositório de terceiro e medir a documentação que **já existe**. O Claims serve ao ciclo
de vida da wiki que a própria ferramenta escreve.

**2. "Detectar arquivo que mudou" sai da nossa lista de coisas a inventar.**

O Claims já faz, melhor, e é de primeira parte. Se algum dia quisermos essa detecção no nosso
caminho, a MÁXIMA MAIOR manda **usar o hash como eles usam**, não inventar o nosso.

**3. Nada de Claims é implementado agora.** Ele já vem ligado no upgrade para 0.4.3 e melhora a
wiki que geramos, sem código nosso. Isso é ganho de graça, e é o suficiente por ora.

## Consequências

- A frase da exceção calibrada no `CLAUDE.md` precisa ser reescrita — hoje ela justifica a coisa
  certa pelo motivo errado, e um motivo errado envelhece pior que nenhum.
- A spec de resolubilidade ganha um vizinho de primeira parte que faz parte do trabalho. Ela
  precisa dizer o que **não** faz, e apontar para cá.
- A partir da 0.4.x, `openwiki/.claims/` passa a existir no repositório.

## O que esta ADR não decide

**Se o produto proposto pela spec ainda vale.** A medição mostra que o Claims não compete com ele
(escopo diferente, quatro travas), mas "não compete hoje" não é "não vai competir". O gatilho
está abaixo.

## Gatilho de reavaliação

Reabrir **se qualquer uma** destas quatro deixar de valer:

1. o Claims ganhar CLI ou API pública (hoje a superfície é `openwiki_submit_page`);
2. deixar de exigir run de geração (`runtime.js:19-22`);
3. aceitar diretório que não seja `openwiki/` (`store.js:83`, `paths.js:21-34`);
4. passar a emitir score agregado com piso.

Se as quatro caírem, o Claims passa a fazer o que a nossa exceção faz, e aí a MÁXIMA MAIOR
manda adotar — a exceção deixa de ter fundamento e esta ADR é superseded, não emendada.

## Um defeito nosso que a comparação revelou

**17 citações do nosso wiki apontam para outras páginas do próprio wiki**, e nós as contamos como
resolvidas — inflando o score. O OpenWiki recusa esse tipo de evidência por política
(`resource.js:79-85`): evidência de código não pode ser documentação. **Eles estão certos.**
Consertado em commit próprio; o número honesto é menor que o que exibíamos.

Vale registrar o mecanismo: a nossa medição estava certa no que afirmava (o caminho resolve) e
errada no que sugeria (a afirmação tem lastro em código).
