"""O MESMO fluxo do helpdesk, montado a partir do YAML declarado em vez de código Python.

POR QUE ISTO EXISTE, e por que ficou parado meses. `agents/assured/workflows/helpdesk.yaml`
existe desde a ADR-021 com um comentário que se explica sozinho: *"existe para provar o runtime
ANTES de alguém construir um editor: um canvas que produz YAML que não roda é um editor
decorativo, e descobrir isso depois do editor pronto seria caro."*

O editor foi construído. O YAML nunca rodou. `usecases.write_flow` monta o fluxo com
`WorkflowFactory` para VALIDAR e joga o objeto fora — o canvas desenha um fluxo que ninguém
executa, e a promessa "declare o passo humano e ele vira um gate" era só uma frase.

O QUE FOI PRECISO ESCREVER: quase nada, e é esse o ponto. Medido no pacote instalado
(`agent_framework_declarative` 1.0.2):

    WorkflowFactory(agents=…).create_workflow_from_yaml(texto)  →  Workflow

e o `Workflow` que sai daí entra no MESMO `AgentFrameworkWorkflow` do adapter AG-UI que o fluxo
em Python já usa. O passo humano também é do runtime: `QuestionExecutor` e
`RequestExternalInputExecutor` chamam `ctx.request_info(...)`, e `request_info` é exatamente o
evento que o card de aprovação da tela já escuta. Não há adaptador entre os dois — é a mesma
cola, com outra origem para o grafo.

O QUE ESTE MÓDULO ACRESCENTA, e é a única coisa: o REGISTRO dos agentes. O YAML cita
`agent.name: TriageAgent`; quem sabe construir esse agente com a credencial da requisição é este
backend. Sem o registro, a factory levanta `ProviderLookupError` — que é o comportamento certo, e
por isso o gate exercita esse caso também.

Os agentes são os MESMOS objetos que `graph.py` encadeia. O YAML diz a ORDEM, não o conteúdo:
prompt continua vindo dos documentos AgentSchema (ADR-013), e um fluxo declarado não duplica
instrução nenhuma.
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING

import app as _app

#: Ancorado no pacote `app`, nunca em `parents[N]` a partir deste arquivo (regra 9).
BACKEND_ROOT = Path(_app.__file__).resolve().parent.parent

if TYPE_CHECKING:
    from agent_framework import Workflow

#: Os nomes que um fluxo declarado pode citar em `agent.name`. FECHADO de propósito: um YAML que
#: cita um agente inexistente falha ao montar, com o nome no erro — e essa falha é melhor no
#: `write_flow` (onde alguém está editando) do que na primeira execução.
AGENTES_DECLARAVEIS = ("TriageAgent", "RetrieveAgent", "ResolveAgent")


def _agentes(credential) -> dict:
    """Os agentes do helpdesk, pelo nome que o YAML usa.

    A recuperação entra SEM o provider com ACL: o caminho declarativo ainda não carrega a
    identidade da requisição até aqui, e um `GroundedRetrieval` sem usuário recuperaria com a
    credencial do processo — o que trocaria o entitlement por conveniência. Sem provider, o
    agente responde do modelo e o gate de citação recusa a resposta, que é a falha SEGURA.
    """
    from app.modules.helpdesk.internal.agents import (
        build_resolve_agent,
        build_retrieve_agent,
        build_triage_agent,
    )

    return {
        "TriageAgent": build_triage_agent(credential),
        "RetrieveAgent": build_retrieve_agent(credential, None),
        "ResolveAgent": build_resolve_agent(credential),
    }


class AgenteDesconhecido(ValueError):
    """O fluxo cita um agente que este backend não sabe construir."""


def _conferir_agentes(yaml_text: str) -> None:
    """Recusa um fluxo que cite agente que não existe — a checagem que o runtime NÃO faz.

    MEDIDO, não suposto: `WorkflowFactory` resolve os agentes PREGUIÇOSAMENTE. Um YAML com
    `agent.name: AgenteQueNaoExiste` monta sem uma palavra, e só falha quando alguém conversa —
    isto é, longe de quem escreveu o fluxo, e depois de ele já estar publicado.

    Esta é a cola que a MÁXIMA MAIOR autoriza: o runtime cobre a montagem, e faltam estes 20%.
    Custa a lista fechada em `AGENTES_DECLARAVEIS` e a varredura abaixo.

    O parse é do YAML inteiro, e não uma regex sobre o texto: `name:` aparece em outros lugares
    (o `id` do trigger, um argumento), e casar por linha marcaria falso positivo no primeiro
    fluxo que tivesse um argumento chamado `name`.
    """
    import yaml as _yaml

    try:
        doc = _yaml.safe_load(yaml_text)
    except _yaml.YAMLError:
        return  # YAML inválido é assunto da factory, que dá um erro melhor que o nosso

    citados: set[str] = set()

    def _varrer(no: object) -> None:
        if isinstance(no, dict):
            agente = no.get("agent")
            if isinstance(agente, dict) and isinstance(agente.get("name"), str):
                citados.add(agente["name"])
            for v in no.values():
                _varrer(v)
        elif isinstance(no, list):
            for v in no:
                _varrer(v)

    _varrer(doc)
    desconhecidos = sorted(citados - set(AGENTES_DECLARAVEIS))
    if desconhecidos:
        raise AgenteDesconhecido(
            f"o fluxo cita agente(s) que este backend não constrói: {', '.join(desconhecidos)}. "
            f"Disponíveis: {', '.join(AGENTES_DECLARAVEIS)}."
        )


def build_declarative_workflow(yaml_text: str, credential=None) -> Workflow:
    """Monta o `Workflow` de um YAML declarado, com os agentes deste backend registrados.

    `credential=None` monta a factory SEM agentes — é o que o caminho de VALIDAÇÃO quer: checar a
    forma do YAML sem construir cliente nenhum. A conferência de nomes acontece nos DOIS modos,
    porque é justamente na validação que ela precisa falar.
    """
    from agent_framework_declarative import WorkflowFactory

    _conferir_agentes(yaml_text)
    factory = WorkflowFactory(agents=_agentes(credential) if credential is not None else None)
    return factory.create_workflow_from_yaml(yaml_text)


# ─────────────────────────────────────────────────────────────────────────────────────────────
# O ENDPOINT: como um fluxo declarado é servido por AG-UI
# ─────────────────────────────────────────────────────────────────────────────────────────────

#: Qual fluxo esta requisição está rodando. CONTEXTVAR porque o `workflow_factory` do adapter
#: recebe SÓ o `thread_id` — medido em `AgentFrameworkWorkflow.__init__` — e o nome do fluxo chega
#: em `forwarded_props`, que só o `run` enxerga. Mesmo padrão de `credential_for_request`: o que
#: é da requisição viaja pela requisição.
_FLUXO_ATUAL: ContextVar[str | None] = ContextVar("fluxo_declarado_atual", default=None)


def flows_dir() -> Path:
    """Onde os fluxos publicados moram. `AGENTS_DIR` os move junto com os prompts (ADR-014)."""
    externo = os.getenv("AGENTS_DIR", "").strip()
    base = Path(externo) if externo else BACKEND_ROOT / "agents" / "assured"
    return base / "workflows"


def list_declarative_flows() -> list[str]:
    """Os fluxos publicados, em ordem."""
    d = flows_dir()
    return sorted(p.stem for p in d.glob("*.yaml")) if d.is_dir() else []


def load_flow_yaml(nome: str) -> str:
    """O YAML de um fluxo publicado.

    O NOME VEM DO CLIENTE (`forwarded_props`), então ele é conferido contra a lista de fluxos
    PUBLICADOS antes de virar caminho — nunca concatenado direto. Um `../../.env` que virasse
    `Path` seria leitura arbitrária de arquivo com o token de qualquer usuário autenticado.
    """
    if nome not in list_declarative_flows():
        raise FluxoDesconhecido(
            f"não existe fluxo publicado '{nome}'. Publicados: {', '.join(list_declarative_flows()) or '(nenhum)'}"
        )
    return (flows_dir() / f"{nome}.yaml").read_text(encoding="utf-8")


class FluxoDesconhecido(ValueError):
    """O cliente pediu um fluxo que não está publicado."""


async def capturar_fluxo_da_requisicao(request) -> None:
    """Dependência do FastAPI que lê o fluxo pedido e o deixa na contextvar.

    POR QUE UMA DEPENDÊNCIA, e não uma subclasse de `AgentFrameworkWorkflow` que sobrescreve
    `run`. Foi a primeira tentativa, e ela quebra o gate de superfície de rotas: o capture
    substitui `OrderedAgentFrameworkWorkflow` por uma `lambda` para montar o app sem agente vivo,
    e uma classe que HERDA daquele nome no import-time passa a herdar de uma função —
    `TypeError: function() argument 'code' must be code, not str`, na definição da classe. Um
    teste que precisa neutralizar a classe-base é um bom motivo para não depender de herdá-la.

    A dependência roda ANTES do handler do adapter, na mesma task — que é exatamente o escopo de
    uma contextvar. `request.json()` é seguro aqui: o Starlette cacheia o corpo em
    `request._body`, então o handler ainda o lê inteiro depois.

    NÃO VALIDA o nome: quem valida é `load_flow_yaml`, contra a lista de publicados, no momento
    de virar caminho. Recusar aqui devolveria 4xx antes do stream AG-UI abrir, e a tela receberia
    um erro de transporte em vez de uma mensagem na conversa.
    """
    import contextlib

    nome = None
    with contextlib.suppress(Exception):
        corpo = await request.json()
        props = corpo.get("forwarded_props") or corpo.get("forwardedProps") or {}
        if isinstance(props, dict):
            nome = props.get("flow")
    # `set` sem `reset`: a contextvar é da REQUISIÇÃO. O Starlette roda cada requisição no seu
    # próprio contexto copiado, então o valor não atravessa para a seguinte — e não há ponto
    # depois do stream onde um `reset` pudesse rodar de forma confiável.
    _FLUXO_ATUAL.set(str(nome) if nome else None)


def _workflow_para_requisicao(thread_id: str | None):
    """A fábrica que o adapter chama, por requisição. Lê o fluxo da contextvar."""
    from app.shared.auth import credential_for_request

    nome = _FLUXO_ATUAL.get()
    if not nome:
        # Sem fluxo escolhido não há o que rodar. Levantar aqui produz um erro de execução que
        # diz o que fazer; devolver um workflow vazio produziria uma conversa que não responde.
        raise FluxoDesconhecido(
            "nenhum fluxo informado — mande `forwarded_props: {flow: <nome>}` na requisição"
        )
    return build_declarative_workflow(load_flow_yaml(nome), credential_for_request())


def build_declarative_agent():
    """UM endpoint, N fluxos — e não um endpoint por fluxo.

    Os fluxos são dado (documento publicável sem rebuild, ADR-014), e montar rota por fluxo no
    boot faria a lista de rotas depender do conteúdo de um diretório: o snapshot de superfície
    mudaria a cada fluxo novo, e um fluxo publicado em runtime não teria rota nenhuma até o
    próximo deploy.

    Reusa `OrderedAgentFrameworkWorkflow` por COMPOSIÇÃO (importado aqui dentro, na hora de
    montar) em vez de herança — ver `capturar_fluxo_da_requisicao` para o que a herança quebrava.
    """
    from app.modules.helpdesk.internal.stream_fix import OrderedAgentFrameworkWorkflow

    return OrderedAgentFrameworkWorkflow(workflow_factory=_workflow_para_requisicao)
