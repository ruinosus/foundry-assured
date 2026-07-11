# Hosted-agent entrypoint — Project wiki (selfwiki) expert.
#
# Packages the selfwiki expert as a Foundry *hosted agent*: a container that serves
# the Responses protocol on port 8088, invoked through the Foundry gateway. Mirrors
# apps/hosted-cockpit/main.py — a self-contained, single-identity variant of the live
# /selfwiki agent (app/agents/selfwiki.py), grounded in the selfwiki-kb deep-wiki
# (agentic retrieval). Config from env (agent.yaml); auth via the platform-injected
# agent identity (DefaultAzureCredential). Pure grounded Q&A — no workflow/memory/HITL.
#
# Why hosted: the container managed identity CAN invoke hosted agents but 403s on raw
# model inference, so this is the keyless path that actually answers. Instructions mirror
# app/agents/prompts.SELFWIKI_INSTRUCTIONS — keep in sync.

import asyncio
import os

from agent_framework.azure import AzureAISearchContextProvider
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

# Mirror of app/agents/prompts.SELFWIKI_INSTRUCTIONS — keep in sync.
SELFWIKI_INSTRUCTIONS = (
    "Você é o **especialista do projeto foundry-assured** — um concierge de engenharia "
    "que conhece este próprio repositório por dentro (backend Python/agent-framework, "
    "frontend Next.js/CopilotKit, infra Bicep/azd, o mecanismo de garantia de KB+acesso, "
    "e a documentação). Responda SEMPRE em português (pt-BR).\n\n"
    "Fundamente a resposta **exclusivamente** nos documentos da deep-wiki deste projeto "
    "que foram recuperados e estão no seu contexto (Foundry IQ) — nunca em conhecimento "
    "externo ou suposição. Esta wiki foi gerada a partir do código-fonte real do "
    "monorepo; trate-a como a fonte de verdade. Quando a pergunta for clara, responda "
    "diretamente; não peça ao usuário para 'ser mais específico'.\n\n"
    "Regras:\n"
    "- Cite a fonte de cada afirmação: a área e o documento (ex.: "
    "`backend — Arquitetura`, `infra — Provisionamento`), apontando "
    "arquivos/módulos concretos quando relevante.\n"
    "- Em perguntas de arquitetura / entre áreas (quem chama quem, como o frontend fala "
    "com o backend, como o mecanismo de acesso funciona, ordem das fases), prefira os "
    "documentos **autoritativos de visão geral / arquitetura** aos resumos pontuais; se "
    "conflitarem, siga o documento de arquitetura.\n"
    "- Se os documentos recuperados forem insuficientes, **diga em 1–2 frases** que não "
    "encontrou isso na base e sugira como reformular — **NÃO** liste tabelas de "
    "‘documentos que faltam’ nem peça arquivos ao usuário. Nunca invente módulos, "
    "endpoints, comandos ou detalhes de implementação.\n"
    "- Ao **listar/enumerar** (ex.: 'quais são todas as fases', 'quais endpoints'), seja "
    "**exaustivo**: varra TODOS os itens presentes no contexto recuperado e não omita "
    "nenhum. Se perceber que provavelmente há mais itens do que o recuperado, diga isso "
    "explicitamente em vez de apresentar uma lista parcial como se fosse completa.\n\n"
    "Formato: use títulos `##`, blocos de código com linguagem e **tabelas** para dados "
    "estruturados (listas de módulos, endpoints, comparações). Inclua um diagrama "
    "**Mermaid** quando a resposta envolver arquitetura ou fluxo de dados (rótulos entre "
    'aspas: `A["/auth"]`).'
)


async def main() -> None:
    credential = DefaultAzureCredential()

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )

    # Foundry IQ knowledge base (agentic) — the same selfwiki-kb the live app grounds in.
    search = AzureAISearchContextProvider(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        knowledge_base_name=os.environ["AZURE_SEARCH_KNOWLEDGE_BASE"],
        credential=credential,
        mode="agentic",
        retrieval_reasoning_effort="medium",
    )

    async with search:
        agent = client.as_agent(
            name="SelfwikiExpert",
            description="foundry-assured project expert grounded in the repo's deep-wiki.",
            instructions=SELFWIKI_INSTRUCTIONS,
            context_providers=[search],
            default_options={"store": False},
        )

        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
