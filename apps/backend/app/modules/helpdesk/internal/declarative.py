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

from typing import TYPE_CHECKING

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
