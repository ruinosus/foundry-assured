"""Quem perguntou — a identidade do chamador MCP, no vocabulário que o backend já lê.

EXISTE PORQUE AGORA HÁ MAIS DE UMA SUPERFÍCIE. Até a Fase 1 só a tool `search_docs` precisava
traduzir o token do FastMCP para o objeto de usuário que `knowledge` espera, e o código morava
lá dentro. Com o resource do documento integral (e a completion que o alimenta), o MESMO
trecho passaria a existir em dois ou três lugares — e a divergência entre eles não daria erro,
só faria uma superfície auditar como `process:app` o que a outra audita como humano, ou
degradar aberta onde a outra falha fechada. Uma implementação, três chamadores.

O que este módulo NÃO faz: decidir acesso. A decisão é DADO (regra 6) e mora em `knowledge` —
aqui só se responde "quem é o chamador", nunca "o que ele pode ler".
"""

from __future__ import annotations

from typing import Any

from fastmcp.exceptions import ToolError

from app.shared.auth import set_current_user
from app.shared.settings import settings


class Chamador:
    """Quem perguntou, no vocabulário que o resto do backend já lê.

    `access_token` é o único atributo que o `retrieve` usa (OBO). Os demais são os que
    `audit.actor()`/`actor_detail()` e `shared.auth.current_roles()` leem do usuário do FastAPI
    — vêm das claims do MESMO token do Entra, então a trilha grava a mesma identidade que
    gravaria se a pergunta tivesse entrado pela web.
    """

    def __init__(self, access_token: str | None, claims: dict[str, Any]) -> None:
        self.access_token = access_token
        self.oid = str(claims.get("oid") or "")
        self.preferred_username = str(claims.get("preferred_username") or "")
        self.email = str(claims.get("email") or "")
        self.roles = list(claims.get("roles") or [])
        # `tid` só importa no modo shared: é a chave que `tenancy.resolve_tenant_record` lê para
        # achar o `TenantRecord` do chamador — mesmo claim que `require_user` já lê no caminho web.
        self.tid = str(claims.get("tid") or "")


def identidade_do_chamador(token: Any, *, erro: str) -> Chamador:
    """Do token do FastMCP para o `Chamador`, DECLARANDO-O como usuário da requisição.

    FALHA FECHADA COM A AUTH LIGADA. Sem token do chamador, o `retrieve` cai no ramo
    "identidade da aplicação": em domínio de fallback ele manda `x-ms-enable-elevated-read`,
    isto é, LÊ TUDO como a app — sem erro, sem log, sem sintoma. Degradar assim é correto no
    dev local (a auth está desligada e é o comportamento do resto do backend), e é vazamento
    em produção. A distinção é `settings.auth_enabled`, a mesma que governa todo o resto.

    A DECLARAÇÃO (`set_current_user`) não é detalhe. A trilha de auditoria da ADR-023 é gravada
    lá dentro do `knowledge`, via `audit.actor()`, que lê esse mesmo contextvar: sem isto, toda
    leitura por MCP entrava na trilha imutável como `process:app` — acesso decidido pela
    identidade certa e registrado com a identidade errada.

    `erro` é a mensagem que o chamador lê quando falta identidade; cada superfície tem a sua
    (uma busca e a leitura de um documento explicam coisas diferentes), e por isso ela vem de
    fora em vez de ser inventada aqui.
    """
    bruto = getattr(token, "token", None) if token is not None else None
    if settings.auth_enabled and not bruto:
        raise ToolError(erro)
    chamador = Chamador(bruto, getattr(token, "claims", None) or {})
    if bruto:
        # Só com token: com a auth desligada não HÁ chamador, e declarar um sem identidade faria
        # a trilha gravar um `human:` inventado onde `process:app` é a verdade.
        set_current_user(chamador)
    return chamador
