"""Catálogos públicos de skills — Microsoft, Anthropic — importáveis para o Foundry.

POR QUE ISTO EXISTE. O formato **agentskills.io** virou o padrão de fato para skill de agente, e
os dois maiores catálogos públicos já estão nele. Medido: `microsoft/skills` tem **198** skills,
`anthropics/skills` tem **20**, ambos no layout `<diretório>/SKILL.md`. O nosso
`create_skill_from_files` publica exatamente esse formato. Absorver não é integração nova — é
ligar duas pontas que já falam a mesma língua.

(Oito dessas skills da Microsoft já estavam vendorizadas em `.github/skills/` pela ADR-012, para
gerar a wiki. Elas não servem como catálogo do produto porque o Dockerfile copia só `app` e
`agents`: `.github/` nunca chega ao container. O catálogo durável é o repositório remoto.)

O LIMITE QUE DESENHOU O RESTO: a API do GitHub **sem token permite 60 chamadas por hora**. Buscar
a descrição das 198 skills seria 198 chamadas — estouraria o limite na primeira abertura da tela.
Então:

    listar   →  1 chamada (árvore recursiva, que volta inteira; medido: `truncated: false`)
                nome e grupo saem do CAMINHO, sem ler arquivo nenhum
    ver      →  1 chamada, só quando a pessoa abre uma skill (o SKILL.md)
    importar →  os arquivos daquele diretório, só dela

Um token opcional levanta o limite para 5.000/h; sem ele, navegar o catálogo custa duas chamadas.

CONTEÚDO DE CATÁLOGO É DADO, NUNCA INSTRUÇÃO. Um SKILL.md é texto escrito por terceiros: ele é
exibido para uma pessoa decidir, e publicado como arquivo. Este módulo não o interpreta, não
executa nada que ele diga e não o injeta em prompt nenhum. A decisão de importar é humana — que é
a mesma propriedade que `assist.py` estabeleceu para a sugestão de campo.
"""

from __future__ import annotations

import re

from app.modules.foundry.internal.github_source import GitHubError, _get
from app.modules.foundry.internal.skills import MAX_INSTRUCTIONS_CHARS

#: Os catálogos que a tela oferece de saída. Ponteiro para repositório de terceiro — não é uma
#: cópia de recurso nosso, então não conflita com a SEGUNDA MÁXIMA; qualquer outro repositório no
#: mesmo formato funciona pelo campo livre.
KNOWN_CATALOGS = (
    {"id": "microsoft", "repo": "microsoft/skills", "label": "Microsoft"},
    {"id": "anthropic", "repo": "anthropics/skills", "label": "Anthropic"},
)

#: Teto do bundle de UMA skill. Skills são pequenas (instruções + referências); um diretório que
#: passa disso não é uma skill, é outra coisa, e subi-lo em silêncio encheria o Foundry.
MAX_BUNDLE_BYTES = 2 * 1024 * 1024
MAX_BUNDLE_FILES = 40

_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
_RAW = "https://raw.githubusercontent.com"

#: O que entra no bundle. `SKILL.md` é obrigatório; o resto é o material que a skill referencia.
_ALLOWED = {".md", ".txt", ".json", ".yaml", ".yml", ".py", ".sh", ".ts", ".js", ".csv", ".sql"}


def _valid_repo(repo: str) -> str:
    repo = (repo or "").strip().removeprefix("https://github.com/").strip("/")
    if not _REPO_RE.match(repo):
        raise ValueError("Informe o repositório como 'org/nome'.")
    return repo


def _tree(repo: str, ref: str, token: str) -> list[dict]:
    """A árvore recursiva do repositório. UMA chamada."""
    dados = _get(f"https://api.github.com/repos/{repo}/git/trees/{ref}?recursive=1", token)
    if dados.get("truncated"):
        # Dizer que faltou é obrigatório: uma lista truncada em silêncio faz a pessoa concluir
        # que a skill que ela procura não existe no catálogo.
        raise GitHubError(
            "A árvore do repositório veio truncada — este catálogo é grande demais para "
            "listar de uma vez."
        )
    return dados.get("tree", [])


def list_catalog(repo: str, ref: str = "main", token: str = "") -> list[dict]:
    """As skills do catálogo: `id`, `name`, `group`, `path`.

    Nome e grupo saem do CAMINHO — nenhum arquivo é lido aqui. `.github/plugins/azure-sdk-dotnet/
    skills/azure-ai-openai-dotnet/SKILL.md` vira grupo `azure-sdk-dotnet`, nome
    `azure-ai-openai-dotnet`. É o suficiente para a pessoa procurar; a descrição vem no preview.
    """
    repo = _valid_repo(repo)
    saida: list[dict] = []
    for entrada in _tree(repo, ref or "main", token):
        caminho = entrada.get("path", "")
        if not caminho.endswith("/SKILL.md"):
            continue
        partes = caminho.split("/")
        nome = partes[-2]

        # O grupo é o segmento ANTES do primeiro `skills/` — o plugin, na organização da
        # Microsoft. Contar posições a partir do fim não serve: 11 das 198 skills ficam mais
        # fundas (`plugins/azure-skills/skills/azure-kubernetes/<skill>/`) e caíam sem grupo.
        # Buscar o segmento pelo NOME sobrevive à profundidade. A Anthropic é plana
        # (`skills/<skill>/`), e ali o `skills` é o primeiro segmento — logo, sem grupo.
        grupo = ""
        if "skills" in partes:
            i = partes.index("skills")
            # `.github` e `plugins` são segmentos ESTRUTURAIS do repositório, não nomes de
            # grupo: `.github/skills/<skill>/` é a raiz do catálogo, e mostrá-la como um grupo
            # chamado ".github" seria vocabulário de repositório vazando para a tela.
            if i > 0 and partes[i - 1] not in (".github", "plugins"):
                grupo = partes[i - 1]

        # O que fica ENTRE o grupo e a skill. Existe para desambiguar: há mais de uma skill
        # chamada `deploy` em subárvores diferentes, e uma lista que mostrasse só o nome faria
        # duas linhas idênticas apontarem para coisas distintas.
        meio = "/".join(partes[i + 1 : -2]) if grupo else ""

        saida.append(
            {
                # O caminho é o identificador: é o único campo garantidamente único.
                "id": caminho[: -len("/SKILL.md")],
                "name": nome,
                "group": grupo,
                "subpath": meio,
                "path": caminho[: -len("/SKILL.md")],
                "repo": repo,
                # O tamanho vem da ÁRVORE, sem baixar nada. Serve para a tela avisar antes do
                # clique que uma skill não cabe no teto de instruções do serviço — medido: 2 das
                # 218 skills dos dois catálogos estouram.
                #
                # É BYTES, e o teto do serviço é em CARACTERES. Num arquivo com acentos os dois
                # divergem, então isto é um AVISO, não um veredito: a recusa exata acontece na
                # importação, onde o texto está em mãos.
                "bytes": int(entrada.get("size", 0) or 0),
            }
        )
    saida.sort(key=lambda s: (s["group"], s["subpath"], s["name"]))
    return saida


def _raw(repo: str, ref: str, caminho: str) -> str:
    """Conteúdo de um arquivo, por raw.githubusercontent.

    Pelo RAW e não pela API de conteúdo: volta texto direto (sem base64) e não consome a cota de
    60/h que faz a listagem existir do jeito que existe. Repositório privado não responde aqui —
    e o catálogo é público por definição.
    """
    import httpx

    url = f"{_RAW}/{repo}/{ref}/{caminho}"
    try:
        r = httpx.get(url, timeout=30.0, follow_redirects=True)
    except Exception as exc:
        raise GitHubError(f"Não foi possível ler o arquivo: {type(exc).__name__}") from exc
    if r.status_code == 404:
        raise GitHubError(f"Arquivo não encontrado no catálogo: {caminho}")
    if r.status_code >= 400:
        raise GitHubError(f"O GitHub respondeu {r.status_code} ao ler {caminho}.")
    return r.text


def _frontmatter(texto: str) -> dict:
    """Os campos do frontmatter YAML do SKILL.md, ou vazio se não houver.

    Lido como DADO. Se o frontmatter trouxer algo além de `name`/`description`/`license`, isso
    fica no arquivo publicado e não vira comportamento aqui.
    """
    if not texto.startswith("---"):
        return {}
    fim = texto.find("\n---", 3)
    if fim < 0:
        return {}
    import yaml

    try:
        dados = yaml.safe_load(texto[3:fim]) or {}
    except Exception:  # noqa: BLE001 — frontmatter quebrado não impede mostrar o corpo
        return {}
    return dados if isinstance(dados, dict) else {}


def preview_skill(repo: str, path: str, ref: str = "main") -> dict:
    """O SKILL.md de uma skill: metadados e corpo, para a pessoa decidir antes de importar."""
    repo = _valid_repo(repo)
    texto = _raw(repo, ref or "main", f"{path.strip('/')}/SKILL.md")
    meta = _frontmatter(texto)
    return {
        "name": str(meta.get("name") or path.rsplit("/", 1)[-1]),
        "description": str(meta.get("description") or ""),
        "license": str(meta.get("license") or ""),
        "author": str((meta.get("metadata") or {}).get("author") or "")
        if isinstance(meta.get("metadata"), dict)
        else "",
        "version": str((meta.get("metadata") or {}).get("version") or "")
        if isinstance(meta.get("metadata"), dict)
        else "",
        # O corpo inteiro, para ler antes de publicar. Sem corte: quem vai importar precisa poder
        # ver o que está importando, e um resumo nosso seria uma leitura a menos.
        "body": texto,
        "path": path,
        "repo": repo,
        # Aqui o texto ESTÁ em mãos, então o número é exato — e é o mesmo que o serviço mede.
        "chars": len(texto),
        "max_chars": MAX_INSTRUCTIONS_CHARS,
        "too_large": len(texto) > MAX_INSTRUCTIONS_CHARS,
    }


def import_skill(repo: str, path: str, ref: str = "main", token: str = "", name: str = "") -> dict:
    """Publica a skill do catálogo no Foundry, com todos os arquivos do diretório dela.

    O bundle é o diretório inteiro — SKILL.md mais o que ele referencia (scripts, exemplos,
    referências). Publicar só o SKILL.md deixaria uma skill que aponta para arquivos ausentes.
    """
    from app.modules.foundry.internal.skills import create_skill_from_files

    repo = _valid_repo(repo)
    ref = ref or "main"
    prefixo = path.strip("/") + "/"

    entradas = [
        e
        for e in _tree(repo, ref, token)
        if e.get("type") == "blob"
        and e.get("path", "").startswith(prefixo)
        and ("." + e["path"].rsplit(".", 1)[-1].lower()) in _ALLOWED
    ]
    if not entradas:
        raise ValueError(f"Nada encontrado em {path} — o caminho existe neste catálogo?")

    arquivos: list[tuple[str, bytes]] = []
    total = 0
    ignorados: list[str] = []
    for e in sorted(entradas, key=lambda x: x["path"]):
        if len(arquivos) >= MAX_BUNDLE_FILES or total + int(e.get("size", 0)) > MAX_BUNDLE_BYTES:
            ignorados.append(e["path"][len(prefixo):])
            continue
        conteudo = _raw(repo, ref, e["path"]).encode("utf-8")
        total += len(conteudo)
        arquivos.append((e["path"][len(prefixo):], conteudo))

    doc = _frontmatter(next((c.decode() for n, c in arquivos if n == "SKILL.md"), ""))
    publicada = create_skill_from_files(
        name or path.rsplit("/", 1)[-1],
        arquivos,
        description=str(doc.get("description") or "")[:512],
    )
    return {
        **publicada,
        "files": len(arquivos),
        "bytes": total,
        "source": f"{repo}/{path}",
        # O que ficou de fora vai na resposta. Truncar em silêncio faria a skill parecer completa
        # quando ela perdeu justamente o arquivo grande que ela referencia.
        "skipped": ignorados,
    }
