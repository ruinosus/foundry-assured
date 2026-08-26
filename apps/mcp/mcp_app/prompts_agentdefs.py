"""Os prompts do produto, publicados no protocolo — DERIVADOS da fonte única, nunca copiados.

ESTE ARQUIVO NÃO CONTÉM PROMPT NENHUM, E ISSO É O PONTO. A fonte de cada instrução é um
documento AgentSchema `PromptAgent` em `apps/backend/agents/assured/` (ADR-013/015), lido pelo
reader oficial da Microsoft e composto — persona → instructions → additionalInstructions →
guardrails — por `app.modules.agentdefs`. Aqui só se pergunta a ele o que existe e se registra
cada resposta como um `@mcp.prompt`.

Escrever o texto de um prompt (ou até só a LISTA de nomes) dentro deste módulo criaria a
segunda verdade que a SEGUNDA MÁXIMA do projeto proíbe: duas listas divergem no primeiro item
novo, e a divergência não dá erro — só faz o cliente MCP anunciar um agente que não existe, ou
esconder um que existe. `tests/prompts_mirror_test.py` é o gate que prova a derivação, no mesmo
espírito de `tests.registry.domain_registry_test` do monolito.

POR QUE `composed_agents()` E NÃO AS CONSTANTES. `agentdefs.public` também exporta
`TRIAGE_INSTRUCTIONS`, `RESOLVE_INSTRUCTIONS` e companhia — mas essas constantes SÃO uma lista
escrita à mão (o dicionário `_AGENT_FOR_CONSTANT`), e ler dali obrigaria este arquivo a
escolher quais entram. `composed_agents()` existe justamente para o publicador não declarar
lista própria: ela devolve TODO agente do escopo, com o texto COMPOSTO (o que o backend roda) e
a descrição do documento. É a mesma função que `cli/provision_agents.py` usa para publicar no
Foundry — o que mantém o MCP e o Foundry mostrando o mesmo conjunto.

PAPEL DO ENTRA TAMBÉM AQUI. Um prompt é superfície como uma tool é: sem `auth=`, ele apareceria
no `prompts/list` de qualquer chamador autenticado, inclusive de quem não tem papel nenhum no
app. O gate é o mesmo `require_any_role` da tool — any-of, não all-of (ver `mcp_app/auth.py`).
"""

from __future__ import annotations

from fastmcp import FastMCP

from app.modules.agentdefs.public import composed_agents
from mcp_app.auth import require_any_role

#: Os papéis que podem LER as instruções publicadas. Igual ao da tool de leitura de propósito:
#: quem pode perguntar pode ver com que instruções o assistente responde.
PAPEIS_DE_LEITURA = ("Reader", "Author", "Approver", "Admin")


def prompt_ids() -> tuple[str, ...]:
    """Os ids que este módulo publica — derivados, em ordem estável.

    Existe para o gate espelhado poder comparar sem reconstruir o servidor, e para `register`
    e o gate lerem a MESMA função (se lessem fontes diferentes, o gate ficaria verde sobre uma
    lista que ninguém publica).
    """
    return tuple(sorted(composed_agents()))


def _prompt(texto: str):
    """Fecha o texto composto numa função sem argumentos — que é o que o `@mcp.prompt` publica.

    Sem argumentos de propósito: um `PromptAgent` do AgentSchema é uma instrução completa, não
    um template com lacunas. Inventar parâmetros aqui seria inventar contrato que o documento
    não tem.
    """

    def instrucoes() -> str:
        return texto

    return instrucoes


def register(mcp: FastMCP) -> None:
    """Publica um prompt por agente do escopo. Falha alto se o escopo vier vazio.

    Escopo vazio significa que os documentos não foram encontrados (ou que o `AGENTS_DIR` da
    ADR-014 aponta para lugar errado) — e um servidor que anuncia zero prompts em silêncio é
    pior que um que se recusa a subir, porque o cliente não tem como distinguir "não há" de
    "não carregou".
    """
    agentes = composed_agents()
    if not agentes:
        raise RuntimeError(
            "escopo de agentes vazio — nenhum documento AgentSchema foi composto "
            "(ver app.modules.agentdefs e ADR-013/014)"
        )
    for nome in sorted(agentes):
        texto, descricao = agentes[nome]
        mcp.prompt(
            _prompt(texto),
            name=nome,
            description=descricao or f"Instruções compostas do agente {nome}.",
            tags={"agentdefs", "read"},
            auth=require_any_role(*PAPEIS_DE_LEITURA),
        )
