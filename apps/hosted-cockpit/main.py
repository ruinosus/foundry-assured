# Hosted-agent entrypoint — Cockpit expert (Phase C, second domain).
#
# Packages the Cockpit expert as a Foundry *hosted agent*: a container that serves
# the Responses protocol on port 8088, invoked through the Foundry gateway.
# agent-framework-foundry-hosting's ResponsesHostServer is the bridge.
#
# A self-contained, single-identity variant of the live /cockpit agent
# (app/agents/cockpit.py): same Foundry IQ knowledge base (cockpit-kb, agentic
# retrieval) grounding, but config comes from env (declared in agent.yaml / injected
# by the platform) and auth is the platform-injected agent identity via
# DefaultAzureCredential. Pure grounded Q&A — no workflow, memory or HITL.
# APIs mirror app/agents/cockpit.py; verified against agent-framework 1.9.0.

import asyncio
import os

from agent_framework.azure import AzureAISearchContextProvider
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

# Mirror of app/agents/prompts.COCKPIT_INSTRUCTIONS — keep in sync. Microsoft's Foundry
# IQ pattern for KB-grounded Q&A: grounding from the search context provider (with
# citations), answering discipline in the instructions, no consume-side Agent Skill.
COCKPIT_INSTRUCTIONS = (
    "Você é um especialista na plataforma **Cockpit** (Avanade AAP). Responda SEMPRE em "
    "português (pt-BR).\n\n"
    "Fundamente a resposta **exclusivamente** nos documentos da base de conhecimento do "
    "Cockpit que foram recuperados e estão no seu contexto (Foundry IQ) — nunca em "
    "conhecimento externo ou suposição. Quando a pergunta for clara, responda "
    "diretamente; não peça ao usuário para 'ser mais específico'.\n\n"
    "Regras:\n"
    "- Cite a fonte de cada afirmação: o componente e o documento (ex.: "
    "`cockpit-portal-api v2.1.1 — Arquitetura`), indicando a versão quando relevante.\n"
    "- Em perguntas de arquitetura / entre componentes (quem persiste o quê, quem chama "
    "quem, hierarquias, depreciações), prefira os documentos **autoritativos de "
    "PLATAFORMA/ARQUITETURA** aos resumos de componentes individuais; se conflitarem, "
    "siga o documento de arquitetura.\n"
    "- Se os documentos recuperados forem insuficientes, **diga que não sabe** e aponte "
    "o que falta — nunca invente componentes, versões, endpoints ou detalhes.\n\n"
    "Formato: use títulos `##`, blocos de código com linguagem e **tabelas** para dados "
    "estruturados (listas de componentes, endpoints, comparações). Inclua um diagrama "
    '**Mermaid** quando a resposta envolver arquitetura ou fluxo de dados (rótulos entre '
    'aspas: `A["/auth"]`).'
)


async def main() -> None:
    credential = DefaultAzureCredential()

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )

    # Foundry IQ knowledge base (agentic) — the same cockpit-kb the live app grounds in.
    search = AzureAISearchContextProvider(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        knowledge_base_name=os.environ["AZURE_SEARCH_KNOWLEDGE_BASE"],
        credential=credential,
        mode="agentic",
    )

    async with search:
        agent = client.as_agent(
            name="CockpitExpert",
            description="Avanade Cockpit platform expert grounded in the Cockpit knowledge base.",
            instructions=COCKPIT_INSTRUCTIONS,
            context_providers=[search],
            # Foundry hosting manages conversation history; don't double-store.
            default_options={"store": False},
        )

        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
