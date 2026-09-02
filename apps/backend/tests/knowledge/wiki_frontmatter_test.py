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

from app.modules.knowledge.internal.wiki_builder import render_page, stamp_verified

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

    carimbada = stamp_verified(pagina(), verifier="wiki-verifier", version="1")
    meta_v = frontmatter(carimbada)
    check(
        "verified é lista com um evento de processo",
        [e["by"] for e in meta_v.get("verified", [])] == ["process:wiki-verifier/1"],
    )
    check(
        "verified[].at tem offset explícito",
        str(meta_v["verified"][0]["at"]).endswith("+00:00"),
    )
    check(
        "o verificador nunca é human: (ADR-023)",
        not meta_v["verified"][0]["by"].startswith("human:"),
    )
    check(
        "generated sobrevive ao carimbo",
        meta_v["generated"] == frontmatter(pagina())["generated"],
    )
    check("o corpo sobrevive ao carimbo", carimbada.endswith(CORPO))

    meta_legado = {
        "type": "doc",
        "verified": {"by": "process:legacy-verifier/1", "at": "2026-01-01T00:00:00+00:00"},
    }
    bloco_legado = yaml.safe_dump(meta_legado, sort_keys=False, allow_unicode=True).rstrip("\n")
    pagina_legada = f"---\n{bloco_legado}\n---\n\n{CORPO}"
    carimbada_legado = stamp_verified(pagina_legada, verifier="wiki-verifier", version="1")
    verified_legado = frontmatter(carimbada_legado).get("verified")
    # Forma defensiva (não `e["by"] for e in ...`): se a normalização regredir, o formato de
    # `verified_legado` pode deixar de ser uma lista de mapas — e a checagem deve reportar
    # `✗` pelo nome, não estourar exceção antes de chegar em `check()`.
    obtidos_legado = (
        [e.get("by") if isinstance(e, dict) else e for e in verified_legado]
        if isinstance(verified_legado, list)
        else verified_legado
    )
    check(
        "normalização do mapa `verified` solto legado: vira lista de um antes de acrescentar (§5.2)",
        obtidos_legado == ["process:legacy-verifier/1", "process:wiki-verifier/1"],
    )

    duas = stamp_verified(carimbada, verifier="fidelity-gate", version="1")
    check(
        "carimbar de novo ACRESCENTA, não substitui",
        [e["by"] for e in frontmatter(duas)["verified"]]
        == ["process:wiki-verifier/1", "process:fidelity-gate/1"],
    )

    print(f"\n{'❌' if falhas else '✅'} {len(falhas)} failure(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
