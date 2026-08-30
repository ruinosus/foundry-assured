"""O decorador que faz toda escrita no Foundry virar evento (ADR-023).

POR QUE UM DECORADOR, e não a chamada repetida em cada função. São oito arquivos de escrita —
agente, skill, base, toolbox, fluxo, importação — e a cobertura da auditoria vinha falhando
exatamente onde alguém esqueceu de instrumentar. Uma linha por função é uma linha que a próxima
função nova não terá.

O QUE ELE GRAVA, e o que ele recusa a gravar:

    grava    o TIPO de recurso, o NOME, a versão que saiu, e a PROCEDÊNCIA quando o documento a
             traz (`metadata.provenance`) — que é o elo que faltava entre "de onde veio este
             texto" e "quando ele entrou num recurso publicado"
    recusa   o corpo do documento. Instruções de agente e conteúdo de skill são texto — do
             modelo, do usuário, ou de um catálogo de terceiro. Copiá-los para uma trilha
             IMUTÁVEL faria dela o maior repositório de conteúdo do produto, e sem volta.

SÓ GRAVA NO SUCESSO. Uma escrita que falhou não é um evento de escrita; registrá-la faria a
trilha afirmar algo que não aconteceu, que é pior que não registrar.

E A FALHA DE GRAVAÇÃO NÃO DERRUBA A ESCRITA. Diferente da aprovação — onde a RULE #5 exige
fail-closed porque o registro É a autorização —, aqui o recurso já está publicado no Foundry
quando o evento seria gravado. Levantar depois disso deixaria a pessoa vendo um erro sobre um
recurso que existe. A lacuna aparece no relatório de verificação, que é onde ela deve aparecer.
"""

from __future__ import annotations

import contextlib
import functools
from collections.abc import Callable


def _procedencia(doc: object) -> dict:
    """A procedência declarada no documento, se houver. Só ela — nunca o resto do metadata.

    ACEITA STRING JSON além de objeto, e a razão é do serviço: o Foundry exige que os VALORES de
    `metadata` sejam string —

        The JSON value could not be converted to System.String. Path: $.…metadata.provenance

    — então a procedência viaja serializada. Medido publicando uma skill com o objeto cru, que o
    serviço recusou com 400. Aqui ela é desserializada de volta para o evento ficar consultável.

    DOIS FORMATOS, e o antigo não é legado por descuido:

        {"okf_version": "0.2", "fields": {...}}   OKF v0.2 — o que a tela grava hoje
        {"campo": ["fonte", ...]}                 o mapa que a tela gravava antes

    Recursos publicados ANTES desta mudança carregam o formato antigo no metadata, para sempre —
    documento publicado não é reescrito (ADR-023). Uma leitura que só entendesse o formato novo
    faria a procedência desses recursos desaparecer da trilha no dia em que alguém os
    republicasse, sem erro nenhum. O normalizador converte, e o evento sai num formato só.
    """
    import json

    if not isinstance(doc, dict):
        return {}
    meta = doc.get("metadata")
    if not isinstance(meta, dict):
        return {}
    prov = meta.get("provenance")
    if isinstance(prov, str) and prov.strip():
        try:
            prov = json.loads(prov)
        except Exception:  # noqa: BLE001 — string ilegível não vira evento sem procedência
            return {}
    if not isinstance(prov, dict) or not prov:
        return {}
    return {"provenance": _verificada(_normalizar(prov))}


def _normalizar(prov: dict) -> dict:
    """Traz o formato antigo para o vocabulário do OKF v0.2, e deixa o novo passar intacto.

    O antigo não sabia QUEM escreveu nem QUANDO — então a conversão não inventa: sai um
    `generated` sem `by` e sem `at`, marcado com a origem do dado. Preencher com o agente de hoje
    e a hora de agora produziria um registro que parece medido e é chute, num campo de auditoria.
    """
    if prov.get("okf_version"):
        return prov
    campos = {
        campo: {
            "generated": {"legacy": True},
            **({"sources": [{"id": str(f), "resource": str(f)} for f in fontes]} if fontes else {}),
        }
        for campo, fontes in prov.items()
        if isinstance(fontes, list)
    }
    return {"okf_version": "0.2", "fields": campos} if campos else prov


def _verificada(prov: dict) -> dict:
    """Carimba `verified` — o campo do OKF v0.2 de que o consumidor deriva o trust tier.

    POR QUE AQUI, E NÃO NA TELA. `verified.by` é a identidade de quem revisou, e a spec deriva o
    tier do prefixo do ator (`human:` → human-reviewed). A tela não pode gravá-lo: o documento que
    ela monta é publicado no Foundry, e um recurso compartilhado não é lugar de identidade — é a
    mesma regra que mantém o nome do aprovador fora da mensagem do chat (I-10). Aqui o destino é
    a TRILHA, onde a identidade já mora e é o que a auditoria pergunta primeiro.

    `actor()` já devolve `human:<e-mail>` — exatamente a convenção de ator do OKF (§7), que este
    repositório adotou antes de saber que era ela.

    Escrita sem usuário resolvido (job, script) sai como `process:app`, o mesmo `actor()` de
    sempre: o tier vira machine-confirmed, que é a verdade.
    """
    from datetime import UTC, datetime

    from app.modules.audit.public import actor

    return {
        **prov,
        "verified": [{"by": actor(), "at": datetime.now(UTC).isoformat(timespec="seconds")}],
    }


def audited(resource: str, action: str = "create"):
    """Registra um evento de escrita quando a função tiver sucesso.

    `resource` é o TIPO (agent, skill, knowledge, toolbox, flow); `action` distingue criação de
    remoção, porque apagar e publicar respondem perguntas diferentes numa auditoria.

    O NOME do recurso é lido do primeiro argumento posicional ou do kwarg `name` — é a convenção
    que todas as funções de escrita deste módulo já seguem. Um chamador fora dessa convenção
    grava o evento sem nome em vez de não gravar: um evento incompleto ainda diz que houve
    escrita; a ausência dele diz que não houve.
    """

    def decorator(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            resultado = fn(*args, **kwargs)

            with contextlib.suppress(Exception):
                from app.modules.audit.public import actor, actor_detail, record

                nome = kwargs.get("name") or (args[0] if args else "")
                detalhe = {"resource": resource, "action": action, **actor_detail()}
                if isinstance(resultado, dict) and resultado.get("version"):
                    detalhe["version"] = str(resultado["version"])
                # A procedência viaja do documento para o evento — o elo ponta a ponta.
                for candidato in (*args[1:], *kwargs.values()):
                    detalhe.update(_procedencia(candidato))

                record(
                    scope="approvals",
                    actor=actor(),
                    kind="write",
                    summary=f"{action} {resource} {nome}".strip(),
                    ref=str(nome),
                    detail=detalhe,
                )
            return resultado

        return wrapper

    return decorator
