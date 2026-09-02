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


def main() -> int:
    falhas: list[str] = []

    for md in sorted((REPO / "docs").rglob("*.md")):
        texto = md.read_text(encoding="utf-8", errors="replace")
        if not texto.startswith("---"):
            continue  # sem bloco não é erro aqui; frontmatter em docs/ é opcional
        rel = md.relative_to(REPO)
        m = BLOCO.match(texto)
        if not m:
            falhas.append(f"{rel}: bloco `---` aberto e não fechado")
            continue
        try:
            dados = yaml.safe_load(m.group(1))
        except yaml.YAMLError as exc:
            falhas.append(f"{rel}: {str(exc).splitlines()[0]}")
            continue
        if dados is not None and not isinstance(dados, dict):
            falhas.append(f"{rel}: frontmatter não é um mapa, e sim {type(dados).__name__}")

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
