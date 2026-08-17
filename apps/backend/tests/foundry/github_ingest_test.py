"""A importação do GitHub é a ÚNICA peça de código nosso — e por isso a mais testada.

Ela existe porque não há knowledge source de GitHub em primeira parte (o conector do Logic Apps
lê issues e PRs; `WebKnowledgeSource` é Bing público; a galeria não tem GitHub). Sendo nossa,
carrega os riscos que o SDK normalmente absorveria:

  * **o token é de terceiro** — não pode aparecer em resposta, em log nem em nome de blob;
  * **o volume é do cliente** — um monorepo tem de bater num teto explícito, não na memória;
  * **o que ficou de fora tem de ser dito** — uma base que indexou 40 de 400 arquivos e não avisa
    responde com confiança sobre um corpus que ela não tem. É o defeito que o mecanismo de
    assurance deste repositório existe para impedir, e aqui ele nasceria da própria ingestão.

Offline: `_get` e `upload_files` são substituídos: nada de rede, nada de credencial.

    uv run python -m tests.foundry.github_ingest_test
"""

from __future__ import annotations

import base64
import sys

from app.modules.foundry.internal import github_source as gh

TOKEN = "ghp_TOKEN_SECRETO_QUE_NAO_PODE_VAZAR"


def _fake_tree(paths_sizes, truncated=False):
    return {
        "truncated": truncated,
        "tree": [
            {"type": "blob", "path": p, "size": s, "sha": f"sha-{i}"}
            for i, (p, s) in enumerate(paths_sizes)
        ],
    }


def main() -> int:
    falhas: list[str] = []
    chamadas: list[str] = []
    subidos: dict = {}

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    tree = _fake_tree(
        [
            ("README.md", 100),
            ("docs/guia.md", 200),
            ("docs/sub/outro.md", 150),
            ("node_modules/pacote/index.js", 50),   # diretório ignorado
            (".git/config", 10),                    # diretório ignorado
            ("app/main.py", 300),                   # extensão não indexável
            ("imagem.png", 400),                    # extensão não indexável
            ("enorme.md", 99 * 1024 * 1024),        # acima do teto por arquivo
        ]
    )

    def fake_get(url: str, token: str) -> dict:
        chamadas.append(url)
        # A guarda mais importante deste arquivo: o token chega às chamadas, e só a elas.
        if token != TOKEN:
            raise AssertionError("o token não chegou à chamada")
        if url.endswith("/repos/org/repo"):
            return {"default_branch": "main"}
        if "/git/trees/" in url:
            return tree
        if "/git/blobs/" in url:
            return {"encoding": "base64", "content": base64.b64encode(b"conteudo").decode()}
        raise AssertionError(f"URL inesperada: {url}")

    def fake_upload(kb_name, files):
        subidos["kb"] = kb_name
        subidos["files"] = files
        return {"container": "kb-teste", "files": [{"name": n, "bytes": len(d)} for n, d in files]}

    gh._get, gh.upload_files = fake_get, fake_upload

    out = gh.ingest_repo("teste", "org/repo", TOKEN)

    print("— o que entrou e o que ficou de fora")
    check("os 3 markdown foram importados", out["ingested"] == 3)
    check("o branch default foi descoberto", out["branch"] == "main")
    nomes = [n for n, _ in subidos["files"]]
    # Container é plano: `docs/a/b.md` e `docs/c/b.md` colidiriam se só o basename subisse.
    check("o caminho é achatado com __ (preserva a origem na citação)",
          "docs__guia.md" in nomes and "docs__sub__outro.md" in nomes)
    check("node_modules e .git NÃO aparecem como pulados (ruído)",
          not any("node_modules" in s["path"] or ".git" in s["path"] for s in out["skipped_sample"]))
    check("arquivo de código e imagem entram como pulados (a pessoa esperava vê-los)",
          {"app/main.py", "imagem.png"} <= {s["path"] for s in out["skipped_sample"]})
    check("arquivo acima do teto é pulado com motivo",
          any(s["path"] == "enorme.md" and "grande" in s["reason"] for s in out["skipped_sample"]))
    check("a CONTAGEM de pulados é completa", out["skipped_count"] == 3)

    print("\n— o token não escapa")
    achatado = repr(out) + repr(subidos)
    check("o token não está na resposta", TOKEN not in achatado)
    check("o token não está em nome de blob", not any(TOKEN in n for n in nomes))
    check("o token não está em nenhuma URL chamada", not any(TOKEN in u for u in chamadas))

    print("\n— tetos e sinalização de incompletude")
    original = gh.MAX_FILES_INGESTED
    gh.MAX_FILES_INGESTED = 1
    limitado = gh.ingest_repo("teste", "org/repo", TOKEN)
    gh.MAX_FILES_INGESTED = original
    check("o teto de importação é respeitado", limitado["ingested"] == 1)
    check("o que passou do teto é reportado com o motivo",
          any("teto" in s["reason"] for s in limitado["skipped_sample"]))

    gh._get = lambda url, token: (
        {"default_branch": "main"} if url.endswith("/repos/org/repo")
        else _fake_tree([("a.md", 10)], truncated=True) if "/git/trees/" in url
        else {"encoding": "base64", "content": base64.b64encode(b"x").decode()}
    )
    trunc = gh.ingest_repo("teste", "org/repo", TOKEN)
    # Se o GitHub truncou a árvore, a lista já estava incompleta ANTES dos nossos tetos.
    check("truncamento do próprio GitHub é sinalizado", trunc["tree_truncated_by_github"] is True)

    print("\n— entradas inválidas")

    def recusa(fn) -> bool:
        try:
            fn()
        except gh.GitHubError:
            return True
        except Exception:
            return False
        return False

    check("repositório fora do formato org/nome é recusado",
          recusa(lambda: gh.ingest_repo("teste", "repo-sozinho", TOKEN)))
    check("token vazio é recusado antes de qualquer chamada",
          recusa(lambda: gh.ingest_repo("teste", "org/repo", "")))

    gh._get = lambda url, token: (
        {"default_branch": "main"} if url.endswith("/repos/org/repo")
        else _fake_tree([("imagem.png", 10)])
    )
    check("repositório sem arquivo indexável dá erro explicativo, não base vazia",
          recusa(lambda: gh.ingest_repo("teste", "org/repo", TOKEN)))

    if falhas:
        print(f"\n❌ {len(falhas)} asserção(ões) falharam.")
        return 1
    print("\n✅ importa o que serve, diz o que ficou fora, e o token não escapa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
