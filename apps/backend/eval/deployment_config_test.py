"""A configuração do ambiente ALVO sustenta o que o registry declara — ou o deploy nasce mudo.

Este gate existe porque o app subiu inteiro, respondeu 200 no health, serviu o helpdesk
normalmente, e mesmo assim três funcionalidades estavam quebradas — sem um único erro:

    /source/<doc>            403   citação que o próprio agente emitiu, impossível de abrir
    /conversations           200   com lista VAZIA
    /conversations/by-id/*   404   nenhuma conversa restaura

Causa única: `AZURE_STORAGE_ACCOUNT` nunca foi declarada em `infra/containerapps.bicep`, então
o container rodava com ela vazia. O código monta `https://{conta}.blob.core.windows.net/...`,
que vira uma URL inválida — e uma URL inválida não levanta exceção, só deixa de casar: o filtro
`blob_url eq` conta zero (fail-closed → 403) e o store de conversas aponta para lugar nenhum.

O valor existia em todas as fontes (GitHub Variables, azd env, output do bicep) e `main.bicep`
até o passava para o módulo — usado só pelo file share, nunca exposto ao app.

POR QUE NÃO COMPARAR `.env.example` COM O BICEP: das 55 variáveis documentadas, 39 não estão no
bicep e a maioria não precisa estar (têm default seguro). Um gate assim nasce com 39 falsos
positivos e é ignorado na primeira semana. O critério aqui é CONTRADIÇÃO: uma config vazia que
torna impossível o que o registry DECLARA. Isso não tem falso positivo — se um domínio declara
um container de corpus, a conta de storage é obrigatória, ponto.

Lê o ambiente ALVO (Container App), não o local: o defeito era a diferença entre os dois.

    AZURE_TARGET_APP=ca-backend-… AZURE_TARGET_RG=rg-… uv run python -m eval.deployment_config_test
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from app import registry


def env_do_alvo(app_name: str, rg: str) -> dict[str, str]:
    out = subprocess.run(
        ["az", "containerapp", "show", "-n", app_name, "-g", rg, "--query",
         "properties.template.containers[0].env[].{n:name,v:value,s:secretRef}", "-o", "json"],
        capture_output=True, text=True, timeout=120, check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:300])
    return {e["n"]: (e.get("v") or ("<secret>" if e.get("s") else "")) for e in json.loads(out.stdout or "[]")}


def contradicoes(env: dict[str, str]) -> list[str]:
    """Cada item: o registry declara algo que esta configuração torna impossível."""
    achados: list[str] = []
    specs = registry._domains()

    if any(getattr(d, "corpus_container", "") for d in specs) and not env.get("AZURE_STORAGE_ACCOUNT"):
        quais = ", ".join(d.id for d in specs if getattr(d, "corpus_container", ""))
        achados.append(
            f"AZURE_STORAGE_ACCOUNT vazia, mas [{quais}] declaram corpus_container — "
            f"a URL do blob nasce inválida: /source dá 403 e as conversas somem"
        )

    com_acl = [d.id for d in specs if getattr(d, "document_access", "acl") == "acl"]
    if com_acl and not (env.get("ENTRA_TENANT_ID") and env.get("ENTRA_API_CLIENT_ID")):
        achados.append(
            f"auth desligada (ENTRA_TENANT_ID/ENTRA_API_CLIENT_ID vazios), mas [{', '.join(com_acl)}] "
            f"declaram document_access='acl' — sem identidade o trim devolve ZERO para todos"
        )

    if not env.get("AZURE_SEARCH_ENDPOINT") and any(getattr(d, "search_index", "") for d in specs):
        achados.append("AZURE_SEARCH_ENDPOINT vazio, mas há domínio com search_index declarado")

    return achados


def sem_role_de_storage(app_name: str, rg: str, conta: str) -> str | None:
    """A identidade do app escreve conversas e trilha em blob — precisa de role no storage.

    Ter a variável não basta: por meses `AZURE_STORAGE_ACCOUNT` estava vazia E a identidade não
    tinha role nenhuma no storage, e os dois defeitos se escondiam um atrás do outro — a URL
    inválida fazia o SDK falhar ANTES de tentar autenticar, então a ausência de permissão nunca
    aparecia. Corrigida a variável, o primeiro `create_container` levou `AuthorizationFailure`
    e virou 502 em /conversations.
    """
    principal = subprocess.run(
        ["az", "containerapp", "show", "-n", app_name, "-g", rg,
         "--query", "identity.userAssignedIdentities.*.principalId | [0]", "-o", "tsv"],
        capture_output=True, text=True, timeout=120, check=False,
    ).stdout.strip()
    if not principal:
        return None  # sem identidade gerenciada declarada — fora do escopo deste gate

    escopo = subprocess.run(
        ["az", "storage", "account", "show", "-n", conta, "-g", rg, "--query", "id", "-o", "tsv"],
        capture_output=True, text=True, timeout=120, check=False,
    ).stdout.strip()
    if not escopo:
        return None

    roles = subprocess.run(
        ["az", "role", "assignment", "list", "--assignee", principal, "--scope", escopo,
         "--query", "[].roleDefinitionName", "-o", "tsv"],
        capture_output=True, text=True, timeout=180, check=False,
    ).stdout.split()
    if any("Storage Blob Data Contributor" in r or "Storage Blob Data Owner" in r for r in
           [" ".join(roles)] + roles):
        return None
    return (
        f"a identidade do app não tem 'Storage Blob Data Contributor' em '{conta}' — "
        f"o store de conversas e a trilha de auditoria escrevem em blob e vão dar 502"
    )


def main() -> int:
    app_name = os.environ.get("AZURE_TARGET_APP", "")
    rg = os.environ.get("AZURE_TARGET_RG", "")
    if not (app_name and rg):
        print("AZURE_TARGET_APP/AZURE_TARGET_RG ausentes — SKIP (gate é pós-deploy).")
        return 0
    try:
        env = env_do_alvo(app_name, rg)
    except Exception as exc:  # noqa: BLE001 — o gate reporta qualquer falha de leitura como vermelho
        print(f"❌ não consegui ler a config de '{app_name}': {exc}")
        return 1

    achados = contradicoes(env)
    conta = env.get("AZURE_STORAGE_ACCOUNT", "")
    if conta:
        problema = sem_role_de_storage(app_name, rg, conta)
        if problema:
            achados.append(problema)
    if achados:
        print(f"❌ a configuração de '{app_name}' contradiz o que o registry declara:\n")
        for a in achados:
            print(f"  ✗ {a}")
        print(
            "\n   Nenhuma dessas falha alto no boot: o app sobe, responde 200 no health e serve"
            "\n   os domínios que não dependem delas. Variável faltando declara-se em"
            "\n   infra/containerapps.bicep (não basta estar no azd env / GitHub Variables);"
            "\n   role faltando, em infra/resources.bicep, para a identidade do app."
        )
        return 1

    print(f"✅ a configuração de '{app_name}' sustenta os {len(registry._domains())} domínios do registry.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
