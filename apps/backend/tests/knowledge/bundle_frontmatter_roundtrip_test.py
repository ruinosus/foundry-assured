"""O frontmatter atravessa a adaptação e PARA antes do índice.

DUAS METADES DE UMA DECISÃO SÓ, e é por isso que elas moram no mesmo gate:

  adapt_openwiki      PRESERVA  — a procedência OKF é do documento, e some se for jogada fora
  ingest_docbundles   RETIRA    — o corpo da página É o texto indexado; YAML ali vira corpus

A auditoria de 2026-09-02 registrou a primeira metade como gap G1 e a segunda como o motivo
real do descarte — que nunca foi o `docbundle.schema.json` (13 propriedades, todas de
manifest; zero ocorrências de `content`/`body`/`frontmatter`/`hash`). Preservar sem retirar
faria o modelo citar `generated:` como se fosse conteúdo da página.

O TESTE É PONTA A PONTA de propósito. Uma versão anterior deste gate casava o texto-fonte do
adaptador com `inspect.getsource`; isso passa a verificar como o código está escrito em vez
do que ele faz, e quebra no primeiro `black` sem que nada tenha regredido.

    uv run python -m tests.knowledge.bundle_frontmatter_roundtrip_test
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from app.modules.knowledge.internal.adapt_openwiki import _split_front_matter, adapt
from app.modules.knowledge.internal.ingest_docbundles import collect_pages

PAGINA = (
    "---\n"
    "type: concept\n"
    "title: Pipeline de conhecimento\n"
    'generated: { by: "openwiki/0.4.3", at: "2026-09-02T14:30:00+00:00" }\n'
    "---\n"
    "\n"
    "## Visão geral\n"
    "\n"
    "Prosa citando `apps/backend/app/main.py`.\n"
)

PAGINA_COM_H1 = (
    "---\n"
    "type: concept\n"
    "title: Página com H1 próprio\n"
    'generated: { by: "openwiki/0.4.3", at: "2026-09-02T14:30:00+00:00" }\n'
    "---\n"
    "\n"
    "# Título próprio da página\n"
    "\n"
    "Prosa citando `apps/backend/app/registry.py`.\n"
)


def _wiki_falsa(raiz: Path) -> Path:
    """Um repositório mínimo com saída de OpenWiki: um índice e duas páginas de conteúdo."""
    wiki = raiz / "repo" / "openwiki"
    (wiki / "backend").mkdir(parents=True)
    (wiki / "index.md").write_text(
        "# Directories\n\n- [backend](backend/)\n", encoding="utf-8"
    )
    (wiki / "backend" / "index.md").write_text(
        "# Files\n\n- [Pipeline](knowledge-pipeline.md) - o pipeline\n"
        "- [Content](content-pipeline.md) - conteúdo com H1\n", encoding="utf-8"
    )
    (wiki / "backend" / "knowledge-pipeline.md").write_text(PAGINA, encoding="utf-8")
    (wiki / "backend" / "content-pipeline.md").write_text(PAGINA_COM_H1, encoding="utf-8")
    return raiz / "repo"


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    # --- o helper, que já estava certo: guarda de regressão para o passo seguinte
    fm, corpo = _split_front_matter(PAGINA)
    check("o split separa bloco e corpo", fm.startswith("---") and corpo.lstrip().startswith("##"))
    check("nada de YAML sobra no corpo devolvido", "generated:" not in corpo)

    # --- metade 1: a adaptação PRESERVA
    with tempfile.TemporaryDirectory() as tmp:
        # .resolve() como o CLI real faz (main(), abaixo) antes de chamar adapt(): sem isso,
        # em macOS `/tmp` é um symlink para `/private/tmp` e `_ordered_pages` (que resolve
        # os alvos) devolve paths fora do subpath de `wd` não resolvido.
        raiz = Path(tmp).resolve()
        repo = _wiki_falsa(raiz)
        bundle = adapt(
            repo=repo,
            component="comp",
            version="v1",
            out_dir=raiz / "out",
            wiki_dir=None,
            language="pt-br",
        )
        pagina_adaptada = (bundle / "pages" / "page-1.md").read_text(encoding="utf-8")

        check("a página adaptada mantém o bloco", pagina_adaptada.startswith("---\n"))
        check("…com a procedência intacta", '"openwiki/0.4.3"' in pagina_adaptada)
        check("…e com o corpo intacto", "apps/backend/app/main.py" in pagina_adaptada)

        # --- metade 2: o ingest RETIRA
        itens, _ = collect_pages(raiz / "out")
        check("collect_pages devolveu as duas páginas", len(itens) == 2)
        if len(itens) >= 1:
            texto_pipeline = itens[0][1].decode("utf-8")
            check(
                "nenhuma linha do blob é um delimitador de frontmatter",
                all(linha.strip() != "---" for linha in texto_pipeline.splitlines()),
            )
            check(
                "nenhuma chave OKF vaza para o índice",
                "generated:" not in texto_pipeline and "type:" not in texto_pipeline,
            )
            check("o cabeçalho do ingest continua na frente", texto_pipeline.startswith("# "))
            check("a prosa sobreviveu", "apps/backend/app/main.py" in texto_pipeline)
        if len(itens) >= 2:
            texto_content = itens[1][1].decode("utf-8")
            # Check that the original H1 line is stripped. After stripping, the blob should start with
            # "# comp v1 — Página com H1 próprio" (the qualified header from collect_pages), then blank line,
            # then "Prosa citando..." (the body without the original H1). The original "# Título próprio da página"
            # should not survive.
            lines = texto_content.split("\n")
            has_original_h1 = any(line == "# Título próprio da página" for line in lines)
            check(
                "o H1 próprio da página não sobrevive ao índice (guarda a ordem strip→H1)",
                not has_original_h1
            )

    print(f"\n{'❌' if falhas else '✅'} {len(falhas)} failure(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
