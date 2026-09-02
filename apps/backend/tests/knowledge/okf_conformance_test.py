"""Os bundles deste repositório são OKF v0.2 conformantes — pelo verificador da própria spec.

POR QUE UM VERIFICADOR DE TERCEIRO, e não o nosso. A conformidade §11 é **da especificação**, não
nossa. O Google publicou o formato e não publicou validador; `vendor/okf_validate.py` implementa
as regras verbatim, incluindo a que mais se erra — *cross-link quebrado NÃO é erro*, porque o
§6.1 obriga o consumidor a tolerá-lo. Um validador escrito aqui teria essa regra errada no
primeiro dia, e do jeito mais caro: recusando bundle de terceiro que o padrão manda aceitar.

Ver `vendor/README.md` para por que ele é COPIADO e não instalado.

A FRONTEIRA, e ela é o motivo de este arquivo existir separado dos outros gates:

    conformidade OKF   este gate          `type` presente, frontmatter parseável, reservados
    política nossa     eval/ e tests/     piso de citação, ACL por fonte, o `spec` do formflow

Chamar o segundo de "validação OKF" seria dizer que seguimos o padrão enquanto recusamos bundles
que o padrão manda aceitar.

AVISO NÃO É ERRO, e o gate respeita isso. `--strict` transformaria `tags` ausente em falha, e a
spec é explícita: campo recomendado ausente é guidance. O que trava é o §11 — e só ele.

    uv run python -m tests.knowledge.okf_conformance_test
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import app as _app

BACKEND = Path(_app.__file__).resolve().parent.parent
REPO = BACKEND.parents[1]
VALIDADOR = BACKEND / "vendor" / "okf_validate.py"

#: Os bundles OKF deste repositório. Explícito e não descoberto por glob: um diretório de
#: markdown que NÃO é bundle (docs/, que é para humanos) não deve ser cobrado como se fosse.
BUNDLES = {
    # A wiki gerada pelo OpenWiki. Ela declara `okf_version` desde sempre — este gate é o que
    # impede a conformidade de se perder numa regeneração.
    "openwiki": REPO / "openwiki",
    # O corpus do helpdesk. Ganhou frontmatter em 2026-08-30; antes disso era markdown solto.
    "knowledge/corpus": REPO / "knowledge" / "corpus",
    # Os manifestos de formulário — `type: formflow`.
    "agents/assured/flows": BACKEND / "agents" / "assured" / "flows",
    # Os copilotos e a política herdada — `type: copilot` e `type: policy`.
    "agents/assured/copilots": BACKEND / "agents" / "assured" / "copilots",
}

#: Diretórios com cara de bundle que este gate NÃO mede, e por quê. Existe porque a saída
#: dizia "os 4 bundles são conformantes" sem dizer que o bundle que o `selfwiki` consulta não
#: era um dos quatro — um verde que afirma mais do que mediu, que é exatamente a falha que o
#: `docs/CASE-STUDY-LLM-WIKI-LOOP.md` documenta.
#:
#: Entrar aqui é uma decisão, não um esquecimento: a lista é impressa em toda execução.
EXCLUDED_BUNDLES = {
    "knowledge/wiki-bundle": (
        "o frontmatter é retirado na adaptação (adapt_openwiki.py:191-194) — É O ARTEFATO "
        "QUE O DOMÍNIO selfwiki CONSULTA; entra no gate na Fase 4 do plano de adoção OKF"
    ),
    "agents/assured/guardrails": (
        "dado de aplicação, deliberadamente não é conceito AgentSchema "
        "(guardrails/response-language.md:2)"
    ),
    "agents/assured/personas": "idem — persona compartilhada, não conceito",
}


def main() -> int:
    falhas: list[str] = []

    if not VALIDADOR.is_file():
        print(f"❌ verificador ausente: {VALIDADOR}")
        return 1

    for nome, caminho in BUNDLES.items():
        if not caminho.is_dir():
            print(f"  ✗ {nome}: diretório não existe ({caminho})")
            falhas.append(nome)
            continue

        # `uv run --with pyyaml` roda o script no ambiente que ele declara (PEP 723) sem
        # acrescentar nada ao nosso: o verificador é ferramenta, não dependência do produto.
        proc = subprocess.run(
            [
                "uv", "run", "--with", "pyyaml", "--no-project",
                "python", str(VALIDADOR), str(caminho), "--json",
            ],
            capture_output=True,
            text=True,
            cwd=REPO,
            # `check=False` de propósito: um bundle NÃO CONFORMANTE faz o verificador sair com 1,
            # e é justamente esse caso que este gate precisa LER e reportar por arquivo. Levantar
            # aqui trocaria a lista de erros por um stack trace.
            check=False,
        )
        try:
            rel = json.loads(proc.stdout)
        except json.JSONDecodeError:
            print(f"  ✗ {nome}: o verificador não devolveu JSON\n{proc.stderr[:400]}")
            falhas.append(nome)
            continue

        erros = rel.get("errors", [])
        avisos = rel.get("warnings", [])
        ok = bool(rel.get("conformant")) and not erros
        print(f"  {'✓' if ok else '✗'} {nome}: {len(erros)} erro(s) · {len(avisos)} aviso(s)")
        for e in erros[:10]:
            print(f"      ✗ {e}")
        if not ok:
            falhas.append(nome)

    if falhas:
        print(f"\n❌ bundle(s) não conformante(s): {', '.join(falhas)}")
        print("   §11: todo .md não-reservado precisa de frontmatter YAML com `type` não-vazio.")
        return 1
    print("\n  não medidos (decisão, não esquecimento):")
    for nome, motivo in EXCLUDED_BUNDLES.items():
        print(f"    – {nome}: {motivo}")
    print(f"\n✅ os {len(BUNDLES)} bundles medidos são OKF v0.2 conformantes (§11): "
          f"{', '.join(BUNDLES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
