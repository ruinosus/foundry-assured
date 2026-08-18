"""Toda superfície que serve agente é AUTENTICADA e DECLARA o que grava.

POR QUE ESTE GATE EXISTE. O produto ganhou agentes por quatro caminhos diferentes — agent-framework,
laço de SSE escrito à mão, LangGraph, e hosted dentro do Foundry — e cada caminho tem um ponto
natural onde a instrumentação se pendura. Como cada um nasceu numa época, a gravação nasceu em
quatro lugares, e o que existe num não existe no outro. Nenhum agente "esqueceu" de gravar; a
topologia é que permitiu esquecer.

Um levantamento manual disso envelhece no primeiro agente novo. Este gate é o levantamento em
forma executável: **uma superfície nova entra nesta matriz, ou não passa no CI.**

O QUE ELE VERIFICA, e por que cada item já se provou necessário:

  1. AUTENTICAÇÃO em toda rota que serve agente. Não é hipotético: `add_langgraph_fastapi_endpoint`
     não aceita `dependencies` (a assinatura upstream tem três parâmetros e nenhum é o gate), e por
     isso `/oncall` e `/deepcall` ficaram ABERTOS — medido, respondiam 422 sem token enquanto
     `/helpdesk` respondia 401. Eram os dois únicos endpoints de agente sem auth, e são justamente
     os que abrem chamado e têm HITL de escrita. O route snapshot não pegou: ele compara caminho e
     método, não dependência.

  2. DECLARAÇÃO COMPLETA do que cada superfície grava. `n/a` é resposta válida — um agente sem base
     de conhecimento não tem referência a citar — mas exige MOTIVO. A diferença entre "não se
     aplica" e "ninguém instrumentou" é a diferença entre uma lacuna conhecida e uma surpresa.

  3. NENHUMA SUPERFÍCIE ÓRFÃ. Rota de agente que ninguém declarou reprova, e declaração de rota que
     não existe mais também. As duas metades apodrecem em direções opostas.

O gate NÃO tenta provar que a gravação declarada de fato acontece — isso é trabalho dos testes de
cada módulo (`usage_seam_test`, `conversation_store_test`). Ele prova que ninguém pode adicionar
agente sem responder à pergunta.
"""

from __future__ import annotations

import sys

#: As colunas da matriz. Toda superfície responde a TODAS.
COLUNAS = ("conversa", "tokens", "referencias", "chamado", "trilha", "caso_de_uso")

#: A MATRIZ. `True` = grava hoje. String = não grava, e o texto diz o quê: começando com "n/a:"
#: quando não se aplica, ou descrevendo a lacuna quando falta mesmo.
#:
#: Medida no código em 2026-08-18, não copiada de documentação. Cada linha vermelha aqui é
#: trabalho conhecido, e o plano de convergência está em docs/adr — um seam por runtime, nunca uma
#: chamada por agente.
MATRIZ: dict[str, dict[str, object]] = {
    # ── runtime A · agent-framework · fábrica de cliente ────────────────────────────────────
    "/helpdesk": {
        "conversa": True,
        "tokens": True,
        "referencias": True,
        "chamado": True,
        "trilha": True,
        "caso_de_uso": True,
    },
    "/platform": {
        "conversa": True,
        "tokens": True,
        "referencias": "n/a: tool-driven, sem base de conhecimento",
        "chamado": "n/a: não abre chamado",
        "trilha": True,
        "caso_de_uso": True,
    },
    "/builder": {
        "conversa": True,
        "tokens": True,
        "referencias": "n/a: assistente de formulário, sem base",
        "chamado": "n/a: não abre chamado",
        "trilha": True,
        "caso_de_uso": True,
    },
    # ── runtime B · Responses API · laço de SSE escrito aqui ────────────────────────────────
    "/techdocs": {
        "conversa": True,
        "tokens": True,
        "referencias": True,
        "chamado": "n/a: não abre chamado",
        "trilha": "n/a: não faz escrita que precise de aprovação",
        "caso_de_uso": True,
    },
    "/selfwiki": {
        "conversa": True,
        "tokens": True,
        "referencias": True,
        "chamado": "n/a: não abre chamado",
        "trilha": "n/a: não faz escrita que precise de aprovação",
        "caso_de_uso": True,
    },
    # ── runtime C · LangChain / LangGraph · fora da fábrica ─────────────────────────────────
    "/oncall": {
        # O turno é do GRAFO, e é lá que ele é gravado: `on_chain_end` na RAIZ
        # (`parent_run_id is None`), que vê o estado final com a transcrição. O token continua
        # vindo do `on_llm_end`, que vê a chamada de modelo. Dois níveis, duas perguntas.
        "conversa": True,
        "tokens": True,
        "referencias": "n/a: triagem por tools, sem base de conhecimento",
        "chamado": True,
        "trilha": True,
        "caso_de_uso": True,
    },
    "/deepcall": {
        # O turno é do GRAFO, e é lá que ele é gravado: `on_chain_end` na RAIZ
        # (`parent_run_id is None`), que vê o estado final com a transcrição. O token continua
        # vindo do `on_llm_end`, que vê a chamada de modelo. Dois níveis, duas perguntas.
        "conversa": True,
        "tokens": True,
        "referencias": "n/a: triagem por tools, sem base de conhecimento",
        "chamado": True,
        "trilha": True,
        "caso_de_uso": True,
    },
    # ── runtime D · hosted no Foundry · execução fora daqui ─────────────────────────────────
    "/helpdesk-hosted": {
        "conversa": True,
        "tokens": True,
        "referencias": "o stream de Responses não devolve as fontes que a base do agente trouxe",
        "chamado": "n/a: não abre chamado",
        "trilha": "n/a: o gêmeo não faz escrita que precise de aprovação",
        "caso_de_uso": True,
    },
    "/platform-hosted": {
        # PASSTHROUGH 1:1 — o Invocations já serve AG-UI e este caminho relaia os bytes sem abrir
        # envelope, de propósito (é o que permite o interrupt de aprovação ir e voltar inteiro).
        # Sem parsing não há texto nem uso a ler, e parsear para medir custaria a propriedade que
        # justifica o desenho. Lacuna declarada, não descuido.
        "conversa": "passthrough de bytes AG-UI: o texto não é lido aqui",
        "tokens": "idem — abrir o envelope para medir quebraria o passthrough do interrupt",
        "referencias": "n/a: tool-driven, sem base",
        "chamado": "n/a: não abre chamado",
        "trilha": True,
        "caso_de_uso": "depende da conversa",
    },
    "/foundry-agent/{name}": {
        # A superfície do agente que o USUÁRIO cria. A amarração vem do `{name}` do caminho, não de
        # um nome fixo — senão a conversa de todo agente criado cairia sob a mesma chave.
        "conversa": True,
        "tokens": True,
        "referencias": "o stream de Responses não devolve as fontes da base do agente",
        "chamado": "n/a: não abre chamado",
        "trilha": "n/a: sem escrita que precise de aprovação por este caminho",
        "caso_de_uso": True,
    },
}

#: Rotas que respondem POST e NÃO servem agente. Precisa ser explícito: sem esta lista, qualquer
#: POST novo entraria como superfície de agente por engano, e o gate viraria ruído.
NAO_SAO_AGENTE = (
    "/tenant",
    "/admin",
    "/agents",
    "/knowledge",
    "/skills",
    "/toolboxes",
    "/usecases",
    "/tickets",
    "/evals",
    "/audit",
    "/conversations",
    "/builder-assist",
    "/flows",
    "/proposals",
    "/memory",
    "/connections",
)


def _superficies() -> dict[str, list[str]]:
    """`{caminho: [dependências]}` das rotas POST que servem agente.

    SUBPROCESSO E PERFIL SINTÉTICO, reusando `tests/smoke/_capture_routes`. Importar `app.main`
    aqui foi a primeira tentativa e quebrou no CI: montar o app em `self_hosted` constrói agente na
    hora, e `FoundryChatClient` exige `FOUNDRY_PROJECT_ENDPOINT`, que o CI não tem. Verde local,
    vermelho no CI — e por uma lacuna do teste, não do código. O `_capture_routes` já resolvia
    exatamente isso, então este gate reusa em vez de duplicar: um lugar só sabe bootar o app sem
    credencial.

    O perfil é `auth_on_oncall` — auth LIGADA e todos os domínios montados. Sem `ENTRA_*` a
    autenticação fica desligada e TODA rota aparece sem dependência, o que responderia
    "desprotegida" para o app inteiro e não significaria nada.
    """
    import json
    import pathlib
    import subprocess
    import sys

    import app as _app

    raiz = pathlib.Path(_app.__file__).resolve().parent.parent
    r = subprocess.run(
        [sys.executable, "-m", "tests.smoke._capture_routes", "auth_on_oncall", "--deps"],
        capture_output=True,
        text=True,
        cwd=raiz,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(f"captura de rotas falhou:\n{r.stderr[-2000:]}")

    from app.registry import DOMAIN_KINDS

    achadas: dict[str, list[str]] = {}
    for caminho, deps in json.loads(r.stdout):
        if any(caminho.startswith(prefixo) for prefixo in NAO_SAO_AGENTE):
            continue
        primeiro = caminho.lstrip("/").split("/")[0]
        if primeiro in DOMAIN_KINDS or "hosted" in caminho or "foundry-agent" in caminho:
            achadas[caminho] = deps
    return achadas


def _autenticada(deps: list[str]) -> bool:
    """A rota exige identidade?

    Lê o `dependant` resolvido (é o que `_capture_routes --deps` emite), não a lista `dependencies`
    declarada: uma dep aplicada por `include_router` — que é como as rotas do LangGraph são
    protegidas, já que o adapter upstream não aceita `dependencies` — só aparece ali. Checar a lista
    declarada daria falso negativo justamente no caminho que precisou do conserto.
    """
    return any("user" in n or "auth" in n or "require" in n for n in deps)


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    rotas = _superficies()
    check(f"a descoberta achou superfícies de agente ({len(rotas)})", len(rotas) >= 10)

    # --- 1 · toda rota de agente é autenticada -------------------------------------------
    abertas = sorted(c for c, deps in rotas.items() if not _autenticada(deps))
    check(
        "nenhuma rota de agente sem autenticação"
        + (f" — ABERTAS: {', '.join(abertas)}" if abertas else ""),
        not abertas,
    )

    # --- 2 · nenhuma superfície órfã, dos dois lados --------------------------------------
    nao_declaradas = sorted(set(rotas) - set(MATRIZ))
    check(
        "toda superfície servida está declarada na matriz"
        + (f" — FALTAM: {', '.join(nao_declaradas)}" if nao_declaradas else ""),
        not nao_declaradas,
    )
    # O perfil monta TUDO, então declaração sem rota é declaração podre — as duas metades
    # apodrecem em direções opostas, e só cobrar uma deixaria a outra mentir.
    orfas = sorted(set(MATRIZ) - set(rotas))
    check(
        "nenhuma declaração aponta para rota inexistente"
        + (f" — ÓRFÃS: {', '.join(orfas)}" if orfas else ""),
        not orfas,
    )

    # --- 3 · toda declaração responde a TODAS as colunas, e `n/a` tem motivo ---------------
    incompletas: list[str] = []
    vazias: list[str] = []
    for caminho, linha in MATRIZ.items():
        faltando = [c for c in COLUNAS if c not in linha]
        if faltando:
            incompletas.append(f"{caminho}: {', '.join(faltando)}")
        for coluna, valor in linha.items():
            if valor is not True and not str(valor).strip():
                vazias.append(f"{caminho}.{coluna}")
    check(
        "toda linha responde a todas as colunas"
        + (f" — INCOMPLETAS: {'; '.join(incompletas)}" if incompletas else ""),
        not incompletas,
    )
    check(
        "toda lacuna declarada tem motivo escrito"
        + (f" — VAZIAS: {', '.join(vazias)}" if vazias else ""),
        not vazias,
    )

    # --- o placar, que é o produto deste gate --------------------------------------------
    total = len(MATRIZ) * len(COLUNAS)
    grava = sum(1 for l in MATRIZ.values() for v in l.values() if v is True)
    na = sum(1 for l in MATRIZ.values() for v in l.values() if str(v).startswith("n/a:"))
    lacuna = total - grava - na
    print(
        f"\n  cobertura: {grava}/{total} gravam · {na} não se aplicam · "
        f"{lacuna} lacunas conhecidas"
    )

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ toda superfície de agente é autenticada e declara o que grava.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
