"""Skills — listar, ver, criar e apagar, via SDK oficial.

MÁXIMA MAIOR: `BetaSkillsOperations` traz 11 operações (`list/get/create/create_from_files/
delete`, mais as de versão e download). Nada de gestão aqui — projeção e validação.

DUAS COISAS QUE O LEVANTAMENTO REVELOU e mudam o que a tela oferece:

**Skill também é recurso versionado.** `SkillDetails` traz `default_version` E `latest_version`, e
os dois são campos separados — a mais nova não é necessariamente a que está em uso. Um agente
usando a `default` continua na versão antiga depois de alguém publicar. Mostrar só uma delas
esconderia exatamente a pergunta que importa quando algo não muda depois de publicar.

**O formato inline é agentskills.io, não nosso.** `SkillInlineContent` tem `instructions`,
`allowed_tools`, `compatibility`, `license` e `metadata` — é o padrão aberto. Então "criar skill"
não inventa esquema: aceita o documento nesse formato. `create_from_files` (zip) é o outro
caminho, para quem já tem a skill empacotada.

Verificado contra o SDK INSTALADO (RULE #1): os campos saem de `SkillDetails`, `SkillVersion` e
`SkillInlineContent`.
"""

from __future__ import annotations

import contextlib
from typing import Any

from app.modules.foundry.internal.names import qualify


class InvalidSkill(ValueError):
    """Documento de skill que não vira recurso, com o motivo."""


def _client():
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    from app.modules.tenancy.public import tenant_config

    return AIProjectClient(
        endpoint=tenant_config().foundry_project_endpoint,
        credential=DefaultAzureCredential(),
        allow_preview=True,
    )


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _version(v: Any) -> dict | None:
    if v is None:
        return None
    return {
        "version": getattr(v, "version", None),
        "description": getattr(v, "description", None),
        "created_at": _iso(getattr(v, "created_at", None)),
    }


def _project(details: Any) -> dict:
    """Uma skill na forma que a interface consome.

    `default` e `latest` sobem os DOIS, e separados. Igualá-los, ou mostrar só o mais novo, faria
    a tela dizer que a skill está atualizada quando os agentes continuam na versão anterior.
    """
    default = _version(getattr(details, "default_version", None))
    latest = _version(getattr(details, "latest_version", None))
    return {
        "name": getattr(details, "name", None),
        "id": getattr(details, "id", None),
        "description": getattr(details, "description", None),
        "created_at": _iso(getattr(details, "created_at", None)),
        "default": default,
        "latest": latest,
        # A pergunta "publiquei e nada mudou, por quê?" respondida antes de ser feita.
        "latest_is_default": bool(
            default and latest and default.get("version") == latest.get("version")
        ),
    }


def list_skills(limit: int = 50) -> list[dict]:
    """As skills do projeto, projetadas. `limit` é o teto do que devolvemos, documentado."""
    client = _client()
    try:
        out: list[dict] = []
        for item in client.beta.skills.list(limit=min(limit, 100)):
            out.append(_project(item))
            if len(out) >= limit:
                break
        return out
    finally:
        with contextlib.suppress(Exception):
            client.close()


def get_skill(name: str) -> dict:
    client = _client()
    try:
        return _project(client.beta.skills.get(name))
    finally:
        with contextlib.suppress(Exception):
            client.close()


def parse_skill(doc: dict) -> dict:
    """Valida um documento no formato agentskills.io e devolve os campos de `SkillInlineContent`.

    Devolve dict, não o objeto do SDK, para o gate rodar offline — sem credencial e em todo push.
    """
    if not isinstance(doc, dict):
        raise InvalidSkill("O documento precisa ser um objeto (mapa de chaves).")

    instructions = doc.get("instructions")
    if isinstance(instructions, list):
        instructions = "\n\n".join(str(x) for x in instructions if x)
    if not instructions or not str(instructions).strip():
        raise InvalidSkill("Falta `instructions` — o que a skill ensina o agente a fazer.")
    if str(instructions).strip().startswith("="):
        raise InvalidSkill(
            "Expressão PowerFx (=...) não é avaliada aqui: sem o runtime .NET o valor chegaria "
            "literal ao serviço. Use o valor direto."
        )

    out: dict[str, Any] = {"instructions": str(instructions).strip()}
    for key in ("description", "allowed_tools", "compatibility", "license", "metadata"):
        if doc.get(key) is not None:
            out[key] = doc[key]

    known = {"name", "instructions", "description", "allowed_tools", "compatibility", "license", "metadata"}
    return {"content": out, "ignored": sorted(set(doc) - known)}


def create_skill(name: str, doc: dict, *, make_default: bool = True) -> dict:
    """Cria (ou versiona) uma skill a partir do documento inline.

    `make_default` é True porque a expectativa de quem clica "criar" é que a skill passe a valer.
    Publicar sem tornar default criaria uma versão que ninguém usa — e o `latest_is_default` da
    listagem existe justamente para tornar essa divergência visível quando ela for intencional.
    """
    from azure.ai.projects.models import SkillInlineContent

    parsed = parse_skill(doc)
    qualified = qualify(name)

    client = _client()
    try:
        version = client.beta.skills.create(
            qualified,
            inline_content=SkillInlineContent(**parsed["content"]),
            default=make_default,
        )
        return {
            "name": qualified,
            "version": getattr(version, "version", None),
            "default": make_default,
            "ignored_fields": parsed["ignored"],
        }
    finally:
        with contextlib.suppress(Exception):
            client.close()


def delete_skill(name: str) -> dict:
    """Apaga a skill e todas as suas versões."""
    qualified = qualify(name)
    client = _client()
    try:
        client.beta.skills.delete(qualified)
        return {"name": qualified, "deleted": True}
    finally:
        with contextlib.suppress(Exception):
            client.close()
