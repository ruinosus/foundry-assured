"""Gate: o recorte do techdocs em níveis de acesso está coerente — e não vaza.

Três invariantes, todas offline (nem Azure, nem rede):

  1. COBERTURA — toda página do wiki-bundle cai em exatamente um componente. Página órfã
     desaparece do domínio em silêncio; página em dois componentes aparece duplicada.
  2. FAIL-CLOSED — todo componente tem entrada na classificação. Componente sem entrada é
     invisível para todo mundo, o que é seguro mas parece bug de ingestão.
  3. ALCANCE — simula o trim e exige o resultado esperado por identidade.

A terceira existe por um erro cometido ao escrever estes arquivos. Os grupos são avaliados por
**OR**: o documento é legível por quem estiver em QUALQUER grupo carimbado. O instinto ao
descrever um nível "interno" é escrever `["public", "internal"]`, pensando em acumular
permissão — e isso LIBERA o documento para quem só tem `public`. A lista correta é o conjunto de
quem ALCANÇA o nível, então o mais restrito lista MENOS grupos, não mais.

O erro não produz exceção nem resultado vazio: produz um vazamento silencioso que só apareceria
com duas identidades reais consultando o índice de verdade. Este gate reproduz esse teste em
aritmética de conjuntos, sem nuvem, para que ele rode em todo push.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import app

RAIZ = Path(app.__file__).resolve().parent.parent.parent.parent
CONHECIMENTO = RAIZ / "knowledge"

# Como `infra/entra/create-acl-identities.sh` cria as identidades de teste.
A = {"public", "internal", "confidential"}   # cleared
B = {"public"}                               # public-only


def main() -> int:
    tiers = json.loads((CONHECIMENTO / "techdocs-tiers.json").read_text(encoding="utf-8"))["components"]
    classif = {k: v for k, v in
               json.loads((CONHECIMENTO / "techdocs-classification.json").read_text(encoding="utf-8")).items()
               if not k.startswith("$")}

    bundle = CONHECIMENTO / "wiki-bundle"
    origens = [d for d in bundle.iterdir() if d.is_dir()] if bundle.exists() else []
    if not origens:
        print(f"✖ nenhum componente em {bundle}", file=sys.stderr)
        return 1
    versoes = sorted((d for d in origens[0].iterdir() if d.is_dir()), key=lambda d: d.name)
    manifesto = json.loads((versoes[-1] / "manifest.json").read_text(encoding="utf-8"))
    titulos_bundle = {p["title"] for p in manifesto["pages"]}

    falhas: list[str] = []

    mapeadas = [t for c in tiers.values() for t in c["pages"]]
    if len(mapeadas) != len(set(mapeadas)):
        dups = sorted({t for t in mapeadas if mapeadas.count(t) > 1})
        falhas.append(f"páginas em mais de um componente: {dups}")
    if orfas := sorted(titulos_bundle - set(mapeadas)):
        falhas.append(f"páginas do bundle sem componente (sumiriam do techdocs): {orfas}")
    if fantasmas := sorted(set(mapeadas) - titulos_bundle):
        falhas.append(f"títulos mapeados que não existem no bundle: {fantasmas}")

    if sem_classe := sorted(set(tiers) - set(classif)):
        falhas.append(f"componentes sem classificação (invisíveis para todos): {sem_classe}")
    if sem_comp := sorted(set(classif) - set(tiers)):
        falhas.append(f"classificação para componente inexistente: {sem_comp}")

    for comp, grupos in classif.items():
        if not (A & set(grupos)):
            falhas.append(f"`{comp}`: a identidade CLEARED não alcança — o teste A/B nunca passaria")

    publicos = [c for c, g in classif.items() if B & set(g)]
    esperado_publico = [c for c, g in classif.items() if set(g) >= A]
    if sorted(publicos) != sorted(esperado_publico):
        falhas.append(
            f"a identidade PUBLIC-ONLY alcança {sorted(publicos)}, mas o nível totalmente aberto "
            f"é {sorted(esperado_publico)} — provável inversão: um nível restrito listando "
            "`public` LIBERA o conteúdo, porque os grupos são avaliados por OR"
        )

    for f in falhas:
        print(f"  ✗ {f}")
    if falhas:
        print(f"\n✖ {len(falhas)} problema(s) no recorte do techdocs.", file=sys.stderr)
        return 1

    print(f"  ✓ {len(titulos_bundle)} páginas → {len(tiers)} componentes, sem órfã nem duplicata")
    print("  ✓ todo componente classificado (nada fail-closed por engano)")
    print(f"  ✓ cleared alcança {len(classif)}/{len(classif)}; public-only alcança "
          f"{len(publicos)}/{len(classif)} — o trim discrimina")
    print("\n✅ o recorte do techdocs está coerente e não vaza nível.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
