"""HTTP para confirmar evidência: o documento integral que sustenta uma citação.

MORA NO `knowledge` porque é ele o dono da ACL e da recuperação — só daqui dá para reusar o
trim sem cruzar fronteira. Pôr no `grounded` obrigaria a importar `knowledge.internal`, que o
contrato "knowledge internals are private" proíbe (importlinter.toml).

SÓ LEITURA. Não existe rota de escrita aqui e não deve existir.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Response

from app.modules.knowledge.public import NomeDocumentoInvalido, authorized_document
from app.modules.tenancy.public import require_domain
from app.shared.auth import auth_dependencies, current_user
from app.shared.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/source", tags=["source"], dependencies=[*auth_dependencies()])

# Teto do documento devolvido por esta rota. A cadeia soma QUATRO cópias em memória por clique
# (blob → JSON do backend → `await r.json()` do proxy Next → parse no browser + Streamdown/Shiki),
# e sem teto o tamanho de um documento na base vira o tamanho da resposta HTTP. 1 MB é folgado
# para o corpus atual (runbooks/wiki em markdown) e pequeno o bastante para não custar caro.
_TETO_DOCUMENTO_BYTES = 1_000_000

# `DomainSpec`/`domain_spec` viviam em `app.registry` — a composition root, uma camada ACIMA
# de `app.modules` (ADR-017) — e por isso a composição EMPURRA a função de resolução aqui no
# boot (mesmo padrão de `app.shared.auth.set_post_authenticate`), em vez deste módulo puxá-la.
# Desde a Fase 0c o catálogo é um MÓDULO (`app.modules.domains`) e este import seria legal; o
# empurrão fica porque trocá-lo acrescentaria a aresta `knowledge -> domains` ao grafo, o que é
# decisão de arquitetura própria. A razão do seam mudou; o seam não.
_domain_lookup: Callable[[str], object] | None = None


def set_domain_lookup(fn: Callable[[str], object]) -> None:
    """Injetado por `app.registry.include_routers` — a única chamada permitida a fazê-lo.

    Levanta se já houver um registro: mesmo precedente de `app.shared.auth.set_post_authenticate`
    — duas chamadas significariam dois lugares reivindicando silenciosamente o mesmo ponto único.
    """
    global _domain_lookup
    if _domain_lookup is not None and fn is not None:
        raise RuntimeError("a resolução de domínio já está registrada")
    _domain_lookup = fn


@router.get("/{domain_id}/{name}")
async def read_source(domain_id: str, name: str, response: Response) -> dict:
    if _domain_lookup is None:
        raise HTTPException(status_code=500, detail="resolução de domínio não configurada")
    try:
        domain = _domain_lookup(domain_id)
    except Exception:  # noqa: BLE001 — qualquer falha na resolução vira 404 genérico, sem
        # vazar detalhe interno de qual domínio/config específica quebrou
        raise HTTPException(status_code=404, detail="domínio desconhecido") from None
    if getattr(domain, "kind", "") == "tool":
        raise HTTPException(status_code=404, detail="domínio não tem documentos")

    # ADR-010: gate de entitlement por tenant no modo shared. `domain_id` é path param, então
    # `domain_deps(domain_id)` — o que toda outra rota por domínio usa (registry.py, hosted/
    # api.py) — não dá pra montar como `dependencies=` estático do router aqui. Chamamos o
    # MESMO `require_domain` que elas chamam, dentro do handler, antes de tocar o documento —
    # não reimplementamos a regra, só o ponto de chamada muda (dependency estática → chamada
    # direta). `_check` pede `Depends(require_user)` só para ordenar a resolução do tenant
    # depois da sessão; a sessão já foi validada pela dependency do router (`auth_dependencies`,
    # acima), então chamamos `_check()` direto, sem o DI do FastAPI. Condicionado a `shared`
    # pelo mesmo motivo que `domain_deps` condiciona: fora do modo shared não existe tenant
    # resolvido (`_current_tenant` fica `None`), e `require_domain` é fail-closed — chamado sem
    # essa guarda, derrubaria self_hosted/dedicated com 403 em toda leitura.
    if settings.deployment_mode == "shared":
        try:
            await require_domain(domain_id)()
        except HTTPException:
            # Mesmo par ACL: a negação por entitlement (ADR-010) é tão interessante para a
            # trilha quanto a negação por ACL logo abaixo — sem isto a auditoria ficava com
            # metade do par (só registrava quem passou pelo gate de tenant).
            _auditar(domain_id, name, autorizado=False, url=None)
            raise

    # Conteúdo controlado por ACL: nunca cacheado por proxy/CDN/navegador — um cache
    # compartilhado devolveria o documento de uma pessoa para outra.
    response.headers["Cache-Control"] = "no-store"

    user = current_user()
    try:
        url, conteudo = await authorized_document(domain, name, user)
    except NomeDocumentoInvalido:
        raise HTTPException(status_code=400, detail="nome de documento inválido") from None
    except PermissionError as exc:
        _auditar(domain_id, name, autorizado=False, url=getattr(exc, "url", None))
        # 403 e não 404: a pessoa está autenticada e a rota existe. Não vazamos se o documento
        # existe — `authorized_document` já não distingue os dois casos.
        raise HTTPException(status_code=403, detail="sem autorização para este documento") from None
    except FileNotFoundError as exc:
        _auditar(domain_id, name, autorizado=False, url=getattr(exc, "url", None))
        raise HTTPException(status_code=404, detail="documento não encontrado") from None

    _auditar(domain_id, name, autorizado=True, url=url)

    # A truncagem é DECLARADA na resposta, nunca silenciosa: quem clica no `[n]` está prestes a
    # confirmar uma evidência, e confirmar sobre um documento cortado sem saber é pior do que não
    # ver o final dele. `truncated` deixa a interface avisar em vez de fingir que mostrou tudo.
    bruto = conteudo.encode("utf-8")
    truncado = len(bruto) > _TETO_DOCUMENTO_BYTES
    if truncado:
        conteudo = bruto[:_TETO_DOCUMENTO_BYTES].decode("utf-8", errors="ignore")
    return {"name": name, "url": url, "content": conteudo, "truncated": truncado}


def _auditar(domain_id: str, name: str, *, autorizado: bool, url: str | None) -> None:
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
            # `url` é a CHAVE real do documento (o que o trim filtra por); `name` sozinho não
            # identifica o recurso entre domínios/containers diferentes.
            detail={"document": name, "url": url, "authorized": autorizado, **actor_detail()},
        )
