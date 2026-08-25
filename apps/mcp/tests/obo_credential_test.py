"""O CONTAINER DO MCP RECEBE A CREDENCIAL QUE O OBO EXIGE — ou a busca nasce morta.

    uv run python -m tests.obo_credential_test

`search_docs`, o resource `document://` e a completion de nome chamam o MESMO
`knowledge.retrieve` do backend, e ele troca o token do chamador por um token de busca via
**OBO** — que é fluxo de cliente confidencial. Medido na fonte instalada do `azure-identity`
(1.26.0b2), sem credencial de cliente ele nem constrói:

    OnBehalfOfCredential(tenant_id=…, client_id=…, client_secret='', user_assertion=…)
    → TypeError: Either "client_certificate", "client_secret", or "client_assertion_func"
      must be provided

O `env` do `mcpApp` carregava `ENTRA_TENANT_ID` e `ENTRA_API_CLIENT_ID` e **não** o segredo. Com
auth ligada e `document_access='acl'` (o default), a tool principal estourava no primeiro uso —
e `mask_error_details=True` devolvia isso como erro interno genérico, sem dizer o que faltava.
Era regressão da separação do app: na `main` o `/mcp` morava no backend, que tem o segredo.

═══ POR QUE ESTE GATE, E NÃO SÓ O PÓS-DEPLOY ═══

`eval/deployment_config_test.py` também passou a cobrar isto, mas ele lê o Container App JÁ
CRIADO — precisa de Azure e roda depois do deploy. Este aqui é offline e roda em todo push: ele
compara o que o CÓDIGO lê com o que o BICEP declara, que é onde a contradição nasce.

E A LISTA DO QUE O CÓDIGO LÊ NÃO É ESCRITA AQUI — é derivada de `_user_search_token` por
`inspect.getsource`, filtrada pelos campos que existem em `settings`. Uma lista escrita à mão
seria a segunda cópia de sempre: divergiria no primeiro campo novo, e a divergência não daria
erro — só faria o gate afirmar que verificou algo que não verificou.
"""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import app as _app
from app.modules.knowledge.internal import retrieval
from app.shared.settings import settings

#: A raiz do repositório, ancorada no pacote `app` (regra 9): app → apps/backend → apps → raiz.
_REPO = Path(_app.__file__).resolve().parent.parent.parent.parent
_BICEP = _REPO / "infra" / "containerapps.bicep"

#: O recurso do bicep que este gate julga.
_RECURSO = "mcpApp"

#: O que liga a auth. Sem os dois, `settings.auth_enabled` é False e o caminho de OBO nem roda —
#: então a exigência do segredo é CONDICIONADA a eles, e não absoluta. Um deployment sem
#: sign-in continua sendo modo suportado.
_LIGA_AUTH = ("ENTRA_TENANT_ID", "ENTRA_API_CLIENT_ID")


def variaveis_de_obo() -> list[str]:
    """As env vars que o caminho de OBO lê — DERIVADAS do código, nunca escritas aqui.

    `settings.X` no corpo de `_user_search_token`, mantido só o que é campo de configuração
    (`auth_enabled` é propriedade derivada, não variável de ambiente).
    """
    lidos = set(re.findall(r"settings\.(\w+)", inspect.getsource(retrieval._user_search_token)))
    campos = type(settings).model_fields
    return sorted(n.upper() for n in lidos if n in campos)


def env_do_recurso(texto: str) -> set[str] | None:
    """Os nomes de env var declarados no container de `_RECURSO`, com valor ou `secretRef`."""
    inicio = texto.find(f"resource {_RECURSO} ")
    if inicio < 0:
        return None
    fim = texto.find("\nresource ", inicio + 1)
    bloco = texto[inicio : fim if fim > 0 else len(texto)]
    return set(re.findall(r"\{\s*name:\s*'([A-Z0-9_]+)'\s*,\s*(?:value|secretRef):", bloco))


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    # ── 1 · a metade "antes": a credencial não é opcional ──────────────────────────────────
    from azure.identity.aio import OnBehalfOfCredential

    erro = ""
    try:
        OnBehalfOfCredential(
            tenant_id="00000000-0000-0000-0000-000000000000",
            client_id="cliente",
            client_secret="",
            user_assertion="token-do-usuario",
        )
    except TypeError as exc:
        erro = str(exc)
    print(f"     sem segredo, o SDK diz: {erro or '(construiu — o SDK mudou!)'}")
    check(
        "sem credencial de cliente, `OnBehalfOfCredential` NÃO constrói (logo, o segredo não é "
        "opcional para o caminho de leitura)",
        "client_secret" in erro,
    )

    # ── 2 · o que o código lê ──────────────────────────────────────────────────────────────
    exigidas = variaveis_de_obo()
    print(f"     o caminho de OBO lê: {', '.join(exigidas)}")
    check("a derivação encontrou o segredo entre o que o OBO lê",
          "ENTRA_API_CLIENT_SECRET" in exigidas)

    # ── 3 · o que o bicep declara ──────────────────────────────────────────────────────────
    check("o bicep de container apps existe", _BICEP.is_file())
    if not _BICEP.is_file():
        print("\n❌ sem o bicep não há com o que comparar.")
        return 1

    declaradas = env_do_recurso(_BICEP.read_text(encoding="utf-8"))
    check(f"o recurso `{_RECURSO}` foi encontrado no bicep", declaradas is not None)
    if declaradas is None:
        return 1

    auth_ligada = all(v in declaradas for v in _LIGA_AUTH)
    print(f"     o `{_RECURSO}` declara auth ({'/'.join(_LIGA_AUTH)})? {auth_ligada}")
    if not auth_ligada:
        # Sem auth o OBO não roda, e cobrar o segredo aqui seria um falso positivo. O gate
        # continua valendo: se alguém LIGAR a auth sem o segredo, a condição passa a valer.
        print("\n✅ o container do MCP não declara auth — o caminho de OBO não roda ali.")
        return 0

    faltando = [v for v in exigidas if v not in declaradas]
    check(
        f"com auth ligada, o `{_RECURSO}` declara TODAS as variáveis do OBO "
        f"(faltando: {', '.join(faltando) or 'nenhuma'})",
        not faltando,
    )

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        print("   Com auth ligada e sem a credencial, `knowledge.retrieve` levanta ao construir")
        print("   a credencial: `search_docs`, `document://` e a completion morrem no primeiro")
        print("   uso — e `mask_error_details=True` esconde o motivo do chamador.")
        return 1
    print("\n✅ o container do MCP recebe tudo o que o caminho de OBO lê.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
