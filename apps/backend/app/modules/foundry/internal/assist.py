"""Assistência do wizard — redigir e revisar campo, com o catálogo real como contexto.

O QUE ISTO É, e o que NÃO é. O padrão de um projeto anterior manda o pedido ao CHAT, e quem escreve o campo
é o agente, pelo caminho normal — o que evita criar um segundo caminho de escrita. Aqui não há
chat ao lado do wizard, então a sugestão volta como PROPOSTA: a tela mostra, a pessoa aceita ou
descarta, e nada é gravado sem esse gesto. Não é o mesmo desenho, mas preserva a propriedade que
importa — **o texto só entra no campo por decisão humana**.

O QUE FAZ DIFERENÇA NA QUALIDADE: o catálogo real vai no contexto. Sugerir instruções para um
agente sem saber que existe uma base chamada `helpdesk-kb` produz texto genérico; sabendo, o
modelo escreve "consulte a base helpdesk-kb e cite o documento". A diferença entre um assistente
que ajuda e um que enfeita é exatamente essa.

MÁXIMA MAIOR: a chamada de modelo é a mesma que `modules/grounded` já usa —
`AIProjectClient.get_openai_client()` + `responses.create`. Nada de cliente novo.
"""

from __future__ import annotations

import contextlib
import inspect

from app.modules.tenancy.public import tenant_config

# O que o modelo pode fazer com um campo. Fechado de propósito: um verbo livre viraria uma via
# para instruções arbitrárias vindas do cliente.
ACOES = ("gerar", "revisar")

# Teto do que aceitamos de volta. Um campo de instruções não precisa de mais que isto, e o limite
# impede que uma resposta longa demais atravesse a tela.
MAX_SAIDA = 4000

_SISTEMA = (
    "Você ajuda alguém a preencher o formulário de criação de um agente ou skill no Azure AI "
    "Foundry. Responda APENAS com o texto do campo, sem preâmbulo, sem aspas em volta e sem "
    "explicar o que fez. Escreva no idioma do pedido. Seja concreto e curto: instruções de agente "
    "boas dizem o que fazer e o que não fazer, não descrevem o agente em terceira pessoa."
)


class AssistRejected(ValueError):
    """Pedido de assistência que não vamos atender, com o motivo."""


def build_prompt(acao: str, campo: str, valor: str, contexto: dict) -> str:
    """Monta o pedido. Pura — testável offline, sem rede.

    O catálogo entra como FATO disponível, não como ordem: o modelo decide se usa. Passar a lista
    de bases não obriga a citá-las; passar nada garante que ele não pode.
    """
    if acao not in ACOES:
        raise AssistRejected(f"Ação '{acao}' não é suportada. Use uma de: {', '.join(ACOES)}.")
    if not campo:
        raise AssistRejected("Informe qual campo está sendo preenchido.")

    partes = [f"Campo: {campo}."]
    if contexto.get("nome"):
        partes.append(f"O recurso se chama {contexto['nome']}.")
    if contexto.get("descricao"):
        partes.append(f"Descrição informada: {contexto['descricao']}")

    bases = contexto.get("bases") or []
    if bases:
        partes.append(
            "Bases de conhecimento disponíveis neste projeto: "
            + ", ".join(str(b) for b in bases[:20])
            + ". Se fizer sentido, oriente o agente a citar a fonte."
        )
    toolboxes = contexto.get("toolboxes") or []
    if toolboxes:
        partes.append("Toolboxes disponíveis: " + ", ".join(str(x) for x in toolboxes[:20]) + ".")

    if acao == "revisar":
        if not valor.strip():
            raise AssistRejected("Não há texto para revisar.")
        partes.append(f"Reescreva o texto abaixo, mantendo a intenção:\n\n{valor.strip()[:6000]}")
    else:
        partes.append("Escreva o conteúdo deste campo.")
        if contexto.get("instrucao"):
            # A instrução livre da pessoa entra como PEDIDO dela, rotulada — o modelo a trata
            # como conteúdo do usuário, que é o que ela é.
            partes.append(f"Pedido de quem está preenchendo: {str(contexto['instrucao'])[:500]}")

    return "\n\n".join(partes)


async def suggest(acao: str, campo: str, valor: str, contexto: dict, language: str = "") -> dict:
    """Devolve a sugestão para o campo. A tela mostra como proposta, nunca grava sozinha."""
    from azure.ai.projects.aio import AIProjectClient
    from azure.identity.aio import DefaultAzureCredential

    prompt = build_prompt(acao, campo, valor, contexto)
    cfg = tenant_config()

    credential = DefaultAzureCredential()
    proj = AIProjectClient(
        endpoint=cfg.foundry_project_endpoint, credential=credential, allow_preview=True
    )
    try:
        client = proj.get_openai_client()
        client = await client if inspect.isawaitable(client) else client

        sistema = _SISTEMA
        if language:
            sistema += f" Responda em {language}."

        # Mesma forma que `build_synthesis_kwargs` usa: `input` é o texto e `instructions` é o
        # papel — a Responses API recusa a lista estilo chat-completions (`[{role, content}]`)
        # com "Invalid value: ''", porque espera itens tipados. Seguir o que o repo já faz é mais
        # seguro que descobrir a forma por tentativa.
        resposta = await client.responses.create(
            model=cfg.foundry_model,
            input=prompt,
            instructions=sistema,
        )
        texto = (getattr(resposta, "output_text", "") or "").strip()
        return {"suggestion": texto[:MAX_SAIDA], "action": acao, "field": campo}
    finally:
        with contextlib.suppress(Exception):
            await proj.close()
        with contextlib.suppress(Exception):
            await credential.close()
