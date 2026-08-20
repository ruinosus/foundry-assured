"""A imutabilidade declarada em `infra/resources.bicep` (ADR-023) precisa ser SATISFAZÍVEL.

    uv run python -m tests.architecture.blob_immutability_test

POR QUE ESTE GATE EXISTE. `azd provision` falhou hoje com
`RequiredFeatureDisabled: Required feature Versioning is disabled` porque os containers `audit` e
`conversations` declaram `immutableStorageWithVersioning: { enabled: true }` enquanto o
`blobService` — recurso pai, conta inteira — nunca ligou `isVersioningEnabled`. A dependência
entre as duas propriedades não é óbvia lendo só o bloco do container (ela vive no recurso PAI,
duas seções acima no arquivo) e não foi pega por `bicep build`, porque sintaticamente as duas
declarações são válidas isoladamente — o Resource Manager só rejeita a COMBINAÇÃO, em tempo de
deploy real. Três coisas concordavam entre si (o bicep, a ADR-023, o texto "write-once") e nenhuma
delas era verdadeira, porque ninguém rodava `azd provision` desde que a declaração entrou. Este
gate é a prova offline de que a combinação nunca mais fica implícita.

O QUE É VERIFICADO, por parsing textual do `.bicep` (não há parser Bicep em Python; o texto é
disciplinado o bastante — um `resource <nome> '<tipo>@<versão>' = { ... }` por bloco — para extrair
por contagem de chaves em vez de regex ingênua sobre o arquivo inteiro):

  1. Se algum container declara `immutableStorageWithVersioning.enabled: true`, o `blobService`
     (o recurso pai, conta inteira) DEVE declarar `isVersioningEnabled: true`. Sem isto, o deploy
     falha exatamente como falhou hoje.
  2. Todo container que declara `immutableStorageWithVersioning.enabled: true` tem um recurso
     filho `.../containers/immutabilityPolicies` com `parent:` apontando para ele. Sem a política,
     a intenção de imutabilidade fica sem efeito nenhum — o container aceita e apaga blob
     normalmente.

O que NÃO é verificado (fora de alcance deste gate, exige credencial Azure): que o Resource
Manager de fato aceita o template, e que `isVersioningEnabled` continua `true` na conta real depois
de um `azd provision`. Isso só o próximo provision revela.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import app as _app

# `_app.__file__` é o ponto de ancoragem — não `__file__` deste arquivo — porque é o que
# `tests.architecture.filesystem_anchors_test` exige (ver o próprio gate, na mesma pasta).
REPO_ROOT = Path(_app.__file__).resolve().parents[3]
BICEP_FILE = REPO_ROOT / "infra" / "resources.bicep"

BLOB_SERVICE_TYPE = "Microsoft.Storage/storageAccounts/blobServices"
CONTAINER_TYPE = "Microsoft.Storage/storageAccounts/blobServices/containers"
IMMUTABILITY_POLICY_TYPE = "Microsoft.Storage/storageAccounts/blobServices/containers/immutabilityPolicies"

_RESOURCE_HEADER_RE = re.compile(
    r"^resource\s+(?P<name>\w+)\s+'(?P<type>[^']+)'\s*=\s*(?:if\s*\([^)]*\)\s*)?\{",
    re.MULTILINE,
)


def _strip_line_comments(text: str) -> str:
    """Remove comentário `//` até o fim da linha. O arquivo não usa `//` dentro de string."""
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


def _extract_resource_blocks(text: str) -> dict[str, tuple[str, str]]:
    """Nome do resource -> (tipo sem versão de API, corpo `{...}` completo), por contagem de chaves.

    Contagem de chaves em vez de regex de um bloco só porque o corpo de um `resource` pode conter
    `{` aninhado à vontade (ex.: `properties: { policy: { rules: [ { ... } ] } }`) — regex não
    aninha, contagem de profundidade sim.
    """
    blocks: dict[str, tuple[str, str]] = {}
    for match in _RESOURCE_HEADER_RE.finditer(text):
        name = match.group("name")
        rtype = match.group("type").split("@", 1)[0]
        open_brace = match.end() - 1
        depth = 0
        end = None
        for i in range(open_brace, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end is None:
            continue  # chave desbalanceada — `az bicep build` já pegaria isto antes deste gate
        blocks[name] = (rtype, text[open_brace : end + 1])
    return blocks


_VERSIONING_ENABLED_RE = re.compile(r"isVersioningEnabled\s*:\s*true\b")
_IMMUTABLE_VERSIONING_RE = re.compile(
    r"immutableStorageWithVersioning\s*:\s*\{[^{}]*\benabled\s*:\s*true\b"
)
_PARENT_RE = re.compile(r"\bparent\s*:\s*(\w+)")


def offenders() -> list[str]:
    """Mensagens de falha; lista vazia = imutabilidade declarada é satisfazível."""
    if not BICEP_FILE.exists():
        return [f"arquivo não encontrado: {BICEP_FILE}"]

    text = _strip_line_comments(BICEP_FILE.read_text())
    blocks = _extract_resource_blocks(text)

    blob_services = {n: b for n, (t, b) in blocks.items() if t == BLOB_SERVICE_TYPE}
    containers = {n: b for n, (t, b) in blocks.items() if t == CONTAINER_TYPE}
    immutability_policies = {n: b for n, (t, b) in blocks.items() if t == IMMUTABILITY_POLICY_TYPE}

    containers_with_versioned_immutability = {
        name for name, body in containers.items() if _IMMUTABLE_VERSIONING_RE.search(body)
    }

    problems: list[str] = []

    if containers_with_versioned_immutability:
        if not blob_services:
            problems.append(
                "nenhum resource 'Microsoft.Storage/storageAccounts/blobServices' encontrado, "
                f"mas {sorted(containers_with_versioned_immutability)} declaram "
                "immutableStorageWithVersioning"
            )
        else:
            versioning_on = any(
                _VERSIONING_ENABLED_RE.search(body) for body in blob_services.values()
            )
            if not versioning_on:
                problems.append(
                    "blobService não declara isVersioningEnabled:true, mas "
                    f"{sorted(containers_with_versioned_immutability)} declaram "
                    "immutableStorageWithVersioning:{enabled:true} — RequiredFeatureDisabled no "
                    "próximo `azd provision`"
                )

    policy_parents = set()
    for name, body in immutability_policies.items():
        m = _PARENT_RE.search(body)
        if m:
            policy_parents.add(m.group(1))
        else:
            problems.append(f"immutabilityPolicies '{name}' não declara `parent:`")

    for name in sorted(containers_with_versioned_immutability - policy_parents):
        problems.append(
            f"container '{name}' declara immutableStorageWithVersioning mas nenhum "
            "'.../immutabilityPolicies' tem `parent: " + name + "`"
        )

    return problems


def main() -> int:
    problems = offenders()
    for problem in problems:
        print(f"  ✗ {problem}")
    if problems:
        print(
            f"\n❌ {len(problems)} problema(s) na imutabilidade declarada em "
            f"{BICEP_FILE.relative_to(REPO_ROOT)}. A declaração de "
            "immutableStorageWithVersioning só tem efeito com isVersioningEnabled:true no "
            "blobService pai — sem isso o Resource Manager recusa o deploy inteiro."
        )
        return 1
    print(
        "✅ todo container com immutableStorageWithVersioning tem isVersioningEnabled:true no "
        "blobService e uma immutabilityPolicies apontando para ele."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
