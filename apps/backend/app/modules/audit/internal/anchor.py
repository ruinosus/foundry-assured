"""A âncora diária — o fecho que torna a adulteração detectável mesmo com a trilha inteira reescrita.

O QUE A CADEIA SOZINHA NÃO RESOLVE. `verify()` prova que a trilha é internamente consistente. Mas
quem conseguisse reescrever o arquivo inteiro poderia recalcular todos os hashes e produzir uma
cadeia nova, íntegra e falsa. A cadeia detecta EDIÇÃO; ela não detecta SUBSTITUIÇÃO.

A âncora é o que fecha isso: uma vez por dia, o hash de cabeça da trilha é gravado num blob
WRITE-ONCE separado. Reescrever a trilha passa a exigir também reescrever as âncoras — e elas
estão sob a política de imutabilidade do Azure, que recusa (ADR-023).

TRILHA VIOLADA NÃO É ANCORADA. Se a verificação falha, a âncora do dia não é gravada e o motivo
fica registrado. Ancorar uma cadeia adulterada seria certificá-la — e a âncora existe justamente
para ser o que alguém confia.

O QUE NÃO TEM AQUI, dito em vez de omitido:

  · **Carimbo de tempo RFC 3161.** Prova o INSTANTE por um terceiro (uma ACT credenciada), e
    depende de contrato comercial que este projeto não tem. O campo `tsr` existe na âncora e
    nasce vazio; preenchê-lo é ligar um cliente de TSA, não redesenhar isto.
  · **Recibo do Confidential Ledger.** É a resposta de primeira parte para "prove que este
    registro foi comprometido naquele instante", e é o caminho de upgrade que a ADR-023 registra.
    A âncora aqui é o degrau que funciona com o storage que já existe.

Sem esses dois, a âncora prova que a trilha não mudou DESDE O FECHAMENTO — o que é bem mais do
que a cadeia sozinha, e menos do que prova jurídica. A diferença está declarada no relatório de
verificação, nunca escondida.
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime

from app.modules.audit.internal.trail import GENESIS, trail, verify

#: As âncoras moram ao lado da trilha, no mesmo container imutável. Prefixo próprio para a
#: listagem separá-las sem precisar abrir nada.
PREFIXO = "_anchors/"


class AnchorExists(RuntimeError):
    """Já existe âncora para este dia. Nunca sobrescrever — write-once é o ponto."""


def _hoje() -> str:
    return datetime.now(UTC).date().isoformat()


def build_anchor(scope: str, eventos: list[dict], dia: str) -> dict:
    """O objeto da âncora. PURO — testável offline, sem rede."""
    verificacao = verify(eventos)
    return {
        "scope": scope,
        "date": dia,
        "events": len(eventos),
        "seq": eventos[-1]["seq"] if eventos else 0,
        # O hash de cabeça: o estado inteiro da trilha resumido num valor.
        "digest": eventos[-1]["hash"] if eventos else GENESIS,
        "verified": verificacao["ok"],
        "reason": verificacao["reason"],
        # Slots declarados e VAZIOS — ver o cabeçalho. Um campo ausente faria parecer que a
        # prova temporal nunca foi considerada; vazio diz que ela falta.
        "tsr": None,
        "ledger_receipt": None,
        "closed_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def close_day(scope: str, dia: str = "") -> dict:
    """Fecha o dia: verifica a trilha e grava a âncora. Recusa se já existir, e recusa se a
    trilha estiver violada."""
    from azure.core import MatchConditions
    from azure.core.exceptions import ResourceExistsError, ResourceModifiedError

    dia = dia or _hoje()
    t = trail()
    eventos = t.read(scope)
    ancora = build_anchor(scope, eventos, dia)

    if not ancora["verified"]:
        # Registrar a RECUSA é parte do controle: uma âncora ausente sem motivo é indistinguível
        # de um dia em que ninguém rodou o fechamento.
        return {**ancora, "written": False, "refused": "trilha violada — não ancorada"}

    container = getattr(t, "_container", None)
    if container is None:
        # Modo em memória: não há write-once, e dizer isso é melhor que devolver sucesso.
        return {**ancora, "written": False, "refused": "sem storage — âncora não é durável"}

    blob = container.get_blob_client(f"{PREFIXO}{scope}/{dia}.json")
    corpo = json.dumps(ancora, ensure_ascii=False, sort_keys=True).encode("utf-8")
    try:
        # `IfMissing` é o write-once: a SEGUNDA gravação do mesmo dia falha, ela não sobrescreve.
        blob.upload_blob(corpo, match_condition=MatchConditions.IfMissing)
    except (ResourceExistsError, ResourceModifiedError) as exc:
        raise AnchorExists(f"a âncora de {scope}/{dia} já existe e não será sobrescrita") from exc
    return {**ancora, "written": True, "refused": ""}


def read(scope: str, dia: str) -> dict | None:
    """A âncora de um dia, ou None."""
    t = trail()
    container = getattr(t, "_container", None)
    if container is None:
        return None
    with contextlib.suppress(Exception):
        bruto = container.get_blob_client(f"{PREFIXO}{scope}/{dia}.json").download_blob().readall()
        return json.loads(bruto.decode("utf-8"))
    return None


def list_anchors(scope: str) -> list[dict]:
    """As âncoras do escopo, mais antigas primeiro."""
    t = trail()
    container = getattr(t, "_container", None)
    if container is None:
        return []
    saida = []
    with contextlib.suppress(Exception):
        for b in container.list_blobs(name_starts_with=f"{PREFIXO}{scope}/"):
            dia = b.name.rsplit("/", 1)[-1].removesuffix(".json")
            saida.append({"date": dia, "name": b.name})
    return sorted(saida, key=lambda a: a["date"])
