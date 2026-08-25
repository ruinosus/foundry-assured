"""A tabela de evidências: o que a sessão guarda, quem consegue ver, e de onde vem o renderizador.

Este gate cobre as DUAS metades da mesma feature da Fase 5 — o estado por usuário
(`mcp_app/sessions.py`) e o MCP App que o consome (`mcp_app/app_evidencias.py`) —, porque
separá-las produziria dois gates que passam sozinhos e nenhum que prove a coisa que importa: as
citações que UM chamador recebeu chegam à tabela DELE, e não à de outro.

AS SEIS PROPRIEDADES, e por que nenhuma é decorativa:

1. **A evidência atravessa duas chamadas.** `search_docs` deposita, `show_evidence` mostra. É o
   caso de uso inteiro; sem isto a sessão é infraestrutura para nada.
2. **E não atravessa entre PESSOAS.** Dois chamadores autenticados, mesma pilha, tokens que
   diferem no `sub`: o segundo vê "nenhuma busca nesta sessão". A sessão é keyed pelo principal
   (`session:{sha256(principal)}:_user`), e esta é a checagem que prova que a chave é o que se
   pensa que é.
3. **Sem papel, a tabela não existe.** Nem a tool na listagem, nem a leitura do renderizador. É
   a mesma regra das outras superfícies, medida na mesma pilha.
4. **Nenhum recurso sem gate nasceu.** O caminho padrão de MCP Apps sintetizaria um renderizador
   `auth=None` — aqui `synthesize_prefab_resources` sobre o servidor REAL tem que vir vazio. A
   matriz cobre isso de outro ângulo (com prova por mutação); aqui é a asserção do próprio item.
5. **O renderizador não vem de CDN.** `mode="bundled"` serve o artefato de dentro do wheel, com
   `resource_domains: []`. O modo `cdn` é medido ao lado, para o custo da escolha ficar visível
   em vez de virar folclore.
6. **O TTL não é decorativo.** `Session._save_raw` grava SEM ttl — a fonte diz que a retenção é
   toda da loja. A prova por mutação põe a loja crua e a embrulhada lado a lado: uma devolve
   `None` (para sempre), a outra devolve o prazo.

Offline como os vizinhos: `httpx2.ASGITransport` (pilha HTTP em processo, sem socket),
`StaticTokenVerifier` no lugar do `AzureJWTVerifier` (que buscaria o JWKS do Entra), `retrieve`
substituído, e a loja de sessão em memória. Zero rede, zero daemon — a durabilidade entre
processos é assunto do gate `durability_test`, que tem Redis e por isso mora noutro job.

    uv run python -m tests.app_evidencias_test
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from html.parser import HTMLParser

import httpx2
from fastmcp import Client
from fastmcp.client.transports.http import StreamableHttpTransport
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

from app.shared import auth as shared_auth
from app.shared.settings import ENTRA_API_SCOPE_NAME, settings
from mcp_app import app_evidencias, tools_knowledge
from mcp_app import main as mcp_main
from mcp_app.auth import MCP_PATH

TENANT = "11111111-1111-1111-1111-111111111111"
CLIENT_ID = "22222222-2222-2222-2222-222222222222"
BASE = "http://testserver"

#: Três chamadores. Os dois primeiros diferem SÓ no `sub` — é o que faz deles principals
#: distintos (`principal_components` é a tripla cliente/emissor/subject), e é a diferença que a
#: propriedade 2 mede. O terceiro difere só no `roles`.
TOKENS = {
    "tok-ana": {
        "client_id": CLIENT_ID,
        "scopes": [ENTRA_API_SCOPE_NAME],
        "roles": ["Reader"],
        "sub": "sub-ana",
        "oid": "00000000-0000-0000-0000-0000000000aa",
        "preferred_username": "ana@exemplo.invalid",
    },
    "tok-bruno": {
        "client_id": CLIENT_ID,
        "scopes": [ENTRA_API_SCOPE_NAME],
        "roles": ["Reader"],
        "sub": "sub-bruno",
        "oid": "00000000-0000-0000-0000-0000000000bb",
        "preferred_username": "bruno@exemplo.invalid",
    },
    "tok-nenhum": {
        "client_id": CLIENT_ID,
        "scopes": [ENTRA_API_SCOPE_NAME],
        "roles": [],
        "sub": "sub-sem-papel",
        "oid": "00000000-0000-0000-0000-0000000000cc",
        "preferred_username": "sem.papel@exemplo.invalid",
    },
}

#: O que o `retrieve` substituído devolve. Nomes reconhecíveis, para a asserção poder procurá-los
#: dentro da árvore de componentes que o renderizador recebe.
LINHAS_DA_BUSCA = [
    {"index": 1, "source": "runbook-vpn.md", "url": "https://c.blob/x/runbook-vpn.md", "snippet": "a"},
    {"index": 2, "source": "runbook-vpn-2.md", "url": "https://c.blob/x/runbook-vpn-2.md", "snippet": "b"},
]


class _Spec:
    def __init__(self, domain_id: str, kind: str) -> None:
        self.id = domain_id
        self.kind = kind


def _auth_estatico(_base_url: str):
    return RemoteAuthProvider(
        token_verifier=StaticTokenVerifier(TOKENS),
        authorization_servers=[f"https://login.microsoftonline.com/{TENANT}/v2.0"],
        base_url=BASE,
        resource_name="Foundry Assured MCP",
    )


def _cliente(app, token: str) -> Client:
    def fabrica(**kwargs):
        kwargs.pop("verify", None)
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=BASE, **kwargs
        )

    return Client(
        StreamableHttpTransport(url=BASE + MCP_PATH, auth=token, httpx_client_factory=fabrica)
    )


def _texto_da_tabela(resultado) -> str:
    """A árvore de componentes que `show_evidence` devolveu, achatada em texto.

    A forma exata da serialização do prefab é DELE, e não é contrato nosso — procurar um nome de
    documento no JSON inteiro é a asserção que continua valendo se a biblioteca reorganizar a
    árvore. O que está sob teste é "as fontes da MINHA busca chegaram", não o formato do prefab.
    """
    partes = [c.text for c in (resultado.content or []) if getattr(c, "text", None)]
    if resultado.structured_content is not None:
        partes.append(json.dumps(resultado.structured_content, ensure_ascii=False))
    return " ".join(partes)


async def _tabela(app, token: str) -> str:
    async with _cliente(app, token) as client:
        return _texto_da_tabela(await client.call_tool("show_evidence", {}))


async def _buscar(app, token: str) -> None:
    async with _cliente(app, token) as client:
        await client.call_tool("search_docs", {"domain": "techdocs", "query": "vpn"})


async def _visao(app, token: str) -> dict:
    async with _cliente(app, token) as client:
        visao = {"tools": sorted(t.name for t in await client.list_tools())}
        try:
            lido = await client.read_resource(app_evidencias.URI_RENDERIZADOR)
            visao["renderizador"] = len(lido[0].text or "")
        except Exception as exc:  # noqa: BLE001 — a recusa É o resultado sob teste
            visao["renderizador"] = f"RECUSADO {type(exc).__name__}"
        return visao


async def _ttl_lado_a_lado() -> tuple[object, object]:
    """A prova por mutação do TTL: a mesma escrita, na loja crua e na embrulhada.

    Sem isto, "a loja tem TTL" seria uma afirmação sobre um construtor. Aqui se mede o efeito no
    único jeito como o FastMCP escreve sessão: um `put` SEM ttl.
    """
    from key_value.aio.stores.memory import MemoryStore
    from key_value.aio.wrappers.ttl_clamp import TTLClampWrapper

    from mcp_app.sessions import TTL_SEGUNDOS

    crua = MemoryStore()
    await crua.put(key="k", value={"a": 1}, collection="c")
    _, ttl_cru = await crua.ttl(key="k", collection="c")

    embrulhada = TTLClampWrapper(
        key_value=MemoryStore(), min_ttl=60, max_ttl=TTL_SEGUNDOS, missing_ttl=TTL_SEGUNDOS
    )
    await embrulhada.put(key="k", value={"a": 1}, collection="c")
    _, ttl_embrulhado = await embrulhada.ttl(key="k", collection="c")
    return ttl_cru, ttl_embrulhado


# Um gate LINEAR de propósito: a ordem das checagens é o argumento. Quebrá-lo em funções
# esconderia que a tabela de Bruno só significa algo DEPOIS de Ana ter buscado.
def main() -> int:
    from fastmcp.server.providers.prefab_synthesis import synthesize_prefab_resources
    from prefab_ui.renderer import get_renderer_csp, get_renderer_html

    from mcp_app import sessions

    falhas: list[str] = []
    logging.disable(logging.CRITICAL)

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    original = (
        mcp_main.build_auth,
        tools_knowledge.retrieve,
        settings.entra_tenant_id,
        settings.entra_api_client_id,
        settings.mcp_public_base_url,
    )

    async def retrieve_falso(query, user, spec):
        return list(LINHAS_DA_BUSCA)

    try:
        settings.entra_tenant_id = TENANT
        settings.entra_api_client_id = CLIENT_ID
        settings.mcp_public_base_url = BASE
        mcp_main.build_auth = _auth_estatico

        app = mcp_main.build_app()
        tools_knowledge.set_domain_registry(lambda d: _Spec(d, "grounded"), ("techdocs",))
        tools_knowledge.retrieve = retrieve_falso

        async def roda():
            async with app.router.lifespan_context(app):
                # Ana busca; Bruno NÃO busca. É a assimetria que a propriedade 2 mede.
                await _buscar(app, "tok-ana")
                return {
                    "ana": await _tabela(app, "tok-ana"),
                    "bruno": await _tabela(app, "tok-bruno"),
                    "visao_com": await _visao(app, "tok-ana"),
                    "visao_sem": await _visao(app, "tok-nenhum"),
                }

        r = asyncio.run(roda())

        # --- 1 · a evidência atravessa duas chamadas -------------------------------------
        check(
            "a tabela de Ana traz as fontes da busca DELA "
            f"({'runbook-vpn.md' in r['ana']})",
            "runbook-vpn.md" in r["ana"] and "runbook-vpn-2.md" in r["ana"],
        )
        check(
            "e não é a tabela vazia (o texto de 'nenhuma busca' NÃO aparece)",
            sessions and app_evidencias.SEM_BUSCA not in r["ana"],
        )

        # --- 2 · e não atravessa entre pessoas -------------------------------------------
        check(
            "Bruno — outro principal, mesma pilha — vê a tabela VAZIA",
            app_evidencias.SEM_BUSCA in r["bruno"],
        )
        check(
            "e nenhum nome de documento da busca de Ana aparece na tabela de Bruno",
            "runbook-vpn" not in r["bruno"],
        )

        # --- 3 · sem papel, a tabela não existe -------------------------------------------
        print(f"     COM papel: {r['visao_com']['tools']} · renderizador={r['visao_com']['renderizador']}")
        print(f"     SEM papel: {r['visao_sem']['tools']} · renderizador={r['visao_sem']['renderizador']}")
        check(
            "com papel · `show_evidence` aparece na listagem",
            "show_evidence" in r["visao_com"]["tools"],
        )
        check(
            "com papel · o renderizador é legível pelo protocolo",
            isinstance(r["visao_com"]["renderizador"], int)
            and r["visao_com"]["renderizador"] > 0,
        )
        check(
            "sem papel · `show_evidence` NÃO aparece na listagem",
            "show_evidence" not in r["visao_sem"]["tools"],
        )
        check(
            "sem papel · a leitura do renderizador é RECUSADA — é a superfície que o caminho "
            "padrão teria deixado sem gate",
            str(r["visao_sem"]["renderizador"]).startswith("RECUSADO"),
        )

        # --- 4 · nenhum recurso sem gate nasceu -------------------------------------------
        sintetizados = asyncio.run(_sintetizados(app, synthesize_prefab_resources))
        check(
            f"o servidor real não sintetiza renderizador nenhum ({sintetizados or 'nenhum'}) — "
            "a URI própria é o que desliga a síntese sem `auth=`",
            sintetizados == [],
        )

        # --- 5 · o renderizador vem do pacote, não de CDN ---------------------------------
        embutido = get_renderer_html(mode="bundled")
        do_cdn = get_renderer_html(mode="cdn")
        check(
            f"embutido: {len(embutido) // 1024} KiB e NENHUMA tag que busque origem externa "
            f"({_tags_externas(embutido) or 'nenhuma'}); `resource_domains` "
            f"{get_renderer_csp('bundled')['resource_domains']}",
            _tags_externas(embutido) == []
            and get_renderer_csp("bundled")["resource_domains"] == [],
        )
        # A PROVA POR MUTAÇÃO DA PRÓPRIA ASSERÇÃO. A checagem acima só vale o que o detector
        # enxerga: enquanto ele olhava `<script src>`/`<link href>`, um `<img>` externo passava e
        # a linha continuava dizendo "NENHUMA tag que busque origem externa". As duas metades
        # medidas juntas: o `<img>` no documento é PEGO, e o mesmo texto dentro de `<script>` —
        # que é onde o bundle de fato tem `<iframe src="https://example.com"`, num docstring de
        # `.py` do payload do Pyodide — NÃO é, porque não é markup para o navegador.
        externo = '<img src="https://cdn.exemplo.invalid/x.png">'
        check(
            "e o detector PEGA um `<img>` externo, que a versão anterior deixava passar "
            f"({_tags_externas(embutido + externo)})",
            _tags_externas(embutido + externo) == ["img"],
        )
        check(
            "sem confundir markup com TEXTO dentro de `<script>` — é por isso que o bundle, que "
            "carrega um `<iframe src=…>` num docstring empacotado, não fica vermelho",
            _tags_externas(f"<html><script>const t = '{externo}';</script></html>") == [],
        )
        check(
            f"o modo `cdn` (recusado) carrega de fora no parse ({_tags_externas(do_cdn)}) e "
            f"aponta para {get_renderer_csp('cdn')['resource_domains']} em {len(do_cdn)} bytes",
            _tags_externas(do_cdn) == ["link", "script"]
            and get_renderer_csp("cdn")["resource_domains"] == ["https://cdn.jsdelivr.net"],
        )
        # A RESSALVA MEDIDA, e ela fica no gate para não virar folclore: o HTML embutido CONTÉM
        # uma URL do Pyodide em `cdn.jsdelivr.net`. Ela não é carregada no parse (a checagem
        # acima mede isso) — é o carregador do renderizador GENERATIVO, alcançado só quando o
        # servidor emite um componente generativo. Este servidor emite uma tabela estática e
        # nada mais. Fica contado, e não afirmado como zero: no dia em que alguém emitir um
        # componente generativo, esta linha é onde a conta muda.
        check(
            f"a única referência externa remanescente é o carregador do Pyodide "
            f"({embutido.count('cdn.jsdelivr.net/pyodide')}), alcançável só em modo generativo — "
            "que este servidor nunca emite",
            embutido.count("cdn.jsdelivr.net/pyodide") == 1,
        )
        check(
            f"e é o embutido que este servidor serve (MODO_RENDERIZADOR={app_evidencias.MODO_RENDERIZADOR!r})",
            app_evidencias.MODO_RENDERIZADOR == "bundled",
        )

        # --- 6 · o TTL não é decorativo ----------------------------------------------------
        ttl_cru, ttl_embrulhado = asyncio.run(_ttl_lado_a_lado())
        check(
            f"a loja CRUA guardaria para sempre (ttl={ttl_cru}) e a embrulhada expira "
            f"(ttl≈{int(ttl_embrulhado or 0)}s) — o FastMCP grava sessão SEM ttl",
            ttl_cru is None and ttl_embrulhado is not None,
        )

        # --- o que NÃO vai para a loja -----------------------------------------------------
        registro = sessions.evidencia_para_guardar(
            "techdocs", [{"index": i, "source": f"d{i}.md", "url": "u", "snippet": "x"} for i in range(50)]
        )
        check(
            "o registro guarda só domínio e fontes — a pergunta do usuário não entra "
            f"({sorted(registro)})",
            sorted(registro) == ["domain", "sources"],
        )
        check(
            f"e tem teto ({len(registro['sources'])} = MAX_CITACOES={sessions.MAX_CITACOES})",
            len(registro["sources"]) == sessions.MAX_CITACOES,
        )
        check(
            "e cada fonte carrega só os três campos que a resposta já mostrou",
            all(sorted(f) == ["index", "source", "url"] for f in registro["sources"]),
        )
    finally:
        (
            mcp_main.build_auth,
            tools_knowledge.retrieve,
            settings.entra_tenant_id,
            settings.entra_api_client_id,
            settings.mcp_public_base_url,
        ) = original
        shared_auth._current_user.set(None)
        logging.disable(logging.NOTSET)

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ a evidência chega à tabela de quem buscou, e só dela; o renderizador tem dono.")
    return 0


#: As tags que fazem o navegador BUSCAR algo ao encontrar a tag — não toda tag com URL. `<a>` e
#: `<area>` ficam de fora de propósito: um link para fora é navegação que a pessoa escolhe, não
#: carga automática. `<input>` entra porque `type="image"` busca o `src`.
_TAGS_QUE_BUSCAM = frozenset(
    {"script", "link", "img", "image", "video", "audio", "source", "iframe", "embed",
     "object", "track", "input", "frame"}
)

#: Os atributos por onde a URL chega em qualquer uma delas (`data` é do `<object>`).
_ATRIBUTOS_DE_BUSCA = frozenset({"src", "srcset", "href", "poster", "data"})


class _ColetorDeBuscas(HTMLParser):
    """Coleta as tags do documento que apontam para uma origem `http(s)` externa.

    PARSER, E NÃO REGEX, e a diferença tem medição por trás. A regex antiga olhava só
    `<script src>` e `<link href>` — mais estreita que a frase que ela sustenta ("esta página,
    ao abrir, vai à internet?"), porque `<img>`/`<video>`/`<iframe>` externos passariam. Alargar
    a regex, porém, produz FALSO VERMELHO: medido, o bundle contém a string
    `<iframe src="https://example.com"` **dentro do docstring de um `.py`** empacotado no
    payload do Pyodide, e três `url(https://…)` dentro de mensagens de erro de JS. Nenhum é
    markup.

    `HTMLParser` responde a pergunta certa porque trata `<script>`/`<style>` como CDATA: o que
    está lá dentro chega como texto, nunca como tag. É o parse do navegador, que é exatamente o
    que a asserção afirma medir.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.achadas: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _TAGS_QUE_BUSCAM:
            return
        for nome, valor in attrs:
            if nome in _ATRIBUTOS_DE_BUSCA and (valor or "").strip().lower().startswith(
                ("http://", "https://")
            ):
                self.achadas.add(tag)


def _tags_externas(html: str) -> list[str]:
    """Os tipos de tag que fazem o navegador buscar coisa de fora AO CARREGAR a página.

    É a pergunta certa sobre um renderizador: não "a string do CDN aparece em algum lugar do
    arquivo?" (aparece — dentro de JS, em comentário e no fonte do próprio módulo embutido),
    mas "esta página, ao abrir, vai à internet?". Ver `_ColetorDeBuscas`.
    """
    coletor = _ColetorDeBuscas()
    coletor.feed(html)
    coletor.close()
    return sorted(coletor.achadas)


async def _sintetizados(app, synthesize) -> list[str]:
    """As URIs que o FastMCP sintetizaria para o servidor REAL — tem que ser lista vazia."""
    mcp = app.state.fastmcp_server if hasattr(app, "state") else None
    if mcp is None:
        from mcp_app.auth import build_auth
        from mcp_app.main import build_mcp, register_surfaces, wire_registry

        wire_registry()
        mcp = build_mcp(build_auth(settings.mcp_public_base_url))
        register_surfaces(mcp)
    return [str(r.uri) for r in await synthesize(mcp)]


if __name__ == "__main__":
    sys.exit(main())
