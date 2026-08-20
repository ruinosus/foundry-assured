"""Direct injection de skill — o conteúdo da skill vira instrução do agente.

POR QUE ESTE CAMINHO, e não o toolbox. Testado contra o serviço: um agente do Foundry apontando
para um toolbox enumera e usa as TOOLS dele, mas NÃO lê as SKILLS — que chegam como MCP Resources
(`resources/list`), e o `mcp` tool server-side não as busca. Direct injection é o caminho
documentado que funciona sem toolbox: baixar o `SKILL.md` e injetá-lo como instrução da sessão.

PARA QUAIS AGENTES ISTO VALE, e por quê. Este módulo entra na composição do `agentdefs`, que é
onde persona, instruções e guardrails já se juntam (ADR-013). Quem passa por ali ganha skill sem
mudar nada:

    ✅ helpdesk (triage/retrieve/resolve) — agent-framework
    ✅ platform                            — agent-framework, tool-driven
    ✅ concierge, techdocs, selfwiki        — grounded (Responses API direto)
    ⚠️ oncall (LangGraph)                  — tem o prompt cravado em graph.py, fora do padrão;
                                             passa a valer quando migrar para AgentSchema
    ❌ hosted agents                        — o prompt vive DENTRO do Foundry, não aqui; para eles
                                             a skill entra pela definição do agente hospedado

Ou seja: não é "todos os runtimes", é "todos que compõem prompt por aqui". A fronteira não é o
runtime — é onde o prompt é montado.

O ACOPLAMENTO NOVO, declarado porque o gate de arquitetura o pegou (ADR-017): `agentdefs` passa a
depender de `tenancy` (para o endpoint do project). Até aqui a composição era pura — arquivos do
disco, nada de rede. A dependência é inerente ao desenho: o conteúdo da skill vive no serviço, e
compor sem buscá-lo seria compor sem a skill.

Uma mitigação vale registro: a rede só acontece se ALGUM agente declarar `skills`. Nenhum declara
hoje, então `agentdefs` segue offline na prática, e os gates que o exercitam continuam
determinísticos. Quando o primeiro agente declarar, a composição daquele agente passa a depender
do serviço — e é aí que o cache e a degradação suave abaixo importam.

QUANDO A REDE ACONTECE. `agentdefs` compõe no import, e fazer I/O de rede em import time faria o
app não subir quando o Azure estivesse fora. Então a resolução é preguiçosa e cacheada: a primeira
composição que precisar de skill busca, as seguintes reusam. Falha de rede NÃO derruba o agente —
ele roda sem a skill, e o aviso vai para o log. Um agente sem skill responde pior; um agente que
não sobe não responde nada.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile

logger = logging.getLogger(__name__)

# Teto por skill. O conteúdo vira instrução do modelo, e instrução longa demais come a janela de
# contexto que a pergunta do usuário precisa.
MAX_SKILL_CHARS = 20_000

# O frontmatter YAML do agentskills.io (`---\nname: …\ndescription: …\n---`) é metadado do
# ARQUIVO, não instrução para o modelo. Sai antes de compor: deixá-lo gastaria contexto e faria o
# modelo ler "name: revisar-pr" como conteúdo da skill.
_FRONTMATTER = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)


def _strip_frontmatter(texto: str) -> str:
    return _FRONTMATTER.sub("", texto, count=1).lstrip()


# Cache de processo: skill resolvida uma vez por vida do container. Promover uma versão nova exige
# reiniciar — que é o mesmo contrato do resto do `agentdefs`, e o mesmo do mount do Azure Files.
_cache: dict[str, str | None] = {}


def _extract_markdown(zip_bytes: bytes) -> str:
    """O texto da skill, a partir do ZIP.

    `SKILL.md` na raiz é o formato agentskills.io. Se não houver, junta os markdown que existirem —
    uma skill empacotada de outro jeito ainda tem conteúdo útil, e recusá-la por causa do nome do
    arquivo seria rigor sem propósito.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        nomes = z.namelist()
        preferidos = [n for n in nomes if n.lower().endswith("skill.md")]
        alvos = preferidos or [n for n in nomes if n.lower().endswith((".md", ".markdown"))]
        partes = []
        for nome in alvos[:20]:
            try:
                partes.append(z.read(nome).decode("utf-8", errors="replace"))
            except Exception as exc:  # noqa: BLE001 — um arquivo ilegível não invalida os outros
                logger.debug("arquivo '%s' da skill ignorado: %s", nome, exc)
                continue
    return "\n\n".join(_strip_frontmatter(p).strip() for p in partes if p.strip())


def fetch_skill(name: str) -> str | None:
    """O conteúdo da versão default de uma skill, ou None se não deu.

    None e não exceção: a skill é um reforço do prompt, não um requisito dele. Derrubar o agente
    porque uma skill não baixou trocaria uma degradação por uma indisponibilidade.
    """
    if name in _cache:
        return _cache[name]

    texto: str | None = None
    try:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        from app.modules.tenancy.public import tenant_config

        client = AIProjectClient(
            endpoint=tenant_config().foundry_project_endpoint,
            credential=DefaultAzureCredential(),
            allow_preview=True,
        )
        try:
            # `download` devolve um iterador de bytes da versão DEFAULT — que é o que faz promover
            # uma versão valer sem tocar em código.
            blob = b"".join(client.beta.skills.download(name))
            texto = _extract_markdown(blob)[:MAX_SKILL_CHARS] or None
        finally:
            import contextlib

            with contextlib.suppress(Exception):
                client.close()
    except Exception as exc:  # noqa: BLE001 — sem skill o agente ainda responde
        logger.warning("skill '%s' não pôde ser carregada (%s); o agente segue sem ela", name, exc)

    _cache[name] = texto
    return texto


def compose_skills(names: list[str]) -> str:
    """As skills pedidas, prontas para entrar no prompt.

    Cada uma vem rotulada com o nome. O rótulo não é enfeite: quando duas skills se contradizem,
    quem for depurar precisa saber de qual veio cada regra — e o modelo trata melhor blocos
    nomeados que um texto corrido sem origem.
    """
    blocos = []
    for nome in names:
        conteudo = fetch_skill(nome)
        if conteudo:
            blocos.append(f"### Skill: {nome}\n\n{conteudo}")
    if not blocos:
        return ""
    return (
        "\n\n## Skills\n\n"
        "As seções abaixo são skills publicadas neste projeto. Trate-as como instruções suas.\n\n"
        + "\n\n".join(blocos)
    )


def clear_cache() -> None:
    """Esquece o que foi baixado. Existe para o teste, e para um eventual recarregamento."""
    _cache.clear()
