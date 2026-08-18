"""As citações falam o vocabulário do FRAMEWORK, e os dois lados concordam.

POR QUE ISTO EXISTE. O painel de evidências é a peça central da história de assurance deste
produto — é ele que mostra de onde cada afirmação veio. O dado que o alimenta atravessa uma
fronteira de linguagem (Python → SSE → TypeScript), e uma fronteira assim quebra em silêncio: o
backend renomeia um campo, o painel lê `undefined`, e a tela mostra "sem fontes" — que é
indistinguível de uma resposta que de fato não citou nada. Falha grave com aparência de cosmética.

O VOCABULÁRIO NÃO É NOSSO, e essa é a mudança que este teste guarda. Pesquisado e medido:

    agent_framework.Annotation          type="citation" · title · url · snippet · annotated_regions
    langchain_core.messages.Citation    type · id · url · title · start_index · end_index · cited_text

Os dois frameworks já tinham o tipo, e nós tínhamos inventado `{index, source, url, content}` —
o mesmo dado com nomes próprios. A troca alinha ao canônico.

O TRANSPORTE CONTINUA SENDO NOSSO, e isso é lacuna medida, não escolha: o protocolo AG-UI tem 38
eventos e NENHUM de citação (`CustomEvent` é o mecanismo que ele mesmo prevê para carga fora do
padrão), e o adapter `agent_framework_ag_ui` não propaga `annotations` — o conversor lê `messageId`
e `delta` de um TextContent e descarta o resto. No dia em que propagar, apaga-se o evento e nada
mais muda, porque a FORMA já é a deles. Este teste é o que garante isso.
"""

from __future__ import annotations

import pathlib
import re
import sys

import app as _app

RAIZ = pathlib.Path(_app.__file__).resolve().parent.parent
PAINEL = RAIZ.parent / "frontend" / "components" / "console" / "EvidencePanel.tsx"

#: Os campos canônicos do `agent_framework.Annotation` que usamos. `index` fica ao lado porque
#: amarra a citação `[n]` do texto ao item da lista — o `annotated_regions` do framework faria isso
#: por posição de caractere, e o nosso prompt cita por número.
CANONICOS = ("type", "title", "url", "snippet")


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    # --- o tipo do framework é o que dizemos que é -----------------------------------------
    from agent_framework import Annotation

    campos = set(getattr(Annotation, "__annotations__", {}))
    check(
        f"`agent_framework.Annotation` ainda tem os campos que adotamos ({', '.join(CANONICOS)})",
        set(CANONICOS) <= campos,
    )

    # --- o backend emite nessa forma --------------------------------------------------------
    fonte = (RAIZ / "app" / "modules" / "grounded" / "internal" / "grounded.py").read_text("utf-8")
    trecho = fonte[fonte.index("sources = ["):fonte.index("stream = await client.responses.create")]
    emitidos = set(re.findall(r'"(\w+)":', trecho))
    check(
        "o backend emite os campos canônicos" + (f" — falta {set(CANONICOS) - emitidos}" if not set(CANONICOS) <= emitidos else ""),
        set(CANONICOS) <= emitidos,
    )
    check("…e `index`, que amarra a citação [n] ao item", "index" in emitidos)
    check(
        "…e NÃO emite mais o vocabulário próprio (`source`/`content`)",
        not ({"source", "content"} & emitidos),
    )

    # --- o painel lê nessa forma ------------------------------------------------------------
    check("o painel de evidências existe onde este teste espera", PAINEL.is_file())
    if PAINEL.is_file():
        painel = PAINEL.read_text("utf-8")
        for campo in ("title", "snippet"):
            check(f"o painel lê `{campo}`", f"c.{campo}" in painel or f"v.{campo}" in painel)
        # Compatibilidade com a forma anterior: uma aba aberta durante o deploy continua recebendo
        # eventos do backend antigo, e um painel que esvazia no meio da conversa parece resposta
        # sem fonte.
        check(
            "o painel ainda aceita a forma ANTERIOR (aba aberta durante o deploy)",
            "v.source" in painel and "v.content" in painel,
        )

    if falhas:
        print(
            f"\n❌ {len(falhas)} verificação(ões) falharam. O painel de evidências quebra em"
            " SILÊNCIO: campo renomeado vira `undefined`, e a tela mostra 'sem fontes' — que é"
            " indistinguível de uma resposta que não citou nada."
        )
        return 1
    print("\n✅ as citações falam o vocabulário do framework, e os dois lados concordam.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
