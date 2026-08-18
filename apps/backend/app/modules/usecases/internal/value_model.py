"""O modelo de valor lido de um documento, não escrito em Python.

MESMO MOVIMENTO QUE OS PROMPTS JÁ FIZERAM. A ADR-013/015 tirou o texto dos agentes do código
porque conteúdo de negócio não se edita em Python. A fórmula de retorno é o mesmo tipo de coisa:
constantes que cada operação precisa ajustar, com procedência que precisa aparecer na tela. Elas
estavam como literais em `outcomes.py`, o que obrigava a trocar código para trocar premissa — e,
pior, permitia que o número mudasse sem que a PROCEDÊNCIA ao lado dele mudasse junto.

`VALUE_MODEL` aponta para outro arquivo: é como uma instalação usa o modelo dela sem fork, do
mesmo jeito que `AGENTS_DIR` faz com os prompts (ADR-014).

FALHA É ALTA, NÃO SILENCIOSA. Se o documento existir e não carregar, isto levanta. O contrário —
cair no default calado — produziria um painel mostrando a premissa de outra pessoa com a cara da
sua, que é exatamente o tipo de erro que este arquivo existe para tornar impossível.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import app

#: Ancorado no pacote `app`, nunca contando `parents[N]` a partir deste arquivo (regra #9 —
#: três caminhos quebraram assim durante a ADR-017, dois em silêncio).
_PADRAO = Path(app.__file__).resolve().parent.parent / "value" / "default.yaml"

#: Constantes que a FÓRMULA fixa, e que portanto o documento não pode mudar mesmo declarando
#: `locked: false`. Editá-las deixaria de ser "adaptar à minha operação" e passaria a ser ajustar
#: a AAH até o número agradar — com o crachá da Microsoft sobre a conta da casa.
_TRAVADAS = ("resolved_weight", "unresolved_weight")


def _caminho() -> Path:
    """O documento a ler. A env var VAZIA vale como ausente.

    `Path("")` é `Path(".")`, que é truthy — então `Path(env) or _PADRAO` nunca cai no default e
    tenta ler o diretório atual. A checagem é na STRING, antes de virar caminho.
    """
    declarado = os.environ.get("VALUE_MODEL", "").strip()
    return Path(declarado).expanduser() if declarado else _PADRAO


def load() -> dict[str, Any]:
    """O documento do modelo de valor. Levanta se o arquivo apontado não puder ser lido."""
    import yaml

    caminho = _caminho()
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    if not isinstance(dados, dict) or "constants" not in dados:
        raise ValueError(f"modelo de valor inválido em {caminho}: falta `constants`")
    return dados


def assumption() -> dict[str, Any]:
    """A premissa, no formato que `outcomes` consome."""
    doc = load()
    c = doc["constants"]
    travadas = {k: float(_PADRAO_CONSTANTES[k]) for k in _TRAVADAS}
    return {
        "minutes_per_reference": float(c["minutes_per_reference"]["value"]),
        "hourly_cost": float(c["hourly_cost"]["value"]),
        "currency": str(c["hourly_cost"].get("currency", "BRL")),
        "source": "default",
        **travadas,
    }


def provenance() -> dict[str, str]:
    """De onde cada constante veio — sobe na resposta junto com o número.

    "Premissa visível" não é só mostrar o valor: é dizer quem o escolheu. O multiplicador é da
    Microsoft e tem fonte publicada; o custo da hora é desta instalação. Misturar os dois sem
    distinguir faria o número inteiro parecer sourced quando metade não é.
    """
    doc = load()
    c = doc["constants"]
    f = doc.get("formula", {})
    return {
        "formula": str(f.get("label", "")),
        "formula_doc": str(f.get("doc", "")),
        "multiplier_source": str(c["minutes_per_reference"].get("note", "")),
        "hourly_cost_source": str(c["hourly_cost"].get("note", "")),
    }


#: Os pesos da fórmula publicada. Ficam aqui, em código, DE PROPÓSITO: são o que o documento não
#: pode mexer, e um valor travado que mora no arquivo editável não está travado.
_PADRAO_CONSTANTES = {"resolved_weight": 1.0, "unresolved_weight": 0.7}
