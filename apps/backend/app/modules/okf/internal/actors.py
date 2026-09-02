"""Atores e timestamps do OKF v0.2.

SPEC.md:489-501 (convenção de ator), SPEC.md:284-285 (timestamps),
SPEC.md:366-380 (`generated`), SPEC.md:384-399 (`verified`).

NADA AQUI PODE ENTRAR NUMA DECISÃO DE AUTORIZAÇÃO. O trust tier derivado destes campos é
sinal consultivo e explicitamente NÃO é controle de acesso (SPEC.md:410). O acesso deste
repositório segue a fonte (ADR-031) e não passa por aqui.

POR QUE `_require` RECUSA `/` E `:`. Os dois são separadores da própria convenção: um
produtor chamado `open/wiki` produziria `open/wiki/0.4.3`, que relê como produtor `open` na
versão `wiki/0.4.3`. E um prefixo com `:` deixaria `human` alcançável por acidente — que é
a única falha desta camada que muda o trust tier sem nenhum outro sintoma.
"""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = [
    "agent_actor",
    "generated_block",
    "human_actor",
    "okf_timestamp",
    "process_actor",
    "verified_entry",
]


def _require(value: str, field: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{field} deve ser texto não vazio")
    if "/" in cleaned or ":" in cleaned:
        raise ValueError(f"{field} não pode conter '/' nem ':': {value!r}")
    return cleaned


def agent_actor(producer: str, version: str) -> str:
    """Um agente ou ferramenta: `<produtor>/<versão>` (SPEC.md:494)."""
    return f"{_require(producer, 'producer')}/{_require(version, 'version')}"


def process_actor(name: str, version: str | None = None) -> str:
    """Um processo automatizado: `process:<id>`, versionado quando houver versão."""
    base = f"process:{_require(name, 'name')}"
    return f"{base}/{_require(version, 'version')}" if version is not None else base


def human_actor(identifier: str) -> str:
    """Uma pessoa: `human:<id>`. Só para ação humana de verdade (SPEC.md:500-501)."""
    return f"human:{_require(identifier, 'identifier')}"


def okf_timestamp(moment: datetime | None = None) -> str:
    """ISO 8601 em UTC com offset explícito, precisão de segundo."""
    if moment is None:
        moment = datetime.now(UTC)
    if moment.tzinfo is None:
        raise ValueError("datetime ingênuo recusado; o OKF exige offset UTC explícito")
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def generated_block(by: str, at: str | None = None) -> dict[str, str]:
    """SPEC.md:377 — `by` é obrigatório dentro de `generated`."""
    if not (by or "").strip():
        raise ValueError("generated.by é obrigatório")
    return {"by": by.strip(), "at": at or okf_timestamp()}


def verified_entry(by: str, at: str | None = None) -> dict[str, str]:
    """Um evento de verificação (SPEC.md:384-399)."""
    if not (by or "").strip():
        raise ValueError("verified[].by é obrigatório")
    return {"by": by.strip(), "at": at or okf_timestamp()}
