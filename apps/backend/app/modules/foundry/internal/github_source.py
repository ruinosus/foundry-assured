"""GitHub → blob. A ÚNICA peça de código nosso nesta spec, e o levantamento explica por quê.

A MÁXIMA MAIOR exige demonstrar que se procurou antes de escrever. Procurei, e as três
alternativas de primeira parte falham para este caso:

  * **Conector GitHub do Logic Apps** — oficial, mas as ações são *issues, pull requests,
    secrets*. Não lê a árvore de arquivos de um repositório.
  * **`WebKnowledgeSource`** — é Bing público; não alcança repositório privado.
  * **Data Sources Gallery** — Blob, Table, ADLS, Cosmos, SQL, MySQL, OneLake, SharePoint.
    Nenhum é GitHub.

Então este arquivo faz o mínimo para voltar ao caminho oficial: lê os arquivos pela API do
GitHub e escreve no blob. **Do blob em diante tudo volta a ser Microsoft** —
`AzureBlobKnowledgeSource` faz chunking, embedding e indexação. A cola é a leitura, não o
pipeline.

O QUE MERECE ATENÇÃO, porque lida com token de terceiro e conteúdo de fonte não confiável:

**O token é do usuário e não é persistido.** Chega no corpo da requisição, é usado nas chamadas
e sai de escopo. Nunca vai para log, nunca para a resposta, nunca para o blob. Um token de
repositório privado no nosso log seria incidente.

**Nada de conteúdo do repositório vira instrução.** Os arquivos são DADOS que serão indexados.
Este módulo não os interpreta; só decide, por extensão e tamanho, o que sobe.

**Teto explícito, e o que ficou de fora é dito.** A spec registra como risco que
`gather_source` lê o repositório inteiro em memória. Aqui o teto é por arquivo, por quantidade e
por total, e o que passou do teto volta na resposta — truncar em silêncio faria a base parecer
completa quando não está, que é exatamente o defeito que o mecanismo de assurance existe para
impedir.
"""

from __future__ import annotations

import base64
import os
import re

from app.modules.foundry.internal.knowledge_write import (
    ALLOWED_SUFFIXES,
    MAX_FILE_BYTES,
    UploadRejected,
    upload_files,
)

_API = "https://api.github.com"

# Tetos. O total é o que impede um monorepo de cliente de derrubar o processo.
MAX_TREE_ENTRIES = 5_000
MAX_TOTAL_BYTES = 60 * 1024 * 1024
MAX_FILES_INGESTED = 400

_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")

# Caminhos que nunca ajudam numa base de conhecimento e só gastam índice.
_SKIP_DIRS = re.compile(
    r"(^|/)(\.git|node_modules|\.venv|venv|__pycache__|dist|build|\.next|target|vendor)(/|$)"
)


class GitHubError(RuntimeError):
    """Falha ao falar com o GitHub, já legível."""


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get(url: str, token: str) -> dict:
    import httpx

    try:
        r = httpx.get(url, headers=_headers(token), timeout=30.0, follow_redirects=True)
    except Exception as exc:
        raise GitHubError(f"Não foi possível falar com o GitHub: {type(exc).__name__}") from exc

    if r.status_code == 401:
        raise GitHubError("O GitHub recusou o token (401). Verifique o token e o escopo.")
    if r.status_code == 403:
        # Distinguir limite de taxa de falta de permissão muda o que a pessoa faz a seguir.
        remaining = r.headers.get("x-ratelimit-remaining")
        if remaining == "0":
            raise GitHubError("Limite de chamadas do GitHub atingido. Tente mais tarde.")
        raise GitHubError("Sem permissão para este repositório (403).")
    if r.status_code == 404:
        raise GitHubError("Repositório ou branch não encontrado (404).")
    if r.status_code >= 400:
        # A mensagem do GitHub, sem o corpo inteiro (que pode ser grande e conter caminhos).
        raise GitHubError(f"GitHub respondeu {r.status_code}.")
    return r.json()


def _wanted(path: str, size: int) -> bool:
    if _SKIP_DIRS.search(path):
        return False
    if os.path.splitext(path)[1].lower() not in ALLOWED_SUFFIXES:
        return False
    return 0 < size <= MAX_FILE_BYTES


def ingest_repo(
    kb_name: str,
    repo: str,
    token: str,
    *,
    ref: str = "",
    subdir: str = "",
) -> dict:
    """Lê os arquivos de texto de um repositório e sobe para o container da base.

    Devolve o que subiu E o que ficou de fora, com o motivo. A segunda metade é o ponto: uma
    base que indexou 40 de 400 arquivos e não diz isso é uma base que responde com confiança
    sobre um corpus que ela não tem.
    """
    if not _REPO_RE.match(repo or ""):
        raise GitHubError("Informe o repositório como 'organizacao/nome'.")
    if not token:
        raise GitHubError("O token do GitHub é obrigatório para ler o repositório.")

    branch = ref or _get(f"{_API}/repos/{repo}", token).get("default_branch") or "main"
    tree = _get(f"{_API}/repos/{repo}/git/trees/{branch}?recursive=1", token)

    entries = [e for e in (tree.get("tree") or []) if e.get("type") == "blob"]
    truncated_by_github = bool(tree.get("truncated"))

    if subdir:
        prefix = subdir.strip("/") + "/"
        entries = [e for e in entries if str(e.get("path", "")).startswith(prefix)]

    skipped: list[dict] = []
    chosen: list[dict] = []
    for e in entries[:MAX_TREE_ENTRIES]:
        path, size = str(e.get("path", "")), int(e.get("size") or 0)
        if _wanted(path, size):
            chosen.append({"path": path, "sha": e.get("sha"), "size": size})
        elif not _SKIP_DIRS.search(path):
            # Diretório ignorado por design não é "pulado" — não interessa a ninguém. O que
            # interessa é o arquivo que a pessoa esperava ver e não veio.
            reason = (
                "extensão não suportada"
                if os.path.splitext(path)[1].lower() not in ALLOWED_SUFFIXES
                else "arquivo muito grande"
            )
            skipped.append({"path": path, "reason": reason})

    files: list[tuple[str, bytes]] = []
    total = 0
    for item in chosen:
        if len(files) >= MAX_FILES_INGESTED or total >= MAX_TOTAL_BYTES:
            skipped.append({"path": item["path"], "reason": "teto de importação atingido"})
            continue
        blob = _get(f"{_API}/repos/{repo}/git/blobs/{item['sha']}", token)
        if blob.get("encoding") != "base64":
            skipped.append({"path": item["path"], "reason": "codificação inesperada"})
            continue
        try:
            data = base64.b64decode(blob.get("content") or "")
        except Exception:  # noqa: BLE001
            skipped.append({"path": item["path"], "reason": "conteúdo ilegível"})
            continue
        total += len(data)
        # O caminho vira nome achatado: o container é plano, e `docs/a/b.md` e `docs/c/b.md`
        # colidiriam se só o basename subisse. `__` preserva a origem na citação.
        files.append((item["path"].replace("/", "__"), data))

    if not files:
        raise GitHubError(
            "Nenhum arquivo indexável encontrado. Verifique o branch, o subdiretório e as "
            f"extensões aceitas ({', '.join(sorted(ALLOWED_SUFFIXES))})."
        )

    try:
        uploaded = upload_files(kb_name, files)
    except UploadRejected as exc:
        raise GitHubError(str(exc)) from exc

    return {
        "repo": repo,
        "branch": branch,
        "ingested": len(files),
        "total_bytes": total,
        "container": uploaded["container"],
        # Lista limitada na resposta, contagem sempre completa: 300 caminhos pulados tornariam a
        # resposta ilegível, mas esconder QUANTOS foram seria a mentira que importa.
        "skipped_count": len(skipped),
        "skipped_sample": skipped[:25],
        # O GitHub trunca árvore muito grande por conta própria. Se isso aconteceu, a lista de
        # arquivos já estava incompleta ANTES dos nossos tetos — e quem lê precisa saber.
        "tree_truncated_by_github": truncated_by_github,
    }
