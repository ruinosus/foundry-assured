#!/usr/bin/env python3
"""Deriva os doc bundles do techdocs a partir do wiki-bundle do selfwiki.

POR QUE DERIVAR, e não commitar três bundles prontos: o conteúdo já existe uma vez em
`knowledge/wiki-bundle/`, gerado pela wiki. Uma segunda cópia divergiria na primeira
regeneração — e divergência de conteúdo não dá erro, só faz um domínio responder com a versão
velha enquanto o outro responde com a nova. O recorte é uma TRANSFORMAÇÃO, então roda na hora
de ingerir.

O recorte em si NÃO está aqui: está em `knowledge/techdocs-tiers.json` (o que é cada coisa) e
`knowledge/techdocs-classification.json` (quem pode ler). RULE #6 — controle de acesso é dado.
Quem quiser mudar o recorte edita JSON; este arquivo não muda.

    python3 scripts/build-techdocs-bundles.py [diretório-de-saída]
"""

import json
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BUNDLE = RAIZ / "knowledge" / "wiki-bundle"
TIERS = RAIZ / "knowledge" / "techdocs-tiers.json"


def versao_mais_recente(componente: Path) -> Path:
    """A versão mais nova de um componente. O diretório guarda TODAS as versões já geradas — a
    regeneração da wiki não poda a anterior — e ingerir duas ao mesmo tempo colocaria conteúdo
    velho e novo lado a lado no índice, sem nada marcar o velho como obsoleto."""
    versoes = sorted((d for d in componente.iterdir() if d.is_dir()), key=lambda d: d.name)
    if not versoes:
        sys.exit(f"✖ sem versões em {componente}")
    return versoes[-1]


def main() -> int:
    saida = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / ".techdocs-staging"
    tiers = json.loads(TIERS.read_text(encoding="utf-8"))["components"]

    origens = [d for d in BUNDLE.iterdir() if d.is_dir()] if BUNDLE.exists() else []
    if not origens:
        sys.exit(f"✖ nenhum componente em {BUNDLE}")
    src = versao_mais_recente(origens[0])
    manifesto = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    por_titulo = {p["title"]: p for p in manifesto["pages"]}

    # Toda página do bundle tem que cair em exatamente um componente. Página não mapeada
    # sumiria do techdocs em silêncio; página mapeada duas vezes apareceria duplicada.
    mapeadas = [t for c in tiers.values() for t in c["pages"]]
    if len(mapeadas) != len(set(mapeadas)):
        sys.exit("✖ há páginas mapeadas em mais de um componente em techdocs-tiers.json")
    faltando = sorted(set(por_titulo) - set(mapeadas))
    sobrando = sorted(set(mapeadas) - set(por_titulo))
    if faltando or sobrando:
        if faltando:
            print(f"✖ páginas do bundle sem componente: {faltando}", file=sys.stderr)
        if sobrando:
            print(f"✖ títulos em techdocs-tiers.json que não existem no bundle: {sobrando}", file=sys.stderr)
        return 1

    if saida.exists():
        shutil.rmtree(saida)
    versao = src.name

    for comp, cfg in tiers.items():
        destino = saida / comp / versao
        (destino / "pages").mkdir(parents=True)
        paginas = []
        for i, titulo in enumerate(cfg["pages"], 1):
            orig = por_titulo[titulo]
            nome = f"page-{i}.md"
            shutil.copyfile(src / orig["file"], destino / "pages" / nome)
            paginas.append({"id": f"page-{i}", "title": titulo, "order": i,
                            "file": f"pages/{nome}", "audience": orig.get("audience", "base")})
        novo = dict(manifesto)
        novo.update({
            "key": f"{comp}-{versao}", "title": f"{cfg['title']} {versao}",
            "component": comp, "componentVersion": versao, "pages": paginas,
            # `groups` fica NULO de propósito: quem carimba é o acl_setup, a partir de
            # techdocs-classification.json. Dois lugares declarando acesso divergem.
            "groups": None,
        })
        (destino / "manifest.json").write_text(json.dumps(novo, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  ✓ {comp:22} {len(paginas):2} páginas")

    print(f"\n  bundles em {saida}")
    print(f"  ingerir com: TECHDOCS_DOCBUNDLES={saida} ACL_CLASSIFICATION={RAIZ}/knowledge/techdocs-classification.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
