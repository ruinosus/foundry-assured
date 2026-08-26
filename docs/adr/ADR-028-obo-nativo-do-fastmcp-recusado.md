# ADR-028 — O OBO nativo do FastMCP é recusado: ele exige o OAuth proxy, e o brokering já existe

- **Status:** Accepted
- **Date:** 2026-08-25
- **Context:** [ADR-005](./ADR-005-never-store-secrets.md) (nunca guardar segredo),
  [ADR-003](./ADR-003-multitenant-identity-obo.md) (identidade e OBO),
  [ADR-027](./ADR-027-mcp-app-separado-fastmcp-4.md) (o app do MCP sobre FastMCP 4),
  [`docs/superpowers/specs/2026-08-24-mcp-t3-t7-execucao.md`](../superpowers/specs/2026-08-24-mcp-t3-t7-execucao.md)

## Contexto

O FastMCP 4 oferece `EntraOBOToken(scopes: list[str]) -> str` como **dependência de parâmetro**:
uma tool declara o escopo que precisa e recebe o token trocado por On-Behalf-Of, sem escrever a
troca. A ergonomia é real, e a camada T4 da spec de execução previa adotá-la.

## A medição

Lida na fonte instalada (`fastmcp==4.0.0b3`), não inferida da documentação:

```python
def _find_azure_provider(auth: AuthProvider | None) -> AzureProvider | None:
    if isinstance(auth, AzureProvider):
        return auth
    if isinstance(auth, MultiAuth) and isinstance(auth.server, AzureProvider):
        return auth.server
    return None
```

Testado com o provider real do `apps/mcp` (`build_auth()`), que é um **`RemoteAuthProvider`**:
`_find_azure_provider` devolve `None`, e `EntraOBOToken` levanta *"requires an AzureProvider as
the auth provider"*.

Reproduzido de forma independente na revisão final da branch, com a mesma fonte.

## Decisão

**Não adotar.** O `apps/mcp` permanece com o `AzureJWTVerifier` + `RemoteAuthProvider`, e a troca
OBO continua pelo caminho que já existe (`tenancy` faz o brokering de credencial; `knowledge.
retrieve` monta o `OnBehalfOfCredential` e é ele que faz o trim de ACL acontecer sob a identidade
de quem perguntou).

## Por quê

**O que adotá-lo custaria.** Trocar o Resource Server pelo `AzureProvider`, que é o OAuth proxy:
ele exige `client_secret` e **emite tokens próprios**. Isso é uma segunda malha de identidade
convivendo com a do Entra que já vale para o produto inteiro — duas respostas para "quem é o
chamador", que é exatamente o que o desenho do T0 recusou por escolha, e não por acidente.

**O que se perde recusando: nada.** Não há lacuna a preencher. O brokering existe, funciona, e é
verificado por gate. Adotar o `EntraOBOToken` não acrescentaria capacidade — trocaria uma
implementação que funciona por outra que custa uma malha de identidade a mais.

**O princípio que decide.** A MÁXIMA MAIOR manda preferir a peça de primeira parte quando ela
cobre a capacidade. Aqui ela **não cobre**: cobre a mesma capacidade *sob um modelo de
autenticação diferente do nosso*. Preferir a peça oficial não é preferir a peça oficial **mais** a
arquitetura que ela pressupõe.

## Consequências

- Tools que precisem falar com Graph ou Azure em nome do usuário escrevem a troca pelo caminho
  existente, em vez de declarar a dependência de parâmetro. É mais verboso e é a única diferença.
- A superfície de segredo do `apps/mcp` não cresce por causa disto.

## Gatilho de reavaliação

**Se o `fastmcp` passar a aceitar `RemoteAuthProvider`** (ou expor a troca OBO sem exigir o proxy),
reavaliar — a conveniência é real e o custo desapareceria.

Verificação, com o mesmo teste que fundamentou esta ADR:

```python
from fastmcp.server.auth.providers.azure import _find_azure_provider
from mcp_app.auth import build_auth
_find_azure_provider(build_auth("https://…"))   # deixar de ser None
```
