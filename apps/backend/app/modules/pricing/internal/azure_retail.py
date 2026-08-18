"""O preço por token vem da Azure, não de uma tabela nossa.

POR QUE ISTO EXISTE. `shared/telemetry/cost.py` mantinha à mão uma tabela de USD por 1M tokens,
e o cabeçalho dela já admitia ser estimativa. O problema medido não é a tabela estar velha — é
que ela **não pode** estar certa para um modelo que não lista, e mesmo assim respondia com
confiança. O casamento por prefixo mais longo levava `gpt-5-pro` a casar com a linha de `gpt-5`
(subestimando o custo em 12×) e `gpt-4.1-nano` a casar com `gpt-4.1` (superestimando em 20×).
Nenhum dos dois chegava ao `DEFAULT_PRICE` "conservador": variante nova casa antes, e erra calada.

A Azure publica os preços numa API **pública e não autenticada** — `prices.azure.com` — e é dela
que o número passa a vir. MÁXIMA MAIOR aplicada literalmente: não há dado aberto de terceiro a
adotar, porque a fonte de primeira parte já existe.

DUAS ARMADILHAS, as duas medidas contra o serviço real antes deste arquivo existir:

  1. o serviço se chama **`Foundry Models`**. Filtrar por "Cognitive Services" — o nome anterior —
     devolve zero itens, sem erro. Uma lista vazia aqui pareceria "modelo sem preço".
  2. a grafia dos meters é INCONSISTENTE: `gpt-5-codex-inp-glbl Tokens` usa hífens,
     `gpt 5 pro inp glbl Tokens` usa espaços. Casar por string literal não funciona; o casamento é
     por CONJUNTO DE TOKENS do nome.

O QUE ESTE MÓDULO RECUSA A FAZER. Se não achar exatamente um meter de entrada e um de saída para
o modelo, ele devolve `None` em vez de escolher o mais parecido. Um painel que diz "não sei o
preço deste modelo" é útil; um que mostra o preço de outro modelo com a mesma cara dos demais é a
razão de este arquivo existir.
"""

from __future__ import annotations

import re
import time

_URL = "https://prices.azure.com/api/retail/prices"
_API_VERSION = "2023-01-01-preview"

#: Cache em memória: `{(modelo, região): (expira_em, preço)}`. O preço de lista muda em escala de
#: meses; consultar a cada requisição gastaria uma chamada de rede para um número estável.
_CACHE: dict[tuple[str, str], tuple[float, tuple[float, float] | None]] = {}
_TTL_SEGUNDOS = 24 * 3600


def _tokens(texto: str) -> list[str]:
    """As palavras de um nome de meter, insensível à grafia (hífen, espaço, ponto)."""
    return [t for t in re.split(r"[\s\-_]+", texto.lower()) if t]


def _fetch(region: str) -> list[dict]:
    """Todos os meters de `Foundry Models` na região. A API pagina em 1000 por vez."""
    import httpx

    filtro = f"armRegionName eq '{region}' and serviceName eq 'Foundry Models'"
    itens: list[dict] = []
    url: str | None = f"{_URL}?api-version={_API_VERSION}&$filter={filtro}"
    while url and len(itens) < 6000:
        r = httpx.get(url, timeout=30.0)
        r.raise_for_status()
        corpo = r.json()
        itens.extend(corpo.get("Items", []))
        url = corpo.get("NextPageLink")
    return itens


#: O VOCABULÁRIO DE PRECIFICAÇÃO — as palavras que descrevem COMO se cobra, não O QUE se cobra.
#: Removê-las do nome do meter deixa a identidade do modelo, e é isso que se compara. Medido: o
#: mesmo catálogo usa TRÊS convenções para a mesma coisa —
#:     `gpt-5-codex-inp-glbl Tokens`   hífens, com "gpt", `glbl`
#:     `gpt 5 pro inp glbl Tokens`     espaços, com "gpt", `glbl`
#:     `5 mini pp Inp Gl 1M Tokens`    espaços, SEM "gpt", `Gl`, unidade 1M
#: — então casar por string, ou exigir o token "gpt", perde modelos inteiros em silêncio. Foi
#: exatamente o que aconteceu com `gpt-5-mini`, que é o modelo padrão deste projeto.
_VOCABULARIO = frozenset(
    {
        "gpt", "tokens", "unit", "units",
        "in", "inp", "inpt", "input", "out", "outp", "outpt", "opt", "output",
        "gl", "glbl", "global", "dz", "dzone", "regional", "regnl",
        "1k", "1m", "100k",
    }
)

#: Meters que NÃO são inferência normal. Cada um tem preço próprio, e casá-los como se fossem o
#: preço base daria número errado em silêncio — `cd`/`cchd` (entrada em cache) é ~10× mais barato,
#: `batch` ~50%, e `ft`/`training`/`hosting` são de fine-tuning, que não é o que medimos.
#: `pp` é PRIORITY PROCESSING, um tier próprio e mais caro — não a modalidade base. Ele quase me
#: enganou: `5 mini pp Inp Gl 1M` custa $0,45/1M contra $0,25/1M de `GPT 5 Mini Inpt Glbl 1M`, e
#: eu quase concluí que a tabela da casa subestimava o modelo padrão em 80%. Quem pegou o erro foi
#: a recusa por ambiguidade lá embaixo, que se negou a escolher entre dois preços do mesmo modelo.
#: É a evidência de que "recusar em vez de chutar" não é preciosismo: foi o que impediu uma
#: correção errada de entrar.
_EXCLUIR = frozenset(
    {
        "cd", "cchd", "ccchd", "cached", "batch", "pp",
        "ft", "training", "hosting", "grdr", "mdl", "dev",
    }
)

#: As grafias de direção, EXTRAÍDAS DO CATÁLOGO em vez de supostas. Contadas em eastus:
#: `inp` 609 · `outp` 206 · `opt` 143 · `input` 76 · `output` 62 · `inpt` 50 · `out` 44 ·
#: `in` 35 · `outpt` 13. Eu tinha escrito `outp` de cabeça e o catálogo usa `outpt` em 13 meters —
#: entre eles TODOS os de saída do gpt-5-mini, que é o modelo padrão. O efeito foi silencioso: a
#: lista de saída ficava vazia e o modelo virava "sem preço". Adivinhar grafia é o erro; ler o
#: catálogo é o conserto.
_ENTRADA = frozenset({"in", "inp", "inpt", "input"})
_SAIDA = frozenset({"out", "outp", "outpt", "opt", "output"})

#: Tipo de deployment. `gl`/`glbl`/`global` é o default do Foundry; `dz` (data zone) custa ~10%
#: mais. Preferir explicitamente é melhor que pegar o primeiro que a API devolver.
_PREFERIDO = frozenset({"gl", "glbl", "global"})

#: Quanto multiplicar o `retailPrice` para chegar a USD por 1M tokens. As duas unidades convivem
#: no mesmo catálogo (medido em eastus: 612 meters em `1K`, 324 em `1M`), e tratar só uma delas
#: descartaria um terço do catálogo sem erro nenhum.
_POR_1M = {"1K": 1000.0, "1M": 1.0}


def _identidade(nome: str) -> set[str]:
    """O que sobra depois de tirar vocabulário de precificação e SUFIXO DE VERSÃO: o modelo.

    O sufixo sai dos DOIS lados, e é o que faz `gpt-5-mini-2026-08-01` — nome de DEPLOYMENT, não
    de modelo — casar com o meter de `gpt-5-mini`. Nomear deployment com a data é padrão da Azure,
    e a tabela anterior tratava esse caso por casamento de prefixo: resolvia o sufixo e, de
    quebra, fazia `gpt-5-pro` casar com a linha de `gpt-5`, subestimando o custo em 12×. Recortar
    o sufixo explicitamente resolve o caso legítimo sem abrir o ilegítimo.

    Só o sufixo FINAL, e nunca até esvaziar. Duas armadilhas que a regra ingênua tinha:
      · uma data quebra em partes de dois dígitos (`2026-08-01` → `2026`,`08`,`01`), então cortar
        só números com 3+ dígitos deixava `08`,`01` na identidade;
      · cortar qualquer número em qualquer posição levaria `gpt-35-turbo` a virar `turbo` e
        `gpt-5` a virar VAZIO — e identidade vazia casa com tudo.
    """
    partes = [t for t in _tokens(nome) if t not in _VOCABULARIO]
    cauda: list[str] = []
    while partes and partes[-1].isdigit():
        cauda.insert(0, partes.pop())
    # Só corta se a cauda numérica contiver um ANO (4 dígitos). `gpt-5-mini-2026-08-01` corta;
    # `gpt-5` não, porque ali o "5" é a geração do modelo, não a versão do deployment — e cortá-lo
    # transformaria o nome em "gpt", que não é modelo nenhum. Foi o erro da primeira versão desta
    # regra, e ele só apareceu porque o teste cobre `gpt-5` puro.
    if not any(len(p) >= 4 for p in cauda):
        partes.extend(cauda)
    return set(partes)


def _mesma_identidade(meter: set[str], alvo: set[str]) -> bool:
    """Identidade igual, tolerando no meter um sufixo de VERSÃO (`0718`, `0125`).

    Igualdade, e não contenção: `gpt-5` contido em `5 mini` é justamente o casamento frouxo que
    subestimava o custo em 12×. Sufixo puramente numérico com 3+ dígitos é data de versão do
    deployment, padrão documentado da Azure, e não muda de que modelo se trata.
    """
    extras = meter - alvo
    return not (alvo - meter) and all(e.isdigit() and len(e) >= 3 for e in extras)


def resolve(model: str, itens: list[dict]) -> tuple[float, float] | None:
    """`(entrada, saída)` em USD por 1M tokens, ou None se não der para decidir COM CERTEZA.

    Pura de propósito: recebe os itens já buscados, então o gate roda offline sobre uma captura
    real da API em vez de depender de rede.
    """
    alvo = _identidade(model)
    if not alvo:
        return None

    entrada: list[tuple[float, set[str]]] = []
    saida: list[tuple[float, set[str]]] = []
    for item in itens:
        nome = item.get("meterName", "")
        fator = _POR_1M.get(item.get("unitOfMeasure", ""))
        if not nome or fator is None:
            continue
        palavras = set(_tokens(nome))
        if palavras & _EXCLUIR or not _mesma_identidade(_identidade(nome), alvo):
            continue
        preco = round(float(item.get("retailPrice", 0.0)) * fator, 6)
        if palavras & _ENTRADA:
            entrada.append((preco, palavras))
        elif palavras & _SAIDA:
            saida.append((preco, palavras))

    def _escolher(candidatos: list[tuple[float, set[str]]]) -> float | None:
        if not candidatos:
            return None
        preferidos = [c for c in candidatos if c[1] & _PREFERIDO] or candidatos
        precos = {p for p, _ in preferidos}
        # Preços DIFERENTES sobrando é ambiguidade real, não detalhe: o nome casou com mais de um
        # produto. Escolher um seria chutar, que é o que este módulo existe para não fazer.
        return precos.pop() if len(precos) == 1 else None

    p_in, p_out = _escolher(entrada), _escolher(saida)
    return (p_in, p_out) if p_in is not None and p_out is not None else None


def meters_for(model: str, itens: list[dict]) -> list[str]:
    """Os NOMES dos meters de que o preço saiu. Vazio quando o preço não foi determinado.

    POR QUE O NOME IMPORTA E NÃO SÓ O NÚMERO. `SkuMeter` é uma coluna do export FOCUS de billing
    da Azure — e é *exatamente* este mesmo vocabulário. Guardar o nome do meter ao lado do custo
    estimado é o que permite, quando houver fatura com volume, cruzar o que estimamos contra o que
    foi cobrado: a chave de junção existe hoje, e sai de graça.

    Sem isto, a reconciliação futura precisaria adivinhar de qual meter cada estimativa veio, que
    é o mesmo problema de casamento por nome que este módulo já resolveu uma vez.
    """
    alvo = _identidade(model)
    if not alvo or resolve(model, itens) is None:
        return []
    nomes = []
    for item in itens:
        nome = item.get("meterName", "")
        palavras = set(_tokens(nome))
        if (
            _POR_1M.get(item.get("unitOfMeasure", "")) is not None
            and not (palavras & _EXCLUIR)
            and _mesma_identidade(_identidade(nome), alvo)
            and palavras & (_ENTRADA | _SAIDA)
            and palavras & _PREFERIDO
        ):
            nomes.append(nome)
    return sorted(nomes)


def price_detail(model: str, region: str) -> dict:
    """`{"price": (entrada, saída) | None, "meters": [nomes]}` — o número E de onde ele veio.

    Uma chamada só de propósito: pedir preço e procedência em duas funções faria duas buscas na
    API para responder sobre a mesma coisa, e abriria a chance de as duas discordarem se o
    catálogo mudasse no meio.
    """
    try:
        itens = _fetch(region)
    except Exception:  # noqa: BLE001 — preço indisponível não derruba o painel
        return {"price": None, "meters": []}
    preco = resolve(model, itens)
    return {"price": preco, "meters": meters_for(model, itens) if preco else []}


def price_for(model: str, region: str) -> tuple[float, float] | None:
    """O preço do modelo na região, direto da Azure. `None` quando não dá para afirmar.

    Silencioso em falha de rede — um painel sem preço é melhor que um painel que não abre — mas o
    `None` que sai daqui é o mesmo do "não achei o meter", e o chamador trata os dois igual: não
    mostra número. Distinguir os dois motivos importaria se houvesse ação diferente; não há.
    """
    chave = (model.lower(), region.lower())
    agora = time.time()
    if chave in _CACHE and _CACHE[chave][0] > agora:
        return _CACHE[chave][1]
    try:
        preco = resolve(model, _fetch(region))
    except Exception:  # noqa: BLE001 — preço indisponível não derruba o painel
        preco = None
    _CACHE[chave] = (agora + _TTL_SEGUNDOS, preco)
    return preco
