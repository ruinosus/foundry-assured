"""O hint de cache (SEP-2549) — ligado SÓ para as listagens, e nunca para `resources/read`.

A Fase 5 recusou este item com a medição de que o botão do FastMCP é **uniforme**:
`build_cache_hints` faz `dict.fromkeys(get_args(CacheableMethod), hint)`, então `cache_ttl=60`
no construtor liga o TTL para os seis métodos cacheáveis de uma vez — `resources/read` entre
eles. Aqui `resources/read` é `document://{domain}/{name}`, o documento integral controlado por
ACL e registrado leitura a leitura na trilha da ADR-023, inclusive as NEGADAS. Um TTL ali
autoriza o cliente a servir a leitura do armazenamento dele: a leitura não chega mais aqui, não
vira evento, e o produto continua afirmando que registra toda leitura de documento controlado.

A RECUSA CAIU PORQUE A MEDIÇÃO ESTAVA INCOMPLETA — e o que faltava não é do FastMCP, é do SDK
debaixo dele. Medido na fonte instalada (regra 1), `mcp 2.1.0`:

    mcp/server/lowlevel/server.py:421   self.cache_hints: dict[str, CacheHint] = validate_cache_hints(...)
    mcp/server/runner.py:357            if (hint := self.server.cache_hints.get(method)) is not None:

O mapa é **por método**, e o runner o consulta por método. Quem é uniforme é só o ATALHO do
FastMCP (`cache_ttl`/`cache_scope` no construtor), que constrói o mapa cheio e o entrega ao
servidor de baixo nível. A capacidade de excluir um método existe no SDK; o construtor do
FastMCP apenas não a expõe.

Medido no fio, com um cliente de verdade, antes de escrever este módulo:

    cache_ttl=60 (o atalho)                tools/list=60000  resources/read=60000
    sem cache nenhum                       tools/list=0      resources/read=0
    mapa por método, sem `resources/read`  tools/list=60000  resources/read=0

A terceira linha é o objetivo: as listagens ganham TTL e `resources/read` fica **idêntico ao de
um servidor que nunca ligou cache** — `ttlMs=0` é o valor que ele já tinha, não um valor novo.

═══ POR QUE MEXER NUM ATRIBUTO QUE COMEÇA COM `_` ═══

`FastMCP` não expõe o servidor de baixo nível por propriedade pública, então o caminho é
`mcp._mcp_server`. O ATRIBUTO ALVO, porém, é público e documentado como mapa por método
(`Server.cache_hints`), e é exatamente o que o próprio FastMCP preenche quando o atalho é usado
— não estamos contornando uma decisão da biblioteca, estamos usando a capacidade que ela
repassa. O risco real de acoplar a um `_` é o seam sumir numa versão nova; por isso o gate
(`tests/cache_hints_test.py`) NÃO confere este atributo: ele mede o `ttlMs` que sai no fio para
um cliente. Se o seam mudar de nome, o hint some do fio e o gate fica vermelho — que é o
desfecho certo, e não um teste verde sobre um atributo órfão.

═══ AS TRÊS DECISÕES, E O QUE CADA UMA CUSTARIA SE FOSSE A OUTRA ═══

1. **`resources/read` FORA.** É a decisão inteira. Ver o primeiro parágrafo.

2. **Escopo `private`, nunca `public`.** As listagens deste servidor são FILTRADAS por chamador:
   `tools/list` some a tool cujo `auth=` o papel do chamador não satisfaz (`server.py:879`), e no
   modo `shared` o catálogo depende do tenant da requisição. `public` significa "pode ser
   compartilhado entre contextos de autorização" — seria autorizar um proxy a servir a listagem
   filtrada de um chamador a outro. A biblioteca aceita `public` sem erro e sem aviso (só recusa
   escopo SEM ttl), então o freio é este módulo mais o gate.

3. **TTL de 60s, e por que uma listagem obsoleta não é uma autorização.** O pior caso do TTL é
   uma pessoa cujo papel foi revogado continuar VENDO `search_docs` na lista por até um minuto.
   Ela não consegue CHAMAR: `tools/call` não é método cacheável nesta versão do protocolo (os
   seis estão em `CACHEABLE_METHODS`), então toda chamada chega aqui e roda o `auth=` de novo,
   mais o gate de tenant e o trim de ACL por documento. O cache alcança a VITRINE, nunca a
   porta. É por isso que 60s é aceitável aqui e não seria em `resources/read`, onde a resposta
   cacheada É o conteúdo controlado.
"""

from __future__ import annotations

from fastmcp import FastMCP
from mcp.server.caching import CacheHint
from mcp_types.methods import CACHEABLE_METHODS

#: O método que NUNCA recebe hint. Um conjunto (e não um `if != `) porque a pergunta que o gate
#: faz é "quais métodos cacheáveis estão de fora?", e a resposta precisa ser um dado, não uma
#: condição escondida numa comprehension.
#:
#: `resources/read` é a única superfície deste servidor cuja resposta É conteúdo controlado por
#: ACL e cuja chegada aqui é o que produz o evento da trilha (ADR-023). Todo o resto que é
#: cacheável é catálogo.
SEM_HINT = frozenset({"resources/read"})

#: Segundos. Ver a decisão 3 no docstring: o teto do dano é uma listagem obsoleta, porque a
#: chamada não é cacheável e revalida tudo.
TTL_SEGUNDOS = 60

#: Nunca `"public"`. Ver a decisão 2 no docstring.
ESCOPO = "private"


def hints() -> dict[str, CacheHint]:
    """O mapa por método que vai para o servidor de baixo nível.

    DERIVADO de `CACHEABLE_METHODS` menos `SEM_HINT`, nunca escrito à mão. Se uma versão nova do
    SDK acrescentar um método cacheável, ele entra aqui sozinho — e se acrescentar um que não
    devesse entrar, o gate (que compara a cobertura com a lista do pacote) é quem obriga a
    decidir. Uma lista literal divergiria no primeiro método novo, em silêncio.
    """
    hint = CacheHint(ttl_ms=TTL_SEGUNDOS * 1000, scope=ESCOPO)
    return {metodo: hint for metodo in sorted(CACHEABLE_METHODS) if metodo not in SEM_HINT}


def aplicar(mcp: FastMCP) -> None:
    """Instala o mapa por método no servidor de baixo nível que o `FastMCP` construiu.

    Chamado por `build_mcp`, e não passado ao construtor, porque o construtor só aceita o atalho
    uniforme — que é justamente o que não serve. Ver a seção sobre o `_` no docstring do módulo.
    """
    mcp._mcp_server.cache_hints = hints()
