"""O assistente do wizard — um agente publicado, não uma constante em Python.

POR QUE ELE EXISTE COMO DOMÍNIO. O prompt que ajuda alguém a preencher o formulário de criação já
existia: era uma string dentro de `foundry/internal/assist.py`. Comportamento de produto que vive
só como configuração de código é exatamente o que a SEGUNDA MÁXIMA proíbe — a tela "Meus agentes"
mostrava dez, e esse décimo primeiro atendia sem nunca aparecer. Agora ele é um documento
AgentSchema (`agents/helpdesk/builder.yaml`) publicado como qualquer outro.

POR QUE `kind: tool` E NÃO `grounded`. O ponto do agente é chamar a tool `propose_field`, que é
uma tool de FRONTEND registrada pela tela. Medido: o adapter oficial
(`add_agent_framework_fastapi_endpoint`) repassa as tools do cliente ao agente
(`convert_agui_tools_to_agent_framework(input["tools"])` + `register_additional_client_tools`),
e o nosso caminho grounded NÃO — ele monta `{model, input, instructions, stream}` e nada mais.
Um builder grounded seria um agente que recebe a instrução de chamar uma ferramenta que ele nunca
enxerga.

NENHUMA TOOL DE SERVIDOR. A lista é vazia de propósito: tudo que este agente faz é propor texto,
e propor é a tool do cliente. Dar a ele uma tool de escrita transformaria o assistente do
formulário numa via de publicação sem revisão — o que a ADR-022 recusou e o gate do propositor
verifica do outro lado.
"""

from __future__ import annotations

from agent_framework import Agent

from app.modules.agentdefs.public import BUILDER_INSTRUCTIONS
from app.modules.grounded.public import PerRequestAgent
from app.shared.auth import credential_for_request


def build_builder_agent() -> Agent:
    """O assistente do formulário. Sem tools de servidor — só propõe."""
    from app.modules.foundry.public import chat_client

    client = chat_client(credential_for_request())
    return client.as_agent(
        name="AssistantBuilder",
        description="Ajuda a preencher o formulário de criação de agente, base e skill.",
        instructions=BUILDER_INSTRUCTIONS,
    )


#: Reconstruído a cada requisição, como o `platform`: a credencial é do usuário (OBO), e um
#: agente construído uma vez no boot atenderia todo mundo com a credencial de quem subiu o
#: processo.
builder_agent_proxy = PerRequestAgent(
    "builder",
    build_builder_agent,
    name="AssistantBuilder",
    description="Ajuda a preencher o formulário de criação de agente, base e skill.",
)
