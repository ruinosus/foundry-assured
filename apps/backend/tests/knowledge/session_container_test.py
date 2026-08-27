"""Um container `document_access="session"` não pode receber conteúdo que declare acesso.

POR QUE ISTO EXISTE. `DomainSpec.document_access="session"` significa que a rota
`GET /source/{domain}/{name}` entrega o documento integral a QUALQUER sessão autenticada, pelo
nome, sem reautorizar contra o trim de ACL do índice (`catalog.py:61` e a docstring da classe).
O catálogo declara a condição que torna isso seguro (`catalog.py:140-150`):

    "Hoje isso não vaza nada porque o container só recebe os runbooks da ingestão."

A ADR-031 registra que essa condição deixa de valer quando a fonte passa a ser um PDF, um PPTX ou
o retorno de uma API que alguém aponta — e que, até lá, a garantia é OPERACIONAL, não verificada.
Este módulo é o que a torna verificável.

O QUE ELE PEGA. Um documento que declara acesso (`groups:`, `audience:`, …) dentro de um
container `session`. É uma contradição, e é a contradição PERIGOSA: quem escreveu acredita ter
restringido, e a restrição não é aplicada em lugar nenhum — nem erro, nem log, nem trim.

O QUE ELE NÃO PEGA, de propósito. Se o conteúdo É sensível. Isso exigiria lógica de classificação
no código, que a Regra #6 proíbe: acesso é DADO que vem da fonte. O gate cobra COERÊNCIA entre o
que a fonte declara e o que o domínio aplica; nunca julga o conteúdo.

O gate se desarma sozinho: tudo é derivado de `document_access`. No dia em que o `helpdesk` virar
`"acl"` (o que a ADR-031 discute), declarar `groups:` nos runbooks deixa de ser contradição e
este módulo para de reclamar, sem precisar ser editado.

    uv run python -m tests.knowledge.session_container_test
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.modules.domains.public import domain_specs
from app.modules.knowledge.internal.ingest import CORPUS_DIR
from app.modules.tenancy.public import tenant_config

# TRIPWIRE, e é o uso legítimo de uma lista à mão: ela não pode ficar verde por estar velha —
# entrada NOVA no catálogo dispara (check 2). Um container `session` novo obriga alguém a vir
# aqui, escrever o porquê, e confirmar que nada restrito entra nele.
_SESSION_CONTAINERS_CONHECIDOS = {
    "corpus": "helpdesk — runbooks de engenharia, audiência única por decisão (ADR-031)",
}

# Chaves de frontmatter que DECLARAM acesso. Não é classificação: é o vocabulário que um autor
# usaria para dizer "isto é restrito". Numa fonte `session`, a declaração é inócua.
_CHAVES_DE_ACESSO = ("groups", "acl", "audience", "access", "permissions", "classification")


def _fontes_do_repo() -> dict[Path, str]:
    """De onde este repositório sobe conteúdo, e para qual container.

    Derivado das MESMAS constantes que o uploader usa (`ingest.CORPUS_DIR` e
    `tenant_config().azure_storage_container`, ambas lidas em `ingest.upload_corpus`), nunca de um
    caminho recopiado — caminho copiado à mão é o que passa a apontar para o lugar errado em
    silêncio depois de uma mudança de pasta (Regra #9)."""
    return {CORPUS_DIR: tenant_config().azure_storage_container}


def _chaves_declaradas(texto: str) -> set[str]:
    """Chaves de topo do frontmatter YAML. Sem parser: só o bloco `---` … `---` inicial."""
    linhas = texto.splitlines()
    if not linhas or linhas[0].strip() != "---":
        return set()
    chaves: set[str] = set()
    for linha in linhas[1:]:
        if linha.strip() == "---":
            break
        if not linha.strip() or linha[:1].isspace() or linha.lstrip().startswith("#"):
            continue  # valor aninhado ou comentário — só chave de topo conta
        if ":" in linha:
            chaves.add(linha.split(":", 1)[0].strip().lower())
    return chaves


def main() -> int:
    falhas: list[str] = []
    especificacoes = list(domain_specs())

    por_container: dict[str, list[tuple[str, str]]] = {}
    for d in especificacoes:
        if d.corpus_container:
            por_container.setdefault(d.corpus_container, []).append((d.id, d.document_access))

    print(f"Domínios: {len(especificacoes)} | containers declarados: {len(por_container)}\n")

    # ── 1. Nenhum container serve `session` E `acl` ao mesmo tempo ───────────────────────────
    # Se servisse, o trim do domínio `acl` seria contornável: o mesmo blob sairia pelo nome, sem
    # ACL, pela rota do domínio `session`. A porta mais fraca decide.
    print("1. container compartilhado entre `session` e `acl`")
    for container, donos in sorted(por_container.items()):
        modos = {acesso for _, acesso in donos}
        if "session" in modos and "acl" in modos:
            falhas.append(
                f"container '{container}' serve {donos} — o trim do domínio `acl` é contornável "
                f"pela rota do domínio `session`"
            )
            print(f"   ❌ {container}: {donos}")
        else:
            print(f"   · {container}: {[i for i, _ in donos]} ({min(modos)})")

    # ── 2. Todo container `session` do catálogo está declarado aqui ──────────────────────────
    print("\n2. containers `session` conhecidos")
    session_no_catalogo = {
        c for c, donos in por_container.items() if any(a == "session" for _, a in donos)
    }
    for container in sorted(session_no_catalogo):
        print(f"   · {container}: {_SESSION_CONTAINERS_CONHECIDOS.get(container, '❌ NÃO DECLARADO')}")
    novos = session_no_catalogo - set(_SESSION_CONTAINERS_CONHECIDOS)
    if novos:
        falhas.append(
            f"container(s) `session` novo(s) e não declarado(s): {sorted(novos)} — acrescente em "
            f"_SESSION_CONTAINERS_CONHECIDOS com o motivo, confirmando que nada restrito entra"
        )
    obsoletos = set(_SESSION_CONTAINERS_CONHECIDOS) - session_no_catalogo
    if obsoletos:
        falhas.append(
            f"declarado(s) aqui mas não mais `session` no catálogo: {sorted(obsoletos)} — remova, "
            f"senão esta lista passa a mentir sobre o que cobre"
        )

    # ── 3. Fonte que este repo sobe para container `session` não declara acesso ──────────────
    print("\n3. declaração de acesso em fonte `session`")
    arquivos_lidos = 0
    containers_cobertos = 0
    for pasta, container in _fontes_do_repo().items():
        donos_session = [i for i, a in por_container.get(container, []) if a == "session"]
        if not donos_session:
            print(f"   · {pasta.name}/ → '{container}': nenhum domínio `session` — fora de escopo")
            continue
        containers_cobertos += 1
        if not pasta.is_dir():
            falhas.append(f"fonte '{pasta}' não existe — o gate não checou o que promete checar")
            continue
        arquivos = sorted(pasta.glob("*.md"))
        arquivos_lidos += len(arquivos)
        print(f"   · {pasta.name}/ → '{container}' ({donos_session}): {len(arquivos)} arquivos")
        for arquivo in arquivos:
            declaradas = _chaves_declaradas(arquivo.read_text(encoding="utf-8")) & set(_CHAVES_DE_ACESSO)
            if declaradas:
                falhas.append(
                    f"{arquivo.name} declara {sorted(declaradas)}, mas '{container}' serve "
                    f"{donos_session} com document_access='session' — a declaração NÃO é aplicada "
                    f"em lugar nenhum"
                )
                print(f"     ❌ {arquivo.name}: {sorted(declaradas)}")

    # ── Anti-tautologia: um gate que não leu nada não provou nada ────────────────────────────
    # É a falha que este projeto mais repetiu: a asserção passa porque o conjunto examinado está
    # vazio. Aqui aconteceria com uma glob errada ou um container renomeado.
    if containers_cobertos == 0:
        falhas.append("nenhum container `session` coberto pelo check 3 — o gate não provou nada")
    if arquivos_lidos == 0:
        falhas.append("nenhum arquivo lido pelo check 3 — o gate não provou nada")
    print(f"\n   cobertura: {containers_cobertos} container(s), {arquivos_lidos} arquivo(s)")

    if falhas:
        print(f"\n❌ {len(falhas)} falha(s):")
        for f in falhas:
            print(f"   - {f}")
        return 1
    print("\n✅ nenhum container `session` recebe conteúdo que declare acesso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
