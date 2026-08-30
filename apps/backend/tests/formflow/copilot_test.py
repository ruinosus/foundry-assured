"""O copiloto é um documento — e ele não pode declarar um alvo que não existe.

POR QUE O `type: copilot` EXISTE. O assistente do wizard já existia: um agente
(`agents/assured/builder.yaml`) mais um punhado de decisões espalhadas em código — em quais telas
ele aparece, em que campos pode escrever, o que ele nunca faz. Nada disso era legível sem abrir o
código, e nada disso era verificável.

O documento não substitui o agente: o agente é QUEM RESPONDE (prompt, modelo), o copiloto é ONDE
ELE ATUA e O QUE PODE TOCAR. Um cita o outro em `engine.agent`.

A CHECAGEM QUE FAZ ISSO VALER A PENA são os alvos. Um copiloto declara em que campos escreve;
sem conferir contra o formulário real, ele declara o que quiser — e o erro aparece quando alguém
usa a tela, na forma de uma proposta para um campo que não existe. É a checagem nº 2 das oito do
`okf-validate` dos mocks: *"os alvos declarados existem neste projeto"*.

E ela é provada POR MUTAÇÃO, não por afirmação: um copiloto sintético com alvo inexistente, campo
inexistente e campo que não aceita proposta tem de produzir exatamente três problemas. Um gate
que só vê o caso bom não distingue verificação de `return []`.

    uv run python -m tests.formflow.copilot_test
"""

from __future__ import annotations

import sys

from app.modules.formflow.public import (
    copilots_dir,
    list_copilots,
    load_copilot,
    verificar_alvos,
)

#: O que um copiloto DECLARADO precisa dizer para não ser uma promessa vaga. Cada um responde uma
#: pergunta que, sem o documento, só o código respondia.
BLOCOS_EXIGIDOS = {
    "surface": "onde ele aparece — fora das telas declaradas ele não existe",
    "engine": "quem executa, e em que runtime",
    "targets": "em que campos ele escreve",
    "tools": "o que ele alcança além de propor",
    "policy": "onde ele para num humano",
}


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool, detalhe: str = "") -> None:
        print(f"  {'✓' if cond else '✗'} {nome}{f'  ({detalhe})' if detalhe and not cond else ''}")
        if not cond:
            falhas.append(nome)

    docs = list_copilots()
    check("há documentos publicados", bool(docs), str(copilots_dir()))
    check("a política HITL existe e é herdável", "hitl" in docs, str(docs))

    copilotos = [d for d in docs if d != "hitl"]
    for nome in copilotos:
        print(f"\n── {nome} ──")
        c = load_copilot(nome)

        for bloco, porque in BLOCOS_EXIGIDOS.items():
            check(f"declara `{bloco}` ({porque})", bloco in c)

        # O runtime é DITO. Um recurso que mente sobre onde executa é pior que um ausente
        # (SEGUNDA MÁXIMA) — e `builder` roda no nosso adapter, não no Foundry, porque só o
        # adapter repassa as tools do cliente ao agente.
        runtime = (c.get("engine") or {}).get("runtime")
        check("`engine.runtime` é declarado", runtime in {"foundry", "backend"}, repr(runtime))

        # A política é HERDADA por nome, não copiada: um gate copiado em N documentos diverge no
        # primeiro que alguém editar, e a divergência não dá erro.
        check("herda a política por NOME", c.get("policy") == "hitl", repr(c.get("policy")))

        # Toda tool de escrita nasce exigindo aprovação. Um copiloto que declarasse escrita sem
        # gate seria uma via de publicação sem revisão (ADR-022).
        escritas = (c.get("tools") or {}).get("write") or []
        sem_gate = [w for w in escritas if w.get("require_approval") != "always"]
        check("toda tool de escrita exige aprovação", not sem_gate, str(sem_gate))

        # ── A CHECAGEM CENTRAL ───────────────────────────────────────────────────────────
        problemas = verificar_alvos(c)
        check("todo alvo existe, e todo campo é propostável", not problemas, str(problemas))

    # ── A PROVA DE QUE O GATE MORDE ──────────────────────────────────────────────────────
    print("\n── por mutação: o verificador reprova o que deve reprovar ──")
    torto = {
        "targets": [
            {"flow": "formulario-que-nao-existe", "writes": ["x"]},
            {"flow": "agent", "writes": ["campo-que-nao-existe"]},
            # `model` existe no formulário do agente e NÃO é `ai: true` — propor nele produziria
            # um card que a pessoa não tem como aceitar.
            {"flow": "agent", "writes": ["model"]},
        ]
    }
    ps = verificar_alvos(torto)
    check("três alvos tortos → três problemas", len(ps) == 3, f"{len(ps)}: {ps}")
    check("…reclama do formulário inexistente", any("formulario-que-nao-existe" in p for p in ps))
    check("…reclama do campo inexistente", any("campo-que-nao-existe" in p for p in ps))
    check("…e reclama do campo que não aceita proposta", any("ai: true" in p for p in ps))

    # Alvo vazio é legítimo: um copiloto sem alvo conversa e não escreve — é uma configuração
    # válida, e reprová-la faria o gate exigir escrita de quem só responde.
    check("copiloto sem alvo nenhum é válido", verificar_alvos({"targets": []}) == [])

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ o copiloto é documento, e o que ele declara escrever existe de verdade.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
