"""As páginas que o `wiki_builder` escreve carregam procedência OKF v0.2.

Fecha o gap G2 da auditoria de 2026-09-02: nenhum conceito de nenhum bundle carregava
`generated`, então toda página lia como não-atribuída E não-verificada para um consumidor
OKF — inclusive as que o verificador tinha reescrito.

A REGRA QUE ESTE GATE EXISTE PARA SEGURAR: o modelo não escreve o frontmatter. Se ele
emitir um bloco próprio, `render_page` o descarta e escreve o dele por cima. Um documento
capaz de declarar o próprio `type` e o próprio ator é um documento capaz de forjar a
própria procedência — e o prompt é a superfície mais barata de influenciar que existe.

    uv run python -m tests.knowledge.wiki_frontmatter_test
"""

from __future__ import annotations

import sys

import yaml

from app.modules.knowledge.internal.wiki_builder import render_page

CORPO = "## Visão geral\n\nProsa citando `apps/backend/app/main.py`.\n"


def frontmatter(texto: str) -> dict:
    assert texto.startswith("---"), "página sem bloco de frontmatter"
    _, _, resto = texto.partition("---")
    bloco, sep, _ = resto.partition("\n---")
    assert sep, "bloco de frontmatter não fechado"
    return yaml.safe_load(bloco) or {}


def pagina(corpo: str = CORPO) -> str:
    return render_page(
        body=corpo,
        title="Ponto de entrada do backend",
        producer="foundry-wiki-builder",
        version="gpt-5-mini",
    )


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    meta = frontmatter(pagina())
    check("type presente e não vazio (SPEC.md:187)", bool(str(meta.get("type", "")).strip()))
    check("title veio do chamador", meta.get("title") == "Ponto de entrada do backend")
    check(
        "generated.by é <produtor>/<versão>",
        meta.get("generated", {}).get("by") == "foundry-wiki-builder/gpt-5-mini",
    )
    check(
        "generated.at tem offset explícito (SPEC.md:284)",
        str(meta.get("generated", {}).get("at", "")).endswith("+00:00"),
    )
    check(
        "generated.by nunca reivindica human:",
        not str(meta["generated"]["by"]).startswith("human:"),
    )
    check("sem verified: ausência é 'unverified' (SPEC.md:405)", "verified" not in meta)
    check(
        "description ausente não vira chave vazia",
        "description" not in meta,
    )

    check("o corpo sai intacto abaixo do bloco", pagina().endswith(CORPO))

    forjada = pagina("---\ntype: Forjado\ngenerated: {by: 'human:alguem'}\n---\n\n## Real\n")
    meta_f = frontmatter(forjada)
    check("bloco emitido pelo modelo não vira o frontmatter", meta_f.get("type") != "Forjado")
    check(
        "…e o ator continua sendo o do produtor",
        meta_f["generated"]["by"] == "foundry-wiki-builder/gpt-5-mini",
    )
    check("…e o corpo real sobrevive", forjada.rstrip().endswith("## Real"))

    com_desc = render_page(
        body=CORPO, title="T", description="Uma frase.",
        producer="p", version="v",
    )
    check("description passa quando dada", frontmatter(com_desc)["description"] == "Uma frase.")

    print(f"\n{'❌' if falhas else '✅'} {len(falhas)} failure(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
