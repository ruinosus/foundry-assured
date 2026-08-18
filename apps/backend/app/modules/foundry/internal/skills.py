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

# Teto do bundle. O serviço extrai e valida o zip do lado dele; isto só impede que um upload
# absurdo ocupe memória do processo antes de chegar lá.
MAX_BUNDLE_BYTES = 25 * 1024 * 1024


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

    # `description` é OBRIGATÓRIO no serviço, e o SDK não diz isso: `SkillInlineContent` o
    # declara opcional. Sem ele o Foundry responde `invalid_payload: The request field is
    # required` — mensagem que não nomeia o campo faltante e manda procurar no lugar errado.
    # Descoberto empiricamente: a mesma chamada passa com description e falha sem.
    descricao = doc.get("description")
    if not descricao or not str(descricao).strip():
        raise InvalidSkill(
            "Falta `description` — uma frase dizendo para que serve a skill. O serviço a exige."
        )

    out: dict[str, Any] = {
        "instructions": str(instructions).strip(),
        "description": str(descricao).strip(),
    }
    for key in ("allowed_tools", "compatibility", "license", "metadata"):
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


def _ensure_frontmatter(name: str, description: str, conteudo: bytes) -> bytes:
    """Garante o frontmatter YAML que o serviço exige no `SKILL.md`.

    O upload multipart falha com "requires a 'description' field in the SKILL.md YAML frontmatter"
    quando ele falta — mensagem correta para quem conhece o formato agentskills.io, e inútil para
    quem só arrastou um arquivo. Como já temos nome e descrição da skill, montamos o cabeçalho.

    Sem aspas nos valores: com elas o serviço responde `invalid_payload`. É exigência do parser
    dele, não escolha de estilo.
    """
    texto = conteudo.decode("utf-8", errors="replace")
    if texto.lstrip().startswith("---"):
        return conteudo  # já tem cabeçalho; respeitamos o que a pessoa escreveu
    limpo = description.replace("\n", " ").replace('"', "").strip() or name
    cabecalho = f"---\nname: {name}\ndescription: {limpo}\n---\n\n"
    return (cabecalho + texto).encode("utf-8")


#: Teto do serviço para as INSTRUÇÕES da skill — o conteúdo do `SKILL.md`.
#:
#: Não é limite nosso; é o que o Foundry responde: `Skill instructions exceed the maximum length
#: of 65536 characters`. Está aqui para a recusa acontecer ANTES do upload do bundle inteiro, com
#: uma mensagem que diz o que fazer, em vez de depois, com vocabulário de plataforma.
MAX_INSTRUCTIONS_CHARS = 65_536


def create_skill_from_files(
    name: str,
    files: list[tuple[str, bytes]],
    *,
    make_default: bool = True,
    description: str = "",
) -> dict:
    """Cria uma versão de skill a partir de um BUNDLE de arquivos.

    É o caminho que a versão inline não cobre, e a diferença é grande: uma skill séria não é uma
    string de instruções — tem scripts, referências, exemplos, templates. `create_from_files`
    aceita **um zip** (o serviço extrai e valida o conteúdo) **ou vários arquivos soltos** (upload
    de diretório, validados como estão). Os dois formatos são do serviço, não nossos.

    Nada aqui interpreta o conteúdo: os arquivos são dados que o serviço valida. O que fazemos é
    recusar o que nem vale a viagem (vazio, ou acima do teto) e repassar.
    """
    if not files:
        raise InvalidSkill("Envie ao menos um arquivo.")
    total = sum(len(d) for _, d in files)
    if total > MAX_BUNDLE_BYTES:
        raise InvalidSkill(
            f"O bundle tem {total // (1024 * 1024)} MB e o limite é {MAX_BUNDLE_BYTES // (1024 * 1024)} MB."
        )

    # As instruções são o SKILL.md. Verificar aqui evita subir megabytes para receber um 400 do
    # serviço sobre o único arquivo que já estava em mãos.
    for fname, data in files:
        if fname.lower().endswith("skill.md"):
            chars = len(data.decode("utf-8", errors="replace"))
            if chars > MAX_INSTRUCTIONS_CHARS:
                raise InvalidSkill(
                    f"O SKILL.md tem {chars:,} caracteres e o serviço aceita no máximo "
                    f"{MAX_INSTRUCTIONS_CHARS:,}. Skills longas devem manter o SKILL.md curto e "
                    "mover o detalhe para arquivos de referência — é a convenção de divulgação "
                    "progressiva do agentskills.io. Esta precisa ser dividida na origem."
                    .replace(",", ".")
                )
    qualified = qualify(name)
    preparados = [
        (fname, _ensure_frontmatter(qualified, description, data)
         if fname.lower().endswith("skill.md") else data)
        for fname, data in files
    ]

    client = _client()
    try:
        version = client.beta.skills.create_from_files(
            qualified,
            {"files": preparados, "default": make_default},
        )
        return {
            "name": qualified,
            "version": getattr(version, "version", None),
            "default": make_default,
            "files": [f for f, _ in files],
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
