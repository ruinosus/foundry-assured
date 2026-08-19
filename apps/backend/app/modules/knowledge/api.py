"""HTTP para confirmar evidência: o documento integral que sustenta uma citação.

MORA NO `knowledge` porque é ele o dono da ACL e da recuperação — só daqui dá para reusar o
trim sem cruzar fronteira. Pôr no `grounded` obrigaria a importar `knowledge.internal`, que o
contrato "knowledge internals are private" proíbe (importlinter.toml).

SÓ LEITURA. Não existe rota de escrita aqui e não deve existir.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import APIRouter, HTTPException

from app.modules.knowledge.public import authorized_document
from app.shared.auth import auth_dependencies, current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/source", tags=["source"], dependencies=[*auth_dependencies()])

# `DomainSpec`/`domain_spec` vivem em `app.registry` — a composition root, uma camada ACIMA
# de `app.modules` (ADR-017/importlinter.toml: "Layers: composition > modules > shared"). Este
# módulo não pode importar `app.registry`, então a composição EMPURRA a função de resolução
# aqui no boot (mesmo padrão de `app.shared.auth.set_post_authenticate`), em vez deste módulo
# puxá-la de lá.
_domain_lookup: Callable[[str], object] | None = None


def set_domain_lookup(fn: Callable[[str], object]) -> None:
    """Injetado por `app.registry.include_routers` — a única chamada permitida a fazê-lo."""
    global _domain_lookup
    _domain_lookup = fn


@router.get("/{domain_id}/{name}")
async def read_source(domain_id: str, name: str) -> dict:
    if _domain_lookup is None:
        raise HTTPException(status_code=500, detail="resolução de domínio não configurada")
    try:
        domain = _domain_lookup(domain_id)
    except Exception:
        raise HTTPException(status_code=404, detail="domínio desconhecido") from None
    if getattr(domain, "kind", "") == "tool":
        raise HTTPException(status_code=404, detail="domínio não tem documentos")

    user = current_user()
    try:
        url, conteudo = await authorized_document(domain, name, user)
    except ValueError:
        raise HTTPException(status_code=400, detail="nome de documento inválido") from None
    except PermissionError:
        _auditar(domain_id, name, autorizado=False)
        # 403 e não 404: a pessoa está autenticada e a rota existe. Não vazamos se o documento
        # existe — `authorized_document` já não distingue os dois casos.
        raise HTTPException(status_code=403, detail="sem autorização para este documento") from None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="documento não encontrado") from None

    _auditar(domain_id, name, autorizado=True)
    return {"name": name, "url": url, "content": conteudo}


def _auditar(domain_id: str, name: str, *, autorizado: bool) -> None:
    """Registra a leitura — e TAMBÉM a negada, que é o sinal mais interessante da trilha.

    Fail-soft como o registro do `retrieve()`: ler é reversível, e negar a leitura por causa
    de um problema de infraestrutura de auditoria puniria o usuário. A ausência aparece como
    lacuna no relatório de verificação, que é onde deve aparecer.
    """
    import contextlib

    with contextlib.suppress(Exception):
        from app.modules.audit.public import actor, actor_detail, record

        record(
            scope="access",
            actor=actor(),
            kind="access",
            summary=f"documento {'aberto' if autorizado else 'NEGADO'}: {name}",
            ref=domain_id,
            detail={"document": name, "authorized": autorizado, **actor_detail()},
        )
