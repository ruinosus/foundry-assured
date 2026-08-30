"""A fonte carrega o próprio acesso: o frontmatter sai do corpo E o `groups` chega ao carimbo.

POR QUE ISTO EXISTE (ADR-031). Antes, uma fonte que NÃO é código não tinha onde declarar quem
pode lê-la: bundles de código carregam `groups` no `manifest.json`, e todo o resto caía no
`ACL_CLASSIFICATION` — um mapa externo, gitignored, casado por convenção de chave. O padrão de
mercado é o oposto (Graph connectors, Kendra: a ACL é propriedade do ITEM), e é isso que
`preparar_corpus` passa a fazer.

As duas metades são um par, e cada uma sozinha é um defeito:

  • tirar o frontmatter e JOGAR FORA  → o acesso declarado some sem erro;
  • recolher o `groups` e MANTER o YAML no corpo → o YAML vira corpus de retrieval, e o modelo
    cita `groups:` como se fosse conteúdo.

Este módulo é offline e puro: exercita `preparar_corpus`, que não toca em rede.

    uv run python -m tests.knowledge.corpus_access_declarado_test
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from app.modules.knowledge.internal.acl_setup import _component
from app.modules.knowledge.internal.ingest import CORPUS_DIR, preparar_corpus

_ok: list[str] = []
_falhas: list[str] = []


def checar(nome: str, condicao: bool, detalhe: str = "") -> None:
    (_ok if condicao else _falhas).append(f"{nome}{f' — {detalhe}' if detalhe else ''}")
    print(f"   {'·' if condicao else '❌'} {nome}{f'  ({detalhe})' if detalhe and not condicao else ''}")


def _escrever(pasta: Path, nome: str, texto: str) -> Path:
    caminho = pasta / nome
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        pasta = Path(td)
        arquivos = [
            _escrever(pasta, "com-acesso.md", "---\ntype: runbook\ngroups: [sre, oncall]\n---\n\n# T\ncorpo A\n"),
            _escrever(pasta, "sem-frontmatter.md", "# T\ncorpo B\n"),
            _escrever(pasta, "sem-groups.md", "---\ntype: runbook\n---\n\n# T\ncorpo C\n"),
            _escrever(pasta, "grupo-vazio.md", "---\ngroups: []\n---\n\n# T\ncorpo D\n"),
        ]
        blobs, acesso = preparar_corpus(arquivos)
        corpo = {nome: dados.decode("utf-8") for nome, dados in blobs}

        print("1. o frontmatter SAI do corpo (senão vira YAML no corpus de retrieval)")
        for nome, texto in corpo.items():
            checar(f"{nome} não começa com '---'", not texto.lstrip().startswith("---"), repr(texto[:24]))
        checar("nenhum corpo contém 'groups:'", not any("groups:" in t for t in corpo.values()))
        checar("o conteúdo real sobrevive", all(f"corpo {L}" in corpo[n] for n, L in
               [("com-acesso.md", "A"), ("sem-frontmatter.md", "B"), ("sem-groups.md", "C"), ("grupo-vazio.md", "D")]))

        print("\n2. o `groups` declarado CHEGA ao mapa de carimbo")
        checar("quem declara aparece", acesso.get(_component("com-acesso.md")) == ["sre", "oncall"],
               f"veio {acesso.get(_component('com-acesso.md'))!r}")
        checar("`groups: []` é declaração de 'ninguém lê' (≠ ausência)",
               acesso.get(_component("grupo-vazio.md")) == [])
        print("\n3. quem NÃO declara fica FORA do mapa (None ≠ [], o consumidor decide)")
        for nome in ("sem-frontmatter.md", "sem-groups.md"):
            checar(f"{nome} ausente do mapa", _component(nome) not in acesso)

        print("\n4. frontmatter quebrado FALHA ALTO (pode ser acesso torto lido como ausência)")
        quebrado = [_escrever(pasta, "torto.md", "---\ngroups: [sre\n---\n\n# T\ncorpo\n")]
        try:
            preparar_corpus(quebrado)
            checar("levanta em YAML inválido", False, "passou sem erro — um typo viraria permissão")
        except SystemExit as exc:
            checar("levanta em YAML inválido", "torto.md" in str(exc), f"mensagem: {str(exc)[:60]}")

        print("\n5. colisão de chave é ERRO (`_canonical` corta versão: `x-2fa-y` → `x`)")
        colidem = [
            _escrever(pasta, "colide-1a.md", "---\ngroups: [a]\n---\n\ncorpo\n"),
            _escrever(pasta, "colide-2b.md", "---\ngroups: [b]\n---\n\ncorpo\n"),
        ]
        mesma_chave = _component("colide-1a.md") == _component("colide-2b.md")
        checar("os dois nomes colapsam na mesma chave (premissa do caso)", mesma_chave,
               f"{_component('colide-1a.md')!r} vs {_component('colide-2b.md')!r}")
        if mesma_chave:
            try:
                preparar_corpus(colidem)
                checar("levanta em colisão", False, "um acesso sobrescreveria o outro em silêncio")
            except SystemExit as exc:
                checar("levanta em colisão", "colisão" in str(exc))

    print("\n6. o corpus REAL de hoje segue sem declarar acesso (nada muda ao mergear)")
    reais = sorted(CORPUS_DIR.glob("*.md"))
    checar("corpus não-vazio (senão este check não prova nada)", len(reais) > 0, f"{len(reais)} arquivos")
    _, acesso_real = preparar_corpus(reais)
    checar("nenhum runbook declara acesso hoje", acesso_real == {}, f"declararam: {sorted(acesso_real)}")

    print("\n7. o corpus é um bundle OKF conformante (§11) — e o frontmatter continua fora do índice")
    # `type` é o ÚNICO campo que a spec do OKF exige de todo documento não-reservado. Sem ele,
    # `knowledge/corpus/` é markdown solto e não um bundle — e este produto declara OKF em
    # `openwiki/index.md`, então os dois lados precisam falar a mesma coisa.
    #
    # O segundo check é o que impede a conformidade de custar caro: o frontmatter que acabou de
    # ser acrescentado NÃO pode aparecer no corpo indexado. Se aparecer, o corpus de retrieval
    # ganha YAML e o modelo passa a citar `type:` como se fosse conteúdo — a mesma falha que o
    # passo 1 guarda para os arquivos sintéticos, aqui sobre os arquivos de verdade.
    from app.modules.knowledge.internal import frontmatter as fm

    sem_tipo: list[str] = []
    for arq in reais:
        try:
            meta, _ = fm.parse(arq.read_text(encoding="utf-8"))
        except fm.FrontmatterInvalido:
            sem_tipo.append(f"{arq.name} (frontmatter inválido)")
            continue
        if not str((meta or {}).get("type", "")).strip():
            sem_tipo.append(arq.name)
    checar("todo documento declara `type` (o único campo obrigatório do OKF)", not sem_tipo,
           f"sem type: {sem_tipo}")

    blobs_reais, _ = preparar_corpus(reais)
    vazou = [n for n, d in blobs_reais if d.decode("utf-8").lstrip().startswith("---")]
    checar("nenhum frontmatter vaza para o corpo indexado", not vazou, f"vazaram: {vazou}")

    print(f"\n{len(_ok)} ok, {len(_falhas)} falha(s)")
    if _falhas:
        for f in _falhas:
            print(f"   - {f}")
        return 1
    print("✅ a fonte carrega o próprio acesso, e o corpo chega limpo ao índice.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
