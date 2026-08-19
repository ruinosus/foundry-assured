"""A conversa gravada guarda a evidência da resposta.

POR QUE ISTO EXISTE. Medido em 19/ago/2026: as mensagens do assistente no blob de conversa
tinham `annotations: nenhuma`. A evidência vivia só como evento ao vivo — recarregar a página
apagava a fonte de toda a conversa. Num produto chamado Assurance Console isso é falha, não
cosmética.

NÃO GUARDA CONTEÚDO: só título, url, índice e o trecho que já saiu na resposta. O direito de
LER o documento é verificado no clique (rota /source), nunca herdado do momento da resposta.
"""

from __future__ import annotations

import sys

from app.modules.conversations.internal import listing


def main() -> int:
    print("citações são gravadas junto da mensagem")
    falhas: list[str] = []

    def check(nome: str, ok: bool) -> None:
        print(f"  {'ok  ' if ok else 'FALHA'} {nome}")
        if not ok:
            falhas.append(nome)

    gravado: dict = {}

    class LojaFalsa:
        def append(self, user, agent, conv, messages):
            gravado["mensagens"] = messages

    # `listing` resolve a loja por chamada de função — trocar o atributo do MÓDULO é o que
    # intercepta. Patchar em outro lugar dá falso positivo (aconteceu antes neste repo).
    original = listing.store
    listing.store = lambda: LojaFalsa()
    try:
        listing.record_turn(
            "user-1", "selfwiki", "conv-1", "pergunta?", "resposta [1]",
            citations=[{"type": "citation", "title": "page-11.md", "url": "https://x/y/page-11.md",
                        "snippet": "trecho", "index": 1}],
        )
    finally:
        listing.store = original

    msgs = gravado.get("mensagens") or []
    check("gravou duas mensagens (pergunta + resposta)", len(msgs) == 2)

    assistente = next((m for m in msgs if m.get("role") == "assistant"), {})
    ann = assistente.get("annotations") or []
    check("a resposta carrega annotations", len(ann) == 1)
    check("a annotation tem o índice que amarra o [n]", (ann[0] if ann else {}).get("index") == 1)
    check("a annotation tem o título do documento", (ann[0] if ann else {}).get("title") == "page-11.md")
    check("a pergunta do usuário NÃO recebe annotations",
          "annotations" not in next((m for m in msgs if m.get("role") == "user"), {}))

    # Sem citação, o formato antigo continua idêntico — chamador existente não muda.
    gravado.clear()
    listing.store = lambda: LojaFalsa()
    try:
        listing.record_turn("user-1", "selfwiki", "conv-2", "p", "r")
    finally:
        listing.store = original
    m2 = next((m for m in (gravado.get("mensagens") or []) if m.get("role") == "assistant"), {})
    check("sem citação, a mensagem não ganha chave vazia", "annotations" not in m2)

    # O redator TEM de alcançar o trecho da citação. Sem isto, `annotations` seria o caminho
    # por onde conteúdo entra no blob sem passar pelo ponto único de escrita da ADR-023.
    from app.modules.conversations.internal.store import sanitize

    saneadas, tipos = sanitize([
        {"role": "assistant", "text": "ok",
         "annotations": [{"title": "d.md", "index": 1, "snippet": "contato: fulano@exemplo.com"}]},
    ])
    trecho_salvo = saneadas[0]["annotations"][0]["snippet"]
    check("o redator alcança annotations[].snippet", "fulano@exemplo.com" not in trecho_salvo)
    check("o redator reporta o tipo encontrado no trecho", len(tipos) > 0)
    check("título e índice atravessam intactos",
          saneadas[0]["annotations"][0]["title"] == "d.md"
          and saneadas[0]["annotations"][0]["index"] == 1)

    print()
    if falhas:
        print(f"FALHOU: {len(falhas)} verificação(ões)")
        return 1
    print("tudo certo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
