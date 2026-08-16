# `knowledge/` — o que alimenta as bases de conhecimento

Tudo que vira **base de conhecimento** de um agente mora aqui. Código fica em `apps/`,
documentação para humanos fica em `docs/`, e conteúdo indexável fica neste diretório.

Isto existia espalhado em três lugares e ninguém achava: o corpus estava seis níveis dentro do
pacote Python (`apps/backend/app/modules/knowledge/corpus/`), o bundle estava em `docs/wiki/`
misturado com documentação escrita à mão, e a wiki gerada em `openwiki/`. Três nomes que não
diziam o papel de nada.

```
knowledge/
  corpus/                              13 runbooks → KB do helpdesk
  wiki-bundle/<componente>/<versão>/    bundle indexável → KB do selfwiki
openwiki/                              (raiz) a wiki gerada, fonte do bundle acima
```

## `corpus/` — o cenário do helpdesk

Treze runbooks de suporte de engenharia, **escritos à mão e fictícios**: AKS compartilhado, VPN
corporativa, recuperação de 2FA. Não descrevem este projeto — descrevem a empresa imaginária
onde o agente de helpdesk trabalha.

Ele precisa ser **estável**, e isso é um requisito, não um acaso: é o chão firme do harness de
eval. `eval/datasets/golden.jsonl` casa pergunta com runbook por título exato, e
`eval/assertions.py` verifica que a fonte citada existe de fato. Três gates dependem disso — se
o conteúdo mudasse sozinho, eles quebrariam a cada alteração.

Ingestão: `uv run python -m app.modules.knowledge.internal.ingest`

## `wiki-bundle/` — a documentação deste repositório

Gerada pela IA a partir do código real, e o que ela prova é o oposto do corpus: não "citou
certo", e sim **"não inventou"**. O gate de fidelidade exige que ao menos 80%
(`eval/assurance.yaml`) das citações resolvam para um arquivo que existe.

**Não edite estes arquivos à mão — regenere.** O caminho completo:

```
openwiki code --update     →  openwiki/**/*.md      (formato da ferramenta, navegável)
adapt_openwiki             →  knowledge/wiki-bundle/  (formato de ingestão)
wiki_fidelity_test         →  ≥ 80% ou o bundle não passa
ingest_docbundles --selfwiki → a base de conhecimento
```

A adaptação **não é uma cópia**: ela remove o front matter YAML e achata os links entre páginas
da wiki, preservando os links para código-fonte (331 no bundle atual, com SHA e linhas). Isso é
deliberado e medido — sem achatar, a fidelidade marcava 99,3% em vez dos 81,0% reais, e a
diferença eram 28 citações-fantasma que resolviam só porque os próprios arquivos da wiki
estavam na árvore escaneada.

### Um bundle na prateleira é um bundle na base

`collect_pages` varre `wiki-bundle/**` inteiro e envia o que encontrar. Não há filtro por data
nem por versão. Foi assim que quatro bundles de um modelo de geração aposentado continuaram
sendo servidos como atuais — inclusive três que **passavam** em fidelidade e ainda assim diziam
"Next.js 15", "ADRs 001–011" e "4 domínios".

A lição está no gate: fidelidade pergunta se a citação **resolve**, não se a frase em volta
ainda é **verdade**. `eval/wiki_shelf_test.py` agora checa as duas coisas, em cada push.

### Remover o arquivo não limpa a base

Apagar um bundio daqui tira ele do repositório, e só. Os blobs e os chunks já indexados
continuam onde estão até alguém **reingerir** — aí `_prune_stale_blobs` e `purge_orphans`
reconciliam o container e o índice.

## Os gates

```bash
cd apps/backend
uv run python -m eval.wiki_shelf_test       # todo bundle commitado: modelo atual + fiel
uv run python -m eval.wiki_freshness_test   # o bundle é mais novo que o código que descreve?
uv run python -m eval.docbundle_contract_test  # o manifesto respeita o schema do produtor
```
