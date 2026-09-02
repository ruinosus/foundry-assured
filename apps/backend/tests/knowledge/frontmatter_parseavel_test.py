"""Um arquivo que PARECE ter frontmatter precisa ter frontmatter que parseia.

POR QUE ISTO É UM GATE E NÃO UMA CONVENÇÃO. `ingest.py:162-165` sai com erro num bloco
torto — de propósito, porque um YAML quebrado tornaria "declarei acesso errado"
indistinguível de "não declarei acesso" (ver `frontmatter.py:41-49`). Mas `docs/` nunca é
ingerido, então um bloco quebrado lá não tem sintoma nenhum: `startswith("---")` conta o
arquivo como tendo frontmatter, e todo mundo que só olha a primeira linha concorda.

Foi assim que `2026-08-17-user-managed-agents-and-knowledge-design.md` passou meses com um
`: ` dentro de escalar não citado. Este gate mede o que o parser mede, não o que o olho vê.

CONTEÚDO ESTÁ FORA DE ESCOPO. Não se cobra `type`, nem `title`, nem conformidade OKF — a
regra de `docs/` é a do `DOCS-STANDARD.md`, não a do OKF. Só se cobra que o YAML parseie.

A classificação é pura e testada contra entradas sintéticas, porque após o repositório estar
limpo uma varredura só exercita o caminho feliz. Ramos de erro sem teste em `docs/` ficariam
sem cobertura, e um gate cujos ramos de erro nunca rodam é o defeito que a auditoria de
2026-09-02 mediu.

    uv run python -m tests.knowledge.frontmatter_parseavel_test
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

import app as _app

BACKEND = Path(_app.__file__).resolve().parent.parent
REPO = BACKEND.parents[1]

#: `\A---\n … \n---` — o mesmo recorte de `knowledge/internal/frontmatter.py:26`, para que
#: este gate e o parser de produção discordem sobre zero arquivos.
BLOCO = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


def _problema(texto: str) -> str | None:
    """A descrição do problema no bloco de frontmatter, ou None se não há problema.

    Pura e separada do loop porque é o que se consegue testar. Varrer `docs/` só
    exercita o caminho feliz depois que o repositório está limpo — os três ramos de
    erro ficariam sem cobertura nenhuma, e um gate cujos ramos de erro nunca rodam
    é o defeito que a auditoria de 2026-09-02 mediu, não a defesa contra ele.
    """
    if not texto.startswith("---"):
        return None  # sem bloco não é erro aqui; frontmatter em docs/ é opcional

    m = BLOCO.match(texto)
    if not m:
        return "bloco `---` aberto e não fechado"

    try:
        dados = yaml.safe_load(m.group(1))
    except yaml.YAMLError as exc:
        return str(exc).splitlines()[0]

    if dados is not None and not isinstance(dados, dict):
        return f"frontmatter não é um mapa, e sim {type(dados).__name__}"

    return None


def main() -> int:
    falhas: list[str] = []

    # Testes sintéticos — cobrem os cinco ramos da classificação.
    def check(nome: str, cond: bool) -> None:
        if not cond:
            falhas.append(f"[lógica] {nome}")

    # Ramo 1: texto sem `---` inicial → None
    check("sem --- inicial", _problema("# Heading\nconteúdo") is None)

    # Ramo 2: bloco bem-formado que parseia para um mapa → None
    check("bloco válido e mapa", _problema("---\ntitle: Teste\n---\nconteúdo") is None)

    # Ramo 3: bloco que abre e não fecha → erro não-None
    check(
        "bloco não fechado",
        _problema("---\ntitle: Teste\nconteúdo") is not None,
    )

    # Ramo 4: bloco cujo YAML levanta exceção (`: ` unquoted)
    check(
        "YAML com erro de sintaxe",
        _problema("---\ndescription: API oficial: 23 operações\n---\nconteúdo")
        is not None,
    )

    # Ramo 5: bloco que parseia para não-mapa (lista YAML)
    check(
        "YAML que não é mapa",
        _problema("---\n- item1\n- item2\n---\nconteúdo") is not None,
    )

    # Falhas na lógica sinalizadas em primeiro lugar.
    if falhas:
        for f in falhas:
            print(f"  ✗ {f}")
        print(
            f"\n❌ {len(falhas)} ramo(s) da lógica de classificação falhou(aram)."
        )
        return 1

    # Varredura de `docs/` contra a lógica testada.
    for md in sorted((REPO / "docs").rglob("*.md")):
        texto = md.read_text(encoding="utf-8", errors="replace")
        problema = _problema(texto)
        if problema:
            rel = md.relative_to(REPO)
            falhas.append(f"{rel}: {problema}")

    for f in falhas:
        print(f"  ✗ {f}")
    if falhas:
        print(f"\n❌ {len(falhas)} bloco(s) de frontmatter não parseiam.")
        print("   Valor com `: ` precisa de aspas. `ingest.py:162-165` sai com erro num destes.")
        return 1
    print("✅ todo bloco de frontmatter em docs/ parseia.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
