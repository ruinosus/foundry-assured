# Escopo e prioridades da wiki

OpenWiki lê este arquivo antes de cada run (`code --init` / `code --update`). Ele é a entrada
autoral do repositório: o que a wiki cobre e sob quais regras. Não é gerado — edite à mão.

## Requisito não-negociável: citações verificáveis por máquina

Toda afirmação relevante DEVE citar a fonte como um link do GitHub neste formato exato,
incluindo o SHA do commit e o range de linhas:

```
https://github.com/ruinosus/foundry-assured/blob/<COMMIT_SHA>/<caminho/relativo/ao/repo>#L<inicio>-L<fim>
```

Use o SHA do HEAD atual — obtenha com `git rev-parse HEAD`, ou use o que vier na mensagem do run.

Exemplos válidos:

- [`app/main.py`](https://github.com/ruinosus/foundry-assured/blob/0cb3b6d10b9b8512e40ef419f76e81804e4f7cba/apps/backend/app/main.py#L35)
- [`app/services/retrieval.py`](https://github.com/ruinosus/foundry-assured/blob/0cb3b6d10b9b8512e40ef419f76e81804e4f7cba/apps/backend/app/services/retrieval.py#L48-L76)

Regras:

- Mínimo de **5 citações nesse formato** por página substantiva.
- **Nunca** cite um arquivo que você não inspecionou.
- **Nunca** cite caminhos dentro de `.worktrees` ou de diretórios temporários.
- Prefira range de linhas a link de arquivo inteiro.
- **Não use caminho relativo** (`../../apps/backend/...`) como citação.

### Por que isso importa aqui, e não é preferência de estilo

Um gate automatizado (`apps/backend/eval/wiki_fidelity_test.py`) pontua cada bundle pela fração
de citações que resolvem para um arquivo-fonte real, e **recusa o ingest abaixo de 80%**
(`build.fidelity_min` em `apps/backend/eval/assurance.yaml`). O bundle vai para uma base de
conhecimento que responde perguntas de usuários — a citação é o que torna a resposta auditável.

Duas coisas medidas neste repositório, para você não repetir:

1. **Caminho relativo passa no gate e mesmo assim é ruim.** Ele resolve por sufixo, então pontua;
   mas `../../apps/backend/...` a partir de `knowledge/wiki-bundle/<comp>/<versão>/pages/` não leva a lugar
   nenhum quando renderizado, e perde o range de linha. Um run sem este arquivo produziu 58
   citações relativas e **zero** blob URLs, num repositório cujo bundle anterior tinha 244.
2. **Link entre páginas da wiki não é citação.** O gate lê qualquer token `algo.md` como citação
   de arquivo. Links de navegação entre páginas inflaram uma medição de 84% para 99% sem nenhum
   ganho real de qualidade. O adaptador remove esses links, mas não os gere gratuitamente.

## Escopo

**O repositório inteiro, num único wiki.** Backend (`apps/backend`), frontend (`apps/frontend`),
infraestrutura (`infra/`), os hosted agents (`apps/hosted-*`), scripts de operação (`scripts/`) e
os testes de ponta a ponta (`e2e/`). Não existe recorte por área.

Isso é decisão registrada — [ADR-016](../docs/adr/ADR-016-openwiki-closes-the-freshness-loop.md),
emenda de 2026-08-15. O OpenWiki mantém **um** `openwiki/` por repositório, enquanto os bundles
eram por área; a segunda área a rodar teria feito `--update` numa wiki sobre outra área, com o
gerador restrito justamente aos arquivos que essa wiki não descreve. Um wiki, um bundle
(`foundry-assured`), e o descasamento some.

Um bundle que promete cobrir o repositório e descreve só `apps/backend` está **errado**, mesmo que
cada frase esteja correta e todas as citações resolvam — foi exatamente o que aconteceu quando esta
seção ainda pedia recorte por área: 12 páginas, 99% de fidelidade, 387 citações, todas apontando
para o mesmo diretório. O gate mede citação, não cobertura.

## Prioridades de conteúdo

- Explique **por que** o código é assim quando a fonte revela a intenção (comentários, ADRs em
  `docs/adr/`), não só o que ele faz.
- Nomeie os pontos de extensão: onde alguém adiciona um domínio, um agente, um gate.
- Registre invariantes e ordem de ciclo de vida — o que quebra se for feito fora de ordem.
- Não duplique o `README.md` nem as ADRs; referencie e siga em frente.
