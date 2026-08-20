#!/usr/bin/env python3
"""Gate: as páginas do GitHub Pages não apontam para caminho que não existe mais.

O Pages serve `main:/docs`. O deploy dele sempre passa — ele copia bytes, não valida conteúdo —
então uma página pode ficar servindo links quebrados por meses com o ambiente verde. Foi o que
aconteceu: a landing linkava `docs/wiki` como "deep-wiki gerado" depois que a wiki mudou para
`openwiki/`, e nada reclamou.

Verifica dois tipos de link, ambos resolvíveis SEM rede:

  1. relativos (`presentation.html`) — o arquivo tem que existir dentro de docs/;
  2. do próprio repo (`github.com/<org>/<repo>/tree/main/<caminho>`) — o caminho tem que existir.

NÃO verifica URL externa: exigiria rede, tornaria o gate intermitente, e um link para fora
quebra por motivo que não está sob controle deste repositório. A exceção conhecida é o botão
"Abrir o app", que aponta para um FQDN de ambiente — ver o comentário ao lado dele no HTML.
"""

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DOCS = RAIZ / "docs"
REPO = re.compile(r"https://github\.com/[^/]+/[^/]+/(?:tree|blob)/[^/]+/(.+?)/?$")


def main() -> int:
    quebrados = []
    paginas = sorted(DOCS.glob("*.html"))
    for pag in paginas:
        for href in re.findall(r'href="([^"]+)"', pag.read_text(encoding="utf-8")):
            alvo = href.split("#")[0].split("?")[0]
            if not alvo:
                continue
            if m := REPO.match(alvo):
                if not (RAIZ / m.group(1)).exists():
                    quebrados.append((pag.name, href, f"o caminho `{m.group(1)}` não existe no repo"))
            elif not alvo.startswith(("http://", "https://", "mailto:")):
                if not (DOCS / alvo).exists():
                    quebrados.append((pag.name, href, f"`docs/{alvo}` não existe"))

    for pagina, href, porque in quebrados:
        print(f"  ✗ {pagina}: {href}\n      {porque}")
    if quebrados:
        print(f"\n✖ {len(quebrados)} link(s) publicados apontam para o que não existe.", file=sys.stderr)
        return 1
    print(f"  ✓ {len(paginas)} páginas: todo link relativo e todo caminho do repo resolvem")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
