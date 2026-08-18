"""Triagem de plantão em **deepagents** — o gêmeo do `oncall`, para comparar na prática.

POR QUE UM DOMÍNIO NOVO E NÃO UMA TROCA. A pesquisa recomendou não adotar, e o dono do projeto
decidiu testar mesmo assim — decisão dele, e a comparação empírica é o único jeito de fechar a
questão. Substituir o `oncall` apagaria o termo de comparação: as duas implementações resolvem o
MESMO problema, com as MESMAS tools e o MESMO documento de prompt, e a diferença fica isolada no
harness. Isso é o que torna a comparação legível.

O ARGUMENTO QUE MUDOU MINHA AVALIAÇÃO, e é técnico: skill não é só o `SKILL.md`. Um bundle traz
`scripts/` e `references/`, e o direct injection que escrevi (`agentdefs/internal/skill_injection`)
extrai apenas os markdown — um `scripts/rollback.py` dentro da skill nunca chega ao modelo. O
`SkillsMiddleware` do deepagents entrega o bundle inteiro via filesystem, com progressive
disclosure: o prompt leva nome e descrição, e o modelo lê o conteúdo sob demanda. São entregas
diferentes, não a mesma coisa com nome diferente.

O QUE ESTE ARQUIVO MANTÉM IGUAL AO `oncall`, de propósito:
  * as duas tools, com o mesmo comportamento;
  * `interrupt_on` idêntico — approve/edit/reject na tool de escrita;
  * o prompt, vindo do mesmo documento AgentSchema (`agents/helpdesk/oncall.yaml`);
  * `DefaultAzureCredential` com token provider (RULE #2 sobrevive à troca de harness).

O QUE DIFERE, e é o que está sendo medido: o harness. `create_deep_agent` empilha filesystem,
subagentes, summarization e skills sobre o `create_agent` que o `oncall` usa direto.

O RUBRIC É O GANHO QUE JUSTIFICA A APOSTA. `RubricMiddleware` faz o agente avaliar a própria
resposta contra critérios e REESCREVER quando falha — self-eval em runtime, não em CI. O `eval/`
deste repositório já fixa esses critérios, mas depois do fato: um caso vermelho no CI diz que o
agente regrediu, não impede a resposta ruim de chegar ao usuário. O rubric age antes.

Ele só atua quando o estado da invocação traz uma `rubric` — sem ela, os dois hooks retornam sem
tocar em nada. Por isso entra incondicionalmente na pilha: ligado, não custa; desligado, não pesa.

O QUE DESLIGAMOS, e por quê. `execute` (shell) e o subagente de propósito geral saem: este domínio
classifica severidade e escala incidente. Um agente que abre chamado não precisa de shell, e o
próprio README do deepagents avisa que o modelo dele é "trust the LLM". Manter ligado o que não se
usa amplia superfície de ataque sem contrapartida.
"""

from __future__ import annotations

from typing import Annotated

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import tool

from app.modules.agentdefs.public import ONCALL_INSTRUCTIONS
from app.modules.hitl.public import recording_hitl
from app.modules.tickets.public import create_ticket
from app.shared.settings import settings

# O MESMO contrato de HITL do `oncall`: leitura flui, escrita espera, e o aprovador pode editar.
# Divergir aqui inviabilizaria a comparação — a diferença tem que ficar no harness, não nas regras.
INTERRUPT_ON = {
    "escalate_incident": {"allowed_decisions": ["approve", "edit", "reject"]},
}


@tool
def assess_severity(symptom: Annotated[str, "What the user reported."]) -> str:
    """Classify an incident's severity from its symptom. Read-only: never stops for approval."""
    lowered = symptom.lower()
    # Palavras nas DUAS línguas, pelo mesmo motivo do gêmeo: uma lista só em inglês classificava
    # "o checkout está fora do ar" como sev3 — cega para o idioma de quem escreve.
    if any(
        w in lowered
        for w in (
            "fora do ar", "indisponível", "caiu", "perda de dados", "vazamento", "invasão",
            "down", "outage", "data loss", "breach",
        )
    ):
        return "sev1 — indisponibilidade para o usuário ou risco a dados; escale agora"
    if any(
        w in lowered
        for w in (
            "lento", "lentidão", "degradado", "taxa de erro", "intermitente", "instável",
            "slow", "degraded", "error rate", "flaky",
        )
    ):
        return "sev2 — degradado mas servindo; escale se persistir"
    return "sev3 — sem impacto observado ao usuário; tratar em horário comercial"


@tool
def escalate_incident(
    summary: Annotated[str, "One-line incident summary."],
    severity: Annotated[str, "sev1 | sev2 | sev3."],
    # O PORQUÊ como ARGUMENTO da tool: o card do HITL do LangGraph mostra os argumentos da
    # chamada, então o motivo chega ao aprovador pelo caminho que já existe — e, quando ele
    # CORRIGE a escalação, corrige o motivo junto. O gêmeo `oncall` recebe o mesmo campo, porque
    # os dois existem para serem comparados: uma diferença de contrato entre eles invalidaria a
    # comparação.
    reason: Annotated[str, "One sentence on what led you to escalate — read by the human approver before they approve."] = "",
) -> str:
    """Open an incident ticket. WRITE: stops for human approval before running."""
    ticket = create_ticket(f"[{severity}] {summary}", domain="deepcall")
    return f'ticket {ticket["id"]} opened: {ticket["summary"]}'


class _AlwaysRubric(AgentMiddleware):
    """Injeta a rubrica no estado antes do agente rodar — é o que liga o self-eval sem depender
    do cliente.

    O `RubricMiddleware` só age quando o estado da invocação traz `rubric`. Deixar isso a cargo de
    quem chama significaria que o AG-UI teria de mandá-la em cada mensagem — e o CopilotKit não
    manda, porque `rubric` não é campo do protocolo. O agente então rodaria SEM autoavaliação e
    ninguém notaria: não há erro, só a ausência silenciosa do que se queria medir.

    `before_agent` devolve um patch de estado, então a rubrica entra por aqui e vale para toda
    invocação. Se o cliente mandar a própria, ela ganha — o default não deve sobrescrever escolha
    explícita de quem chama.
    """

    name = "always_rubric"

    def before_agent(self, state, runtime):
        if state.get("rubric"):
            return None
        return {"rubric": ONCALL_RUBRIC}


def build_deepcall_graph():
    """Um deep agent compilado — mesma forma de retorno do `oncall`.

    `create_deep_agent` devolve um `CompiledStateGraph`, exatamente como `create_agent`. Por isso
    o registry monta os dois pelo mesmo caminho (`add_langgraph_fastapi_endpoint`) sem nenhuma
    adaptação: o protocolo é a costura, não uma abstração que mantemos (ADR-020).

    O checkpointer continua obrigatório: o HITL interrompe o grafo, e sem estado persistido não há
    para onde retomar.
    """
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from deepagents import create_deep_agent
    from deepagents.middleware.rubric import RubricMiddleware
    from langchain_openai import AzureChatOpenAI
    from langgraph.checkpoint.memory import InMemorySaver

    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
    )
    # O MESMO `record_usage` do resto do backend, pelo ponto canônico do LangChain. Estes dois
    # domínios não passam pela fábrica de cliente do agent-framework, então o `ChatMiddleware` que
    # mede todo o resto não os alcança — ficavam inteiramente fora da contabilidade. `callbacks` é
    # a superfície de observabilidade do próprio LangChain (ADR-020: cada framework do jeito dele),
    # e o destino é compartilhado: uma contabilidade, dois pontos de entrada.
    from app.modules.conversations.public import usage_callback

    model = AzureChatOpenAI(
        azure_deployment=settings.oncall_model,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        azure_ad_token_provider=token_provider,
        callbacks=[usage_callback()],
    )

    return create_deep_agent(
        model=model,
        tools=[assess_severity, escalate_incident],
        system_prompt=ONCALL_INSTRUCTIONS,
        # Mesmo contrato do gêmeo. `interrupt_on` é açúcar: por baixo é o
        # `HumanInTheLoopMiddleware` do langchain, o mesmo que o `oncall` instancia à mão.
        # `interrupt_on=` NÃO é passado de propósito: com ele, o `create_deep_agent` monta o
        # `HumanInTheLoopMiddleware` DELE por dentro (graph.py:876) e a decisão passa por uma
        # máquina que não registra. Sem ele, o middleware que entra é o nosso — mesma classe do
        # LangGraph, só observando —, e o gêmeo passa a produzir a mesma trilha que o `oncall`.
        # Sem isso, comparar os dois harnesses pela trilha seria impossível justamente na métrica
        # que mais importa: quem aprovou o quê.
        #
        # A ORDEM IMPORTA: `_AlwaysRubric` vem primeiro para o estado já ter a rubrica quando o
        # `RubricMiddleware` decidir se atua. Invertido, ele leria o estado sem rubrica, sairia
        # sem fazer nada, e o self-eval nunca aconteceria — falha silenciosa, sem erro nenhum. O
        # HITL vai por último, na mesma posição em que o `deepagents` o acrescentava.
        middleware=[
            _AlwaysRubric(),
            RubricMiddleware(model=model, on_evaluation=_log_evaluation),
            recording_hitl(INTERRUPT_ON, "deepcall"),
        ],
        checkpointer=InMemorySaver(),
    )


#: A rubrica deste domínio — os MESMOS critérios que `agents/helpdesk/eval-cases/oncall-contract`
#: fixa no CI. A diferença é quando eles agem: o gate reprova depois, o rubric corrige antes.
#: Passada no estado da invocação (`{"messages": [...], "rubric": ONCALL_RUBRIC}`).
ONCALL_RUBRIC = """A resposta será aceita apenas se:
1. A severidade foi classificada com `assess_severity` ANTES de qualquer escalação.
2. Não pede confirmação em texto para escalar — a aprovação humana acontece fora do agente.
3. Não afirma que um chamado foi aberto sem que a ferramenta tenha retornado um ticket.
4. Está no idioma de quem perguntou."""


def _log_evaluation(evaluation) -> None:
    """Registra o veredito do grader.

    Existe porque a alternativa é o rubric agir em silêncio: quando ele reescreve, quem lê o log
    precisa saber que a primeira resposta foi reprovada e por quê — do contrário a diferença entre
    os dois harnesses vira anedota em vez de medição.

    `RubricEvaluation` é um TypedDict, não um objeto. Escrevi `getattr(evaluation, "status")` de
    início e o log saiu com "status=?" em toda invocação — sem erro, só vazio. Os nomes vieram de
    `__annotations__`, não de suposição: grading_run_id, iteration, result, explanation, criteria.
    """
    import logging

    logging.getLogger(__name__).info(
        "rubric: iteração=%s resultado=%s · %s",
        evaluation.get("iteration"),
        evaluation.get("result"),
        str(evaluation.get("explanation") or "")[:280],
    )


def deepcall_configured() -> bool:
    """Mesma condição do gêmeo: sem endpoint do Azure OpenAI não há o que montar."""
    return bool(settings.azure_openai_endpoint and settings.oncall_model)
