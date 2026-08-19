"""As citações falam o vocabulário do FRAMEWORK, e os dois lados concordam.

POR QUE ISTO EXISTE. A evidência de cada resposta — de onde veio cada afirmação — é a peça
central da história de assurance deste produto. Hoje ela mora SOB CADA MENSAGEM (não mais num
painel lateral com a última resposta; ver `MessageEvidence.tsx`), mas quem efetivamente lê o
payload bruto do evento SSE e o traduz para o vocabulário que o resto da tela consome é
`lib/citations.tsx` — é ali, na função `normalizar()`, que a fronteira de linguagem (Python → SSE
→ TypeScript) é atravessada. E uma fronteira assim quebra em silêncio: o backend renomeia um
campo, `normalizar()` lê `undefined`, a citação some do array e a tela mostra "sem fontes" — que é
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
# NÃO é mais `EvidencePanel.tsx` — aquele componente hoje só renderiza as garantias estáticas de
# assurance (fidelity/access/evaluated) e não lê citação nenhuma, de propósito (ver comentário no
# topo do próprio arquivo). Quem lê o payload bruto do evento `sources` e traduz para o
# vocabulário canônico é `lib/citations.tsx` — é o único lugar do frontend que faz essa tradução;
# `MessageEvidence.tsx` e `SourceViewer.tsx`, que exibem a citação sob a resposta e destacam o
# trecho no documento, só consomem o `Citation` já normalizado por este arquivo.
CONSUMIDOR = RAIZ.parent / "frontend" / "lib" / "citations.tsx"

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

    # --- o consumidor real lê nessa forma -----------------------------------------------------
    check("o consumidor de citações existe onde este teste espera", CONSUMIDOR.is_file())
    if CONSUMIDOR.is_file():
        consumidor = CONSUMIDOR.read_text("utf-8")
        # Precisão equivalente à leitura anterior (`c.campo` literal, não "existe em algum lugar
        # do arquivo") — checar substring solta passaria com o campo só num comentário.
        for campo in ("title", "url", "snippet", "index"):
            check(f"o consumidor lê `{campo}`", f"c.{campo}" in consumidor)
        # Compatibilidade com a forma anterior: uma aba aberta durante o deploy continua recebendo
        # eventos do backend antigo (`source`/`content`), e uma citação que esvazia no meio da
        # conversa parece resposta sem fonte. A tolerância mora na mesma função (`normalizar()`)
        # que faz a tradução — não em `MessageEvidence.tsx`, que só vê o `Citation` já traduzido.
        check(
            "o consumidor ainda aceita a forma ANTERIOR (aba aberta durante o deploy)",
            "c.source" in consumidor and "c.content" in consumidor,
        )

    if falhas:
        print(
            f"\n❌ {len(falhas)} verificação(ões) falharam. A evidência sob a resposta quebra em"
            " SILÊNCIO: campo renomeado vira `undefined`, e a tela mostra 'sem fontes' — que é"
            " indistinguível de uma resposta que não citou nada."
        )
        return 1
    print("\n✅ as citações falam o vocabulário do framework, e os dois lados concordam.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
