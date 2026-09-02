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
    # O bundle que o domínio `selfwiki` consulta. Ficou fora deste gate até 2026-09 porque a
    # adaptação retirava o frontmatter (auditoria, defeito 1) — o único artefato não medido,
    # e o único que usuários de fato leem. Uma versão por diretório; todas são cobradas.
    "knowledge/wiki-bundle": REPO / "knowledge" / "wiki-bundle",
}

#: Diretórios com cara de bundle que este gate NÃO mede, e por quê. Existe porque a saída
#: dizia "os 4 bundles são conformantes" sem dizer que o bundle que o `selfwiki` consulta não
#: era um dos quatro — um verde que afirma mais do que mediu, que é exatamente a falha que o
#: `docs/CASE-STUDY-LLM-WIKI-LOOP.md` documenta.
#:
#: Entrar aqui é uma decisão, não um esquecimento: a lista é impressa em toda execução.
EXCLUDED_BUNDLES = {
    "agents/assured/guardrails": (
        "dado de aplicação, deliberadamente não é conceito AgentSchema "
        "(guardrails/response-language.md:2)"
    ),
    "agents/assured/personas": "idem — persona compartilhada, não conceito",
}

#: Avisos que ESTE gate trata como erro. A spec manda o consumidor tentar consumir um bundle
#: de versão desconhecida (SPEC.md:778-780) — e por isso o verificador está certo em avisar.
#: Mas um bundle NOSSO declarando uma versão que não validamos não é consumo best-effort, é
#: uma afirmação falsa; foi assim que `okf_version: "0.1"` sobreviveu a todo merge desde que
#: o gate existe. O verificador é de terceiro e não se edita (vendor/README.md).
#:
#: O match é no TEXTO do aviso de versão, não no nome do campo `okf_version`: o verificador
#: emite dois avisos cujo texto contém `okf_version` (vendor/okf_validate.py:330 e :332-333) —
#: um por frontmatter extra no `index.md` raiz (nada a ver com versão) e só o outro pela
#: própria versão. Promover pelo nome do campo promove os dois, e o primeiro vira uma falha
#: que lê como problema de versão sem ser. Por isso a string é o prefixo da frase inteira do
#: aviso de versão, não um substring genérico que reaparece em outro aviso.
AVISOS_FATAIS = ("§12 bundle declares",)


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
        promovidos = [a for a in avisos if any(t in a for t in AVISOS_FATAIS)]
        ok = bool(rel.get("conformant")) and not erros and not promovidos
        print(f"  {'✓' if ok else '✗'} {nome}: {len(erros)} erro(s) · "
              f"{len(avisos)} aviso(s) · {len(promovidos)} aviso(s) fatal(is)")
        for e in erros[:10]:
            print(f"      ✗ {e}")
        for a in promovidos:
            print(f"      ✗ (aviso promovido a erro) {a}")
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
