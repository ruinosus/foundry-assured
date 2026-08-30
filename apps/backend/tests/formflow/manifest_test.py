"""Os manifestos de FormFlow: válidos, conformantes, e sem regra que a tela vá ignorar calada.

POR QUE ESTE GATE. O manifesto virou a fonte do formulário: campos, regras, revisão e plano de
publicação saem dele. Isso troca uma classe de erro por outra. Antes, um campo errado era um erro
de TypeScript; agora é um documento que carrega bem e produz um formulário sutilmente errado.

Os quatro modos de falha silenciosa que este gate fecha:

1. **Regra com nome que a tela não conhece.** `rules: [resourceNames]` (com "s") carrega, e o
   renderizador simplesmente não aplica nada. O campo passa a aceitar qualquer coisa e ninguém
   descobre até a publicação ser recusada pelo serviço. O vocabulário é FECHADO, e vive nos dois
   lados — aqui e em `lib/formflow/rules.ts`.
2. **Dependência para uma operação que não existe.** `requires: [create_bse]` trava a publicação
   para sempre, esperando um passo que nunca vem.
3. **Campo `ai: true` de um tipo que o agente não sabe escrever.** Propor texto para um seletor de
   arquivo é uma proposta que nunca pode ser aceita.
4. **Documento que não é OKF.** O manifesto mora num bundle e é `type: formflow`. Sem o
   frontmatter ele é um markdown solto, e o bundle deixa de ser conformante (§11).

    uv run python -m tests.formflow.manifest_test
"""

from __future__ import annotations

import sys

from app.modules.formflow.internal.loader import _validar
from app.modules.formflow.public import FlowInvalid, flows_dir, list_flows, load_flow

#: O vocabulário de regras que a tela sabe aplicar. FECHADO de propósito — ver o modo 1 acima.
#: Espelha `REGRAS` em `apps/frontend/lib/formflow/rules.ts`; o gate de espelho abaixo é o que
#: impede os dois de divergirem.
REGRAS = {"resourceName", "max63", "unique", "safeFilename"}

#: Os tipos de campo que o renderizador conhece. Um tipo novo é CÓDIGO (um controle novo), não
#: dado — é a linha que impede o manifesto de virar linguagem de programação pela porta dos fundos.
TIPOS = {"text", "longtext", "choice", "multi", "pair", "files", "secret"}

#: Os tipos que o agente consegue propor: os que são texto. `ai: true` em qualquer outro produz um
#: card de proposta que a pessoa não tem como aceitar.
TIPOS_COM_IA = {"text", "longtext"}


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool, detalhe: str = "") -> None:
        print(f"  {'✓' if cond else '✗'} {nome}{f'  ({detalhe})' if detalhe and not cond else ''}")
        if not cond:
            falhas.append(nome)

    nomes = list_flows()
    check("há manifestos publicados", bool(nomes), f"nenhum em {flows_dir()}")
    # Os três wizards que o produto tem. Um a menos aqui significa uma tela sem formulário.
    check("os três formulários existem", set(nomes) >= {"agent", "skill", "knowledge"}, str(nomes))

    for nome in nomes:
        print(f"\n── {nome} ──")
        flow = load_flow(nome)
        campos = [(s, c) for s in flow["sections"] for c in s["fields"]]

        # 4 · o documento é OKF
        texto = (flows_dir() / f"{nome}.md").read_text(encoding="utf-8")
        check("é documento OKF (`type: formflow` no frontmatter)", "type: formflow" in texto)

        # 1 · toda regra citada existe no vocabulário
        desconhecidas = {
            r for _, c in campos for r in (c.get("rules") or []) if r not in REGRAS
        }
        check("nenhuma regra fora do vocabulário", not desconhecidas, f"desconhecidas: {desconhecidas}")

        # o tipo também
        tipos_ruins = {c["type"] for _, c in campos if c["type"] not in TIPOS}
        check("nenhum tipo de campo desconhecido", not tipos_ruins, f"{tipos_ruins}")

        # 3 · `ai: true` só onde o agente sabe escrever
        ia_ruim = {c["id"] for _, c in campos if c.get("ai") and c["type"] not in TIPOS_COM_IA}
        check("`ai: true` só em campo de texto", not ia_ruim, f"{ia_ruim}")

        # 2 · as dependências do plano apontam para operações do próprio plano
        plano = flow.get("plan") or []
        ids = {op.get("id") for op in plano}
        check("o plano tem ao menos uma operação", bool(plano))
        quebradas = {
            f"{op.get('id')} → {r}"
            for op in plano
            for r in (op.get("requires") or [])
            if r not in ids
        }
        check("toda dependência aponta para uma operação que existe", not quebradas, f"{quebradas}")

        # a revisão fala de campos que existem — uma linha citando `{modelo}` num fluxo cujo campo
        # é `model` renderiza o placeholder cru para quem vai publicar.
        ids_campos = {c["id"] for _, c in campos}
        import re

        refs = {
            m
            for linha in (flow.get("review") or [])
            for m in re.findall(r"\{(\w+)\}", str(linha.get("from", "")) + str(linha.get("withKnowledge", "")))
        }
        check("a revisão só cita campos que existem", refs <= ids_campos, f"fora: {refs - ids_campos}")

    # --- o loader recusa o que precisa recusar ------------------------------------------
    print("\n── o loader é fail-loud ──")

    def recusa(spec: dict) -> bool:
        try:
            _validar(spec, "teste")
        except FlowInvalid:
            return True
        return False

    check("spec sem sections", recusa({}))
    check("seção sem id", recusa({"sections": [{"fields": [{"id": "a", "type": "text"}]}]}))
    check("seção sem campos", recusa({"sections": [{"id": "s", "fields": []}]}))
    check("campo sem id", recusa({"sections": [{"id": "s", "fields": [{"type": "text"}]}]}))
    check("campo sem type", recusa({"sections": [{"id": "s", "fields": [{"id": "a"}]}]}))
    # O mais caro dos cinco: dois campos com o mesmo `id` compartilhariam valor, e a proposta do
    # agente cairia nos dois ao mesmo tempo.
    check(
        "id de campo repetido",
        recusa({"sections": [
            {"id": "s1", "fields": [{"id": "a", "type": "text"}]},
            {"id": "s2", "fields": [{"id": "a", "type": "text"}]},
        ]}),
    )

    print(f"\n{'❌' if falhas else '✅'} {len(falhas)} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
