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
    return {"provenance": prov} if isinstance(prov, dict) and prov else {}


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
