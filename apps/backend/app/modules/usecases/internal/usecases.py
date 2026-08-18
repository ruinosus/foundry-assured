"""Casos de uso — a camada que o negócio lê, sobre os agentes que a máquina executa.

O PROBLEMA QUE ISTO RESOLVE, dito pelo dono do projeto: *"ninguém de negócio consegue ler essa
lista imensa de agents"*. E é verdade — `triage`, `retrieve`, `resolve` são peças. Quem é de
negócio abre e não encontra "o helpdesk", porque o helpdesk foi dissolvido em cinco linhas
técnicas. O nível de abstração estava errado para o público.

DE ONDE VEM CADA COISA, e nada aqui é declarado duas vezes (SEGUNDA MÁXIMA):

    quais casos existem   →  os AGENTES PUBLICADOS, agrupados por `metadata.use_case`
    quais peças cada um tem →  os agentes publicados, agrupados pelo caso
    qual o fluxo          →  o Dataset `<caso>-flow` no Foundry (disco só como reserva de boot)
    como ele se chama     →  `metadata.use_case_name`, editável pela tela

Um caso de uso não é uma tabela nossa: é uma LEITURA sobre o que já existe, mais um punhado de
campos guardados no `metadata` do agente publicado. Criar uma tabela paralela seria a segunda
verdade que a máxima proíbe — e divergiria no primeiro agente publicado por fora.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import app

#: CACHE local dos fluxos — a FONTE é o Foundry.
#:
#: O fluxo do canvas era gravado só aqui, e isso estava errado de duas formas: em produção o disco
#: do container é efêmero (um fluxo montado sumia no restart), e um recurso fora do Foundry viola a
#: SEGUNDA MÁXIMA. Agora `write_flow` publica um Dataset versionado no projeto e grava aqui só
#: para o repositório continuar tendo os fluxos em git — quem lê, lê do serviço primeiro.
#:
#: Ancorado no pacote `app`, nunca contado por `parents[N]` (regra 9).
_BACKEND_ROOT = Path(app.__file__).resolve().parent.parent
WORKFLOWS_DIR = _BACKEND_ROOT / "agents" / "helpdesk" / "workflows"

#: Documento AgentSchema → caso de uso a que pertence.
#:
#: Só as exceções: um agente cujo nome já é o do caso não precisa de linha aqui. `helpdesk` tem
#: cinco documentos porque é um workflow de três passos mais duas variantes de concierge — é
#: exatamente por isso que a lista de agentes ficou ilegível para quem é de negócio.
_CASE_FOR_AGENT = {
    "triage": "helpdesk",
    "retrieve": "helpdesk",
    "resolve": "helpdesk",
    "concierge-grounded": "helpdesk",
    "concierge-ungrounded": "helpdesk",
    "helpdesk-concierge": "helpdesk",
}

#: Rótulo de negócio por caso, quando o serviço ainda não tem `metadata.use_case_name`.
#: É semente, não verdade: a tela grava o nome escolhido no metadata, e ele passa a ganhar.
_DEFAULT_LABEL = {
    "helpdesk": "Atendimento a desenvolvedores",
    "selfwiki": "Consulta à documentação do projeto",
    "oncall": "Triagem de plantão",
    "deepcall": "Triagem de plantão (experimento)",
    "platform": "Operações de plataforma",
    "techdocs": "Documentação de plataforma",
}


def _case_of(agent_name: str, metadata: dict) -> str:
    """A qual caso este agente pertence.

    `metadata.use_case` ganha de tudo: é o que a tela grava quando alguém reorganiza. O mapa é
    fallback para os agentes que o repositório publica, e o nome do próprio agente é o último
    recurso — um agente criado pelo wizard vira um caso de uso de uma peça só, que é o
    comportamento certo: ele É um assistente completo.
    """
    return metadata.get("use_case") or _CASE_FOR_AGENT.get(agent_name) or agent_name


def _flow_path(case_id: str) -> Path:
    return WORKFLOWS_DIR / f"{case_id}.yaml"


def read_flow(case_id: str) -> str | None:
    """O YAML do fluxo. FOUNDRY primeiro, disco como reserva.

    A ordem é o ponto: o serviço é a fonte, e um fluxo publicado pelo canvas só existe lá. O
    arquivo continua sendo lido porque os fluxos que vêm no repositório (versionados em git) ainda
    não foram publicados num ambiente novo — e uma tela vazia logo depois do `azd up` seria pior
    que ler o que o repositório traz.

    Um caso sem fluxo em lugar nenhum é um caso de passo único, não um erro.
    """
    with contextlib.suppress(Exception):
        from app.modules.foundry.public import load_flow

        publicado = load_flow(f"{case_id}-flow")
        if publicado:
            return publicado

    caminho = _flow_path(case_id)
    if not caminho.is_file():
        return None
    with contextlib.suppress(OSError):
        return caminho.read_text(encoding="utf-8")
    return None


def write_flow(case_id: str, yaml_text: str) -> dict:
    """Grava o fluxo, VALIDANDO antes de gravar.

    A validação é o próprio `WorkflowFactory`: se ele não consegue montar, o YAML não serve, e
    escrever um fluxo inválido transformaria um erro de edição num assistente quebrado. Usar o
    build do runtime como validador é mais fiel que escrever um validador nosso — ele conhece as
    ações, os alvos de `GotoAction` e os handlers obrigatórios.
    """
    from agent_framework_declarative import WorkflowFactory

    try:
        WorkflowFactory().create_workflow_from_yaml(yaml_text)
    except Exception as exc:
        raise ValueError(f"O fluxo não é válido: {exc}") from exc

    # PUBLICA NO FOUNDRY — é onde o fluxo passa a existir. Cada gravação é uma versão nova do
    # dataset, e versões não se sobrescrevem: o histórico do fluxo vem de graça, e o portal
    # mostra o mesmo que a tela.
    from app.modules.foundry.public import save_flow

    publicado = save_flow(f"{case_id}-flow", yaml_text, description=f"Fluxo do caso {case_id}")

    # O disco é CACHE, e a gravação é best-effort de propósito: em produção ele é read-only ou
    # efêmero, e falhar aqui depois de publicar com sucesso transformaria uma publicação boa num
    # erro. O que importa já aconteceu.
    with contextlib.suppress(OSError):
        WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
        _flow_path(case_id).write_text(yaml_text, encoding="utf-8")

    return {
        "case": case_id,
        "bytes": len(yaml_text.encode("utf-8")),
        "dataset": publicado.get("name"),
        "version": publicado.get("version"),
    }


def _steps_of(yaml_text: str | None) -> list[dict]:
    """Os passos do fluxo, achatados para a tela.

    Lê o YAML como dados — sem montar o workflow, porque listar não deve exigir credencial nem
    runtime .NET. A tela de leitura precisa funcionar mesmo onde o fluxo não roda.
    """
    if not yaml_text:
        return []
    import yaml as _yaml

    try:
        doc = _yaml.safe_load(yaml_text) or {}
    except Exception:  # noqa: BLE001 — YAML quebrado vira "sem passos", não derruba a lista
        return []

    acoes = ((doc.get("trigger") or {}).get("actions")) or doc.get("actions") or []
    passos = []
    for a in acoes:
        if not isinstance(a, dict):
            continue
        kind = a.get("kind") or ""
        if kind in ("EndWorkflow", "SetVariable"):
            continue  # mecânica do fluxo, não passo que alguém reconheça
        passos.append(
            {
                "id": a.get("id"),
                "kind": kind,
                # `displayName` é o rótulo que o autor escreveu para humanos; sem ele, o id.
                "label": a.get("displayName") or a.get("id"),
                "agent": (a.get("agent") or {}).get("name") if isinstance(a.get("agent"), dict) else None,
                # A informação que mais importa para quem é de negócio: este passo para e pergunta?
                "waits_for_human": kind in ("RequestExternalInput", "Question")
                or bool(a.get("requireApproval")),
            }
        )
    return passos


def list_use_cases() -> list[dict]:
    """Os casos de uso, montados a partir dos agentes publicados e dos fluxos do repositório.

    Falha ao ler o Foundry NÃO devolve lista vazia: devolve os casos que o repositório conhece,
    com `agents: []` e o motivo. A tela precisa distinguir "não há caso" de "não consegui ler" —
    é a mesma lição que a tela de avaliações custou.
    """
    agentes: list[dict] = []
    motivo: str | None = None
    try:
        from app.modules.foundry.public import list_agents

        agentes = list_agents(100)
    except Exception as exc:  # noqa: BLE001
        motivo = f"Não foi possível ler os agentes do Foundry: {exc}"

    casos: dict[str, dict] = {}

    def _garante(case_id: str) -> dict:
        if case_id not in casos:
            fluxo = read_flow(case_id)
            casos[case_id] = {
                "id": case_id,
                "name": _DEFAULT_LABEL.get(case_id, case_id),
                "description": "",
                "agents": [],
                "steps": _steps_of(fluxo),
                "has_flow": fluxo is not None,
                # Quem executa. `declarative` quando há fluxo YAML; senão, o que o agente
                # publicado declarou em `metadata.runtime` (preenchido abaixo). Lido do AGENTE e
                # não do registry de propósito: importar `app.registry` daqui seria um módulo
                # dependendo da composição, que a ADR-017 proíbe — e a informação já viaja no
                # metadata, que é onde a SEGUNDA MÁXIMA a colocou.
                "runtime": "declarative" if fluxo else "—",
            }
        return casos[case_id]

    # NENHUM caso é semeado a partir do código: um caso existe porque há agente publicado. Um
    # domínio que nunca passou pelo ingest não aparece — e isso é o comportamento certo, não uma
    # lacuna: a SEGUNDA MÁXIMA diz que tudo fica no Foundry, então o que não está lá não existe
    # para quem olha o produto. O aviso na tela vazia manda rodar `cli.provision_agents`.

    for a in agentes:
        versao = a.get("version") or {}
        # Assistente de TELA não é caso de uso. Ele ajuda alguém a preencher um formulário; não
        # tem conversa atendida nem chamado evitado, e incluí-lo faria as métricas desta lista
        # deixarem de significar o que significam. A medição dele é outra (/assistants).
        if (versao.get("metadata") or {}).get("surface") == "tool":
            continue
        metadata = {k: v for k, v in (versao.get("metadata") or {}).items()} if isinstance(versao.get("metadata"), dict) else {}
        case_id = _case_of(a.get("name") or "", metadata)
        caso = _garante(case_id)
        if metadata.get("use_case_name"):
            caso["name"] = metadata["use_case_name"]
        if metadata.get("use_case_description"):
            caso["description"] = metadata["use_case_description"]
        # O runtime do caso vem do primeiro agente que o declara — todos os agentes de um caso
        # rodam no mesmo lugar, porque é o caso que define onde.
        if caso["runtime"] == "—" and versao.get("runtime"):
            caso["runtime"] = versao["runtime"]
        caso["agents"].append(
            {
                "name": a.get("name"),
                "state": a.get("state"),
                "version": versao.get("version"),
                "runtime": versao.get("runtime"),
                "description": versao.get("description"),
            }
        )

    saida = sorted(casos.values(), key=lambda c: (not c["agents"], c["name"].lower()))
    if motivo:
        for c in saida:
            c["reason"] = motivo
    return saida


def get_use_case(case_id: str) -> dict:
    """Um caso com o fluxo cru — a tela de leitura e o canvas consomem o mesmo objeto."""
    for c in list_use_cases():
        if c["id"] == case_id:
            c["flow"] = read_flow(case_id)
            return c
    raise KeyError(f"Caso de uso '{case_id}' não encontrado.")


def rename_use_case(case_id: str, name: str, description: str = "") -> dict:
    """Grava o rótulo de negócio no `metadata` dos agentes do caso.

    NO METADATA, não numa tabela nossa: é o que a SEGUNDA MÁXIMA exige, e tem uma consequência
    boa — quem abrir o portal do Foundry vê o mesmo nome que a tela mostra. Uma tabela nossa
    ficaria invisível lá, e as duas divergiriam na primeira edição feita pelo portal.

    Escreve em TODOS os agentes do caso porque o caso não tem recurso próprio: ele é o conjunto.
    Marcar só um deixaria o rótulo dependente de qual agente a listagem lesse primeiro.
    """
    from app.modules.agentdefs.public import composed_agents
    from app.modules.foundry.public import create_agent_version
    from app.modules.tenancy.public import tenant_config

    # O PROMPT VEM DO REPOSITÓRIO, não do serviço. Renomear publica uma versão nova (versões são
    # imutáveis), e a versão nova precisa da definição inteira — se eu lesse as instruções de
    # volta do Foundry, um agente editado por fora sobrescreveria o documento na próxima renomeação.
    # A fonte de prompt é o documento AgentSchema, e continua sendo aqui.
    documentos = composed_agents()
    modelo = tenant_config().foundry_model or "gpt-5-mini"

    caso = get_use_case(case_id)
    atualizados = []
    for a in caso["agents"]:
        nome = a["name"]
        par = documentos.get(nome)
        if not par:
            # Agente sem documento no repo (criado pelo wizard, ou hosted deployado). Não temos o
            # prompt dele, e republicar sem instruções apagaria o comportamento. Pular e DIZER.
            atualizados.append(
                {"agent": nome, "ok": False, "reason": "sem documento no repositório"}
            )
            continue
        instrucoes, descricao_doc = par
        try:
            create_agent_version(
                nome,
                {
                    "kind": "prompt",
                    "model": modelo,
                    "instructions": instrucoes,
                    "metadata": {
                        "runtime": a.get("runtime") or "backend",
                        "source": "repo",
                        "use_case": case_id,
                        "use_case_name": name[:512],
                        "use_case_description": description[:512],
                    },
                },
                description=descricao_doc,
            )
            atualizados.append({"agent": nome, "ok": True})
        except Exception as exc:  # noqa: BLE001 — um agente falho não impede os outros
            atualizados.append({"agent": nome, "ok": False, "reason": str(exc)[:160]})

    return {"id": case_id, "name": name, "agents": atualizados}
