"""Path A da ADR-022 — rascunhar um agente que ainda não existe.

O QUE ESTE MÓDULO NÃO FAZ, e é o ponto inteiro: **não publica**. Ele devolve um rascunho ao
chamador e não guarda nada. Publicar continua sendo a rota de escrita já existente
(`POST /foundry/agents/{name}/versions`), que exige Admin. `tests/architecture/proposer_read_only_test.py`
verifica isso a cada push — a fronteira precisa estar em código, não em intenção, porque o risco
real é uma edição futura que acrescenta a publicação "para economizar um clique".

POR QUE ELE É ÚTIL, e não só um prompt bonito: o CATÁLOGO REAL vai no contexto. Propor um
assistente sem saber que existe uma base `helpdesk-kb` e uma skill `wiki-page-writer` produz texto
genérico; sabendo, o rascunho diz qual base usar e qual skill anexar. É a mesma diferença que o
`assist.py` já provou para um campo — aqui vale para o formulário inteiro.

E ele responde a pergunta que ninguém faz sozinho: **o que já existe e cobre parte disso?** Um
propositor que só sabe criar leva a organização a acumular agentes quase iguais. Por isso o
rascunho tem um campo `reuse` que aponta os agentes existentes que já resolvem parte da
necessidade — inclusive quando a resposta honesta é "não crie nada, use aquele ali".
"""

from __future__ import annotations

import contextlib
import inspect
import json

from app.modules.tenancy.public import tenant_config

#: Teto do que aceitamos de volta. Um rascunho é um formulário, não um documento.
MAX_INSTRUCOES = 6000

_SISTEMA = (
    "Você propõe a configuração de um agente no Azure AI Foundry a partir de uma necessidade de "
    "negócio. Responda APENAS com um objeto JSON, sem cercas de código e sem texto em volta, com "
    "as chaves: name (identificador curto em minúsculas, com hifens, sem acento), display_name, "
    "description (uma frase), instructions (o prompt do agente: o que fazer e o que não fazer, "
    "concreto e curto), knowledge (lista de nomes de bases DENTRE as disponíveis), skills (lista "
    "de nomes de skills DENTRE as disponíveis), reuse (lista de objetos {name, why} com agentes "
    "JÁ EXISTENTES que cobrem parte da necessidade) e rationale (uma frase explicando a escolha). "
    "Só cite bases, skills e agentes que constem das listas fornecidas — inventar um nome faz o "
    "rascunho falhar na publicação. Se o que existe já resolve, diga isso em rationale e deixe "
    "instructions curto."
)


def build_prompt(need: str, catalogo: dict) -> str:
    """Monta o pedido. PURA — testável offline, sem rede nem credencial.

    O catálogo entra como FATO disponível, não como ordem, igual ao `assist.py`: o modelo decide
    o que usar. A necessidade da pessoa entra ROTULADA como pedido dela — é conteúdo de usuário,
    e o rótulo mantém essa distinção visível no prompt.
    """
    need = (need or "").strip()
    if not need:
        raise ValueError("Descreva a necessidade que o assistente deve atender.")

    partes = [f"Necessidade descrita por quem pediu: {need[:2000]}"]

    for rotulo, chave in (
        ("Agentes já publicados neste projeto", "agents"),
        ("Bases de conhecimento disponíveis", "knowledge"),
        ("Skills disponíveis", "skills"),
        ("Toolboxes disponíveis", "toolboxes"),
    ):
        itens = [str(x) for x in (catalogo.get(chave) or [])][:40]
        # Dizer que a lista está VAZIA importa: sem isso o modelo assume que existe algo e
        # inventa um nome, e o rascunho falha só na hora de publicar.
        partes.append(f"{rotulo}: " + (", ".join(itens) if itens else "(nenhum)") + ".")

    return "\n\n".join(partes)


def parse_draft(texto: str, catalogo: dict) -> dict:
    """O JSON do modelo, validado contra o catálogo. PURA.

    Nome de base, skill ou agente que não existe é REMOVIDO e listado em `dropped`. Deixar passar
    produziria um rascunho que parece pronto e falha na publicação; remover em silêncio faria a
    pessoa achar que pediu algo que o rascunho não tem. As duas coisas erram — dizer o que caiu é
    a terceira opção.
    """
    bruto = (texto or "").strip()
    # O modelo às vezes devolve cercado por ```json apesar da instrução. Tirar a cerca é mais
    # barato que uma segunda chamada.
    if bruto.startswith("```"):
        bruto = bruto.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        dados = json.loads(bruto)
    except Exception as exc:
        raise ValueError(f"O modelo não devolveu um rascunho legível: {exc}") from exc
    if not isinstance(dados, dict):
        # ValueError, não TypeError: a API mapeia ValueError→400. Um JSON de forma errada é
        # falha do pedido, não do tipo da chamada — TypeError viraria 500 e acusaria o serviço.
        raise ValueError("O modelo não devolveu um objeto de rascunho.")  # noqa: TRY004

    caidos: list[str] = []

    def filtrar(valores, disponiveis: set[str]) -> list[str]:
        saida = []
        for v in valores or []:
            nome = str(v).strip()
            if nome in disponiveis:
                saida.append(nome)
            elif nome:
                caidos.append(nome)
        return saida

    bases = {str(x) for x in (catalogo.get("knowledge") or [])}
    skills = {str(x) for x in (catalogo.get("skills") or [])}
    agentes = {str(x) for x in (catalogo.get("agents") or [])}

    reuse = []
    for item in dados.get("reuse") or []:
        if not isinstance(item, dict):
            continue
        nome = str(item.get("name") or "").strip()
        if nome in agentes:
            reuse.append({"name": nome, "why": str(item.get("why") or "")[:300]})
        elif nome:
            caidos.append(nome)

    return {
        "name": str(dados.get("name") or "")[:63],
        "display_name": str(dados.get("display_name") or "")[:120],
        "description": str(dados.get("description") or "")[:512],
        "instructions": str(dados.get("instructions") or "")[:MAX_INSTRUCOES],
        "knowledge": filtrar(dados.get("knowledge"), bases),
        "skills": filtrar(dados.get("skills"), skills),
        "reuse": reuse,
        "rationale": str(dados.get("rationale") or "")[:512],
        # O que o modelo citou e não existe. Sobe na resposta, e a tela mostra.
        "dropped": caidos,
        # Marca o que isto É. A tela lê para nunca apresentar um rascunho como recurso criado.
        "published": False,
    }


def _nomes(resultado, chave: str = "") -> list[str]:
    """Os nomes, seja qual for a forma que o catálogo devolveu.

    As quatro listagens NÃO têm a mesma forma, e isto custou um rascunho errado antes de virar
    código: `list_agents`/`list_skills`/`list_toolboxes` devolvem LISTA de dicts, e
    `list_knowledge` devolve DICT `{"bases": [...], "sources": [...]}`. Assumir lista para todas
    fazia as bases sumirem — e o propositor rascunhava um assistente fundamentado sem base
    nenhuma, que é o pior resultado possível para um produto cujo diferencial é citar a fonte.
    """
    itens = resultado.get(chave, []) if isinstance(resultado, dict) else resultado
    saida = []
    for x in itens or []:
        nome = x.get("name") if isinstance(x, dict) else x
        if nome:
            saida.append(str(nome))
    return saida


def catalog_snapshot() -> dict:
    """O catálogo do tenant, só os nomes. LEITURA — nenhuma função de escrita é importada aqui.

    Falha NÃO vira lista vazia em silêncio: "não há base" e "não consegui listar as bases" levam
    o modelo a rascunhos opostos, e o segundo caso precisa aparecer na tela. O motivo sobe em
    `errors` e o rascunho continua — propor com catálogo parcial ainda é melhor que uma tela de
    erro, desde que a lacuna esteja dita.
    """
    from app.modules.foundry.public import (
        list_agents,
        list_knowledge,
        list_skills,
        list_toolboxes,
    )

    catalogo: dict = {"errors": []}
    for campo, fn, chave in (
        ("agents", list_agents, ""),
        ("knowledge", list_knowledge, "bases"),
        ("skills", list_skills, ""),
        ("toolboxes", list_toolboxes, ""),
    ):
        try:
            catalogo[campo] = _nomes(fn(), chave)
        except Exception as exc:  # noqa: BLE001 — um catálogo ilegível não impede rascunhar
            catalogo[campo] = []
            catalogo["errors"].append(f"{campo}: {type(exc).__name__}")
    return catalogo


async def propose_agent(need: str, language: str = "") -> dict:
    """O rascunho. NÃO PUBLICA — devolve para uma pessoa decidir."""
    catalogo = catalog_snapshot()
    prompt = build_prompt(need, catalogo)

    from azure.ai.projects.aio import AIProjectClient
    from azure.identity.aio import DefaultAzureCredential

    cfg = tenant_config()
    credential = DefaultAzureCredential()
    proj = AIProjectClient(
        endpoint=cfg.foundry_project_endpoint, credential=credential, allow_preview=True
    )
    try:
        client = proj.get_openai_client()
        client = await client if inspect.isawaitable(client) else client

        sistema = _SISTEMA + (f" Escreva os textos em {language}." if language else "")
        # Mesma forma que `assist.py` e `grounded`: `input` é o texto, `instructions` é o papel.
        # A Responses API recusa a lista estilo chat-completions.
        resposta = await client.responses.create(
            model=cfg.foundry_model, input=prompt, instructions=sistema
        )
        rascunho = parse_draft(getattr(resposta, "output_text", "") or "", catalogo)
        rascunho["catalog"] = {k: len(v) for k, v in catalogo.items()}
        return rascunho
    finally:
        with contextlib.suppress(Exception):
            await proj.close()
        with contextlib.suppress(Exception):
            await credential.close()
