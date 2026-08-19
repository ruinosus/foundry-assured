# Evidência por resposta — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Toda afirmação marcada com `[n]` fica rastreável até o documento que a sustenta — na resposta a que pertence, com o documento integral abrindo sob reautorização por usuário.

**Architecture:** A citação deixa de ser estado global da sessão e passa a pertencer à mensagem. O backend carimba o `message_id` no evento `sources` onde ele existe, e o frontend liga o evento sem id à próxima mensagem que começa (regra determinística: no caminho de workflow o evento é emitido entre o retrieve e o resolve, então a próxima mensagem É a resposta). Uma rota nova serve o documento integral, reautorizando por usuário com o **mesmo** trim do índice que já autoriza a recuperação — nunca uma segunda implementação da regra de acesso. A tela usa os slots canônicos do CopilotKit v2 (`assistantMessage`, `markdownRenderer`); nada de renderizador de chat próprio.

**Tech Stack:** Python 3.12 · FastAPI · `azure-search` REST (api-version `2025-05-01-preview`) · `azure-storage-blob` · `DefaultAzureCredential`/`OnBehalfOfCredential` · Next.js 16 / React 19 · `@copilotkit/react-core` v2 · next-intl

## Global Constraints

- **MÁXIMA MAIOR**: nenhum renderizador de chat próprio. Usar os slots exportados `CopilotChat → messageView → assistantMessage → markdownRenderer` (verificados em `apps/frontend/node_modules/@copilotkit/react-core/dist/copilotkit-D0aAnD3i.d.mts`).
- **RULE #6**: acesso é DADO, nunca lógica de classificação. A autorização da rota é o filtro `blob_url eq '<url>'` no índice com o token OBO do usuário no header `x-ms-query-source-authorization`. **Zero resultados ⇒ 403.** Proibido comparar grupos em código.
- **RULE #1**: não inventar assinatura de SDK. As chamadas ao Search usam `POST /indexes/{index}/docs/search?api-version=2025-05-01-preview` — medido funcionando em 19/ago/2026.
- **ADR-017**: código novo entra dentro de um módulo com `public.py`/`internal/`; import cross-module só via `public`. Rodar `uv run lint-imports --config importlinter.toml` antes de cada commit.
- **Regra #9**: nunca calcular caminho contando `parents[N]` a partir do arquivo; ancorar em `Path(app.__file__).resolve().parent.parent`.
- Testes de backend são **módulos executáveis**, não pytest: cada um tem `main()` e sai com código ≠ 0 ao falhar. Rodar com `uv run python -m tests.<módulo>.<nome>`.
- Todo texto de interface passa por next-intl. Chaves novas entram em **`messages/pt-BR.json` E `messages/en.json`** — `npm run check:i18n` é gate.
- Conventional Commits, escopos `backend`/`frontend`.
- Domínios no escopo: `selfwiki`, `techdocs`, `helpdesk`. `platform` fica de fora (não cita documento).

## Decisões técnicas fechadas antes do plano

Estas eram as pendências do entendimento. Fechadas por medição em 19/ago/2026, não por suposição:

1. **`[n]` sem citação correspondente** (o modelo escreve `[13]` com 12 documentos): renderiza como **texto simples**, nunca como link morto. Um link que não leva a lugar nenhum é pior que nenhum link.
2. **Abertura negada (403) também é auditada.** Tentativa negada é o sinal mais interessante da trilha, não o menos. O registro é **fail-soft** como o do `retrieve()` — falha de trilha não derruba a resposta, porque punir o usuário por problema de infraestrutura é pior que uma lacuna no relatório.
3. **Localizar o trecho para destacar**: normaliza espaço em branco dos dois lados e procura a maior sequência do trecho que exista no documento. Não achou ⇒ mostra o documento **sem** destaque. Nunca falha a visualização por causa do destaque.
4. **Onde a rota mora**: `app/modules/knowledge/api.py` (novo). O `knowledge` é dono da ACL e da recuperação — é ele que pode reusar o trim sem cruzar fronteira. Pôr no `grounded` obrigaria a importar `knowledge.internal`, que o contrato "knowledge internals are private" proíbe (`importlinter.toml:97`).
5. **SSRF**: a rota **nunca** aceita URL do cliente. Recebe o nome do documento, valida contra `^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$`, e constrói a URL a partir do container configurado do domínio.

---

### Task 1: `message_id` no evento `sources`

**Files:**
- Modify: `apps/backend/app/modules/grounded/internal/grounded.py:259-260`
- Modify: `apps/backend/app/modules/grounded/internal/sources_executor.py:58-59`
- Test: `apps/backend/tests/grounded/sources_message_id_test.py`

**Interfaces:**
- Consumes: nada (primeira tarefa).
- Produces: o payload do `CustomEvent(name="sources")` passa a ser `{"message_id": str | None, "citations": list[dict]}`. As citações mantêm a forma canônica `{type, title, url, snippet, index}`. A Task 4 consome isto no frontend.

**Contexto para quem implementa:** há DOIS emissores e eles vivem em momentos diferentes do turno. O `grounded.py` emite **depois** do texto — ali o `message_id` existe na função e é só passar. O `sources_executor.py` é um executor de workflow que roda **entre** o retrieve e o resolve, antes de a resposta existir — ali não há id, e mandar `None` é honesto. A Task 4 liga o `None` à próxima mensagem que começa.

- [ ] **Step 1: Write the failing test**

Criar `apps/backend/tests/grounded/sources_message_id_test.py`:

```python
"""O evento `sources` diz A QUAL RESPOSTA ele pertence.

POR QUE ISTO EXISTE. O painel de evidência guardava só a última resposta, e a causa era
esta: o evento não carregava o id da mensagem, então a tela recebia uma lista solta e não
tinha onde arquivá-la. O `message_id` estava na mesma função, duas linhas acima do `yield`.

O `None` do caminho de workflow é DELIBERADO, não lacuna: ali o evento sai entre o retrieve
e o resolve, antes de a resposta existir. Quem consome liga o `None` à próxima mensagem que
começa — e essa ordem é o que este teste guarda.
"""

from __future__ import annotations

import pathlib
import re
import sys

import app as _app

RAIZ = pathlib.Path(_app.__file__).resolve().parent.parent
GROUNDED = RAIZ / "app" / "modules" / "grounded" / "internal" / "grounded.py"
EXECUTOR = RAIZ / "app" / "modules" / "grounded" / "internal" / "sources_executor.py"

falhas: list[str] = []


def check(nome: str, ok: bool) -> None:
    print(f"  {'ok  ' if ok else 'FALHA'} {nome}")
    if not ok:
        falhas.append(nome)


def main() -> int:
    print("evento `sources` carrega o id da resposta")

    g = GROUNDED.read_text(encoding="utf-8")
    # O emissor grounded tem o message_id em escopo — precisa usá-lo.
    check(
        "grounded.py emite sources com message_id",
        bool(re.search(r'CustomEvent\(\s*name="sources"[^)]*message_id', g, re.S)),
    )
    check(
        "grounded.py emite sources com a chave citations",
        bool(re.search(r'CustomEvent\(\s*name="sources"[^)]*"citations"', g, re.S)),
    )

    e = EXECUTOR.read_text(encoding="utf-8")
    check(
        "sources_executor emite a mesma forma (dict com citations)",
        bool(re.search(r'WorkflowEvent\(\s*"sources"[^)]*"citations"', e, re.S)),
    )
    check(
        "sources_executor manda message_id None e diz por quê",
        '"message_id": None' in e and "resolve" in e,
    )

    print()
    if falhas:
        print(f"FALHOU: {len(falhas)} verificação(ões)")
        return 1
    print("tudo certo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd apps/backend && uv run python -m tests.grounded.sources_message_id_test
```
Expected: FALHOU: 4 verificação(ões) — todas as quatro, porque hoje o payload é uma lista solta.

- [ ] **Step 3: Implement — emissor grounded**

Em `apps/backend/app/modules/grounded/internal/grounded.py`, trocar:

```python
        if sources:
            yield enc.encode(CustomEvent(name="sources", value=sources))
```

por:

```python
        if sources:
            # A EVIDÊNCIA É DA RESPOSTA, não da sessão. Sem o `message_id` a tela recebia uma
            # lista solta e só podia guardar a última — rolar a conversa para cima mostrava
            # respostas antigas sem fonte nenhuma. O id está em escopo desde o início do turno.
            yield enc.encode(
                CustomEvent(name="sources", value={"message_id": message_id, "citations": sources})
            )
```

- [ ] **Step 4: Implement — emissor de workflow**

Em `apps/backend/app/modules/grounded/internal/sources_executor.py`, trocar:

```python
        if citacoes:
            ctx.add_event(WorkflowEvent("sources", data=citacoes))
```

por:

```python
        if citacoes:
            # `message_id: None` é DELIBERADO. Este executor roda ENTRE o retrieve e o resolve —
            # a resposta ainda não existe, então não há id para carimbar. Quem consome liga o
            # None à próxima mensagem que começa, e nesta posição essa mensagem É o resolve.
            # Emitir depois do resolve daria o id, mas faria o painel só aparecer no fim, e a
            # pessoa lê a resposta enquanto ela chega.
            ctx.add_event(
                WorkflowEvent("sources", data={"message_id": None, "citations": citacoes})
            )
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd apps/backend && uv run python -m tests.grounded.sources_message_id_test
```
Expected: `tudo certo`, exit 0.

- [ ] **Step 6: Rodar os gates que tocam este caminho**

```bash
cd apps/backend
uv run python -m tests.grounded.citation_vocabulary_test
uv run python -m tests.helpdesk.sources_event_test
uv run lint-imports --config importlinter.toml
```
Expected: os três passam. Se `citation_vocabulary_test` reclamar da forma do payload, ele valida a forma da CITAÇÃO (que não mudou) — leia a mensagem antes de mexer nele.

- [ ] **Step 7: Commit**

```bash
git add apps/backend/app/modules/grounded/internal/grounded.py \
        apps/backend/app/modules/grounded/internal/sources_executor.py \
        apps/backend/tests/grounded/sources_message_id_test.py
git commit -m "feat(backend): o evento de fontes diz a qual resposta pertence"
```

---

### Task 2: citações gravadas junto da mensagem

**Files:**
- Modify: `apps/backend/app/modules/conversations/internal/listing.py:84-109`
- Modify: `apps/backend/app/modules/conversations/internal/store.py:142-177` (`sanitize` passa a redigir `annotations[].snippet`)
- Modify: `apps/backend/app/modules/conversations/public.py` (reexporta a assinatura nova)
- Modify: `apps/backend/app/modules/grounded/internal/grounded.py` (chamada de `_record_turn`)
- Test: `apps/backend/tests/conversations/citations_persisted_test.py`

**Interfaces:**
- Consumes: as citações montadas na Task 1 (`sources`, forma `{type, title, url, snippet, index}`).
- Produces: `record_turn(user_id, agent, conversation_id, user_text, assistant_text, citations=None)` — o parâmetro novo é **keyword-only com default `None`**, para que os chamadores existentes não mudem. A mensagem do assistente ganha a chave `annotations` no JSONL.

**Contexto para quem implementa:** hoje as mensagens gravadas têm `annotations: nenhuma` — verificado no blob `59064647-…/selfwiki/bb82ca58-….jsonl` em 19/ago. Reabrir uma conversa antiga mostra respostas sem fonte. Gravar título/índice **não** vaza conteúdo, porque abrir o documento reautoriza no clique (Task 3).

- [ ] **Step 1: Write the failing test**

Criar `apps/backend/tests/conversations/citations_persisted_test.py`:

```python
"""A conversa gravada guarda a evidência da resposta.

POR QUE ISTO EXISTE. Medido em 19/ago/2026: as mensagens do assistente no blob de conversa
tinham `annotations: nenhuma`. A evidência vivia só como evento ao vivo — recarregar a página
apagava a fonte de toda a conversa. Num produto chamado Assurance Console isso é falha, não
cosmética.

NÃO GUARDA CONTEÚDO: só título, url, índice e o trecho que já saiu na resposta. O direito de
LER o documento é verificado no clique (rota /source), nunca herdado do momento da resposta.
"""

from __future__ import annotations

import sys

from app.modules.conversations.internal import listing


def main() -> int:
    print("citações são gravadas junto da mensagem")
    falhas: list[str] = []

    def check(nome: str, ok: bool) -> None:
        print(f"  {'ok  ' if ok else 'FALHA'} {nome}")
        if not ok:
            falhas.append(nome)

    gravado: dict = {}

    class LojaFalsa:
        def append(self, user, agent, conv, messages):
            gravado["mensagens"] = messages

    # `listing` resolve a loja por chamada de função — trocar o atributo do MÓDULO é o que
    # intercepta. Patchar em outro lugar dá falso positivo (aconteceu antes neste repo).
    original = listing.store
    listing.store = lambda: LojaFalsa()
    try:
        listing.record_turn(
            "user-1", "selfwiki", "conv-1", "pergunta?", "resposta [1]",
            citations=[{"type": "citation", "title": "page-11.md", "url": "https://x/y/page-11.md",
                        "snippet": "trecho", "index": 1}],
        )
    finally:
        listing.store = original

    msgs = gravado.get("mensagens") or []
    check("gravou duas mensagens (pergunta + resposta)", len(msgs) == 2)

    assistente = next((m for m in msgs if m.get("role") == "assistant"), {})
    ann = assistente.get("annotations") or []
    check("a resposta carrega annotations", len(ann) == 1)
    check("a annotation tem o índice que amarra o [n]", (ann[0] if ann else {}).get("index") == 1)
    check("a annotation tem o título do documento", (ann[0] if ann else {}).get("title") == "page-11.md")
    check("a pergunta do usuário NÃO recebe annotations",
          "annotations" not in next((m for m in msgs if m.get("role") == "user"), {}))

    # Sem citação, o formato antigo continua idêntico — chamador existente não muda.
    gravado.clear()
    listing.store = lambda: LojaFalsa()
    try:
        listing.record_turn("user-1", "selfwiki", "conv-2", "p", "r")
    finally:
        listing.store = original
    m2 = next((m for m in (gravado.get("mensagens") or []) if m.get("role") == "assistant"), {})
    check("sem citação, a mensagem não ganha chave vazia", "annotations" not in m2)

    print()
    if falhas:
        print(f"FALHOU: {len(falhas)} verificação(ões)")
        return 1
    print("tudo certo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd apps/backend && uv run python -m tests.conversations.citations_persisted_test
```
Expected: FALHA — `record_turn() got an unexpected keyword argument 'citations'`.

- [ ] **Step 3: Implement — `record_turn` aceita citações**

Em `apps/backend/app/modules/conversations/internal/listing.py`, trocar a assinatura e o corpo:

```python
def record_turn(
    user_id: str,
    agent: str,
    conversation_id: str,
    user_text: str,
    assistant_text: str,
    *,
    citations: list[dict] | None = None,
) -> None:
```

e o bloco que monta as linhas:

```python
    linhas = []
    if user_text:
        linhas.append({"role": "user", "text": user_text})
    if assistant_text:
        # A EVIDÊNCIA VIAJA COM A RESPOSTA. Sem isto, recarregar a página apagava a fonte de
        # toda a conversa — a citação vivia só como evento ao vivo. Guardamos título, url,
        # índice e o trecho que JÁ saiu na resposta; nunca o documento. O direito de ler o
        # documento é verificado no clique (rota /source), nunca herdado daqui.
        #
        # `keyword-only` com default None para que os chamadores existentes não mudem, e a
        # chave só existe quando há citação — mensagem sem fonte continua byte-idêntica.
        mensagem = {"role": "assistant", "text": assistant_text}
        if citations:
            mensagem["annotations"] = citations
        linhas.append(mensagem)
```

- [ ] **Step 4: Implement — o grounded passa as citações**

Em `apps/backend/app/modules/grounded/internal/grounded.py`, trocar:

```python
        _record_turn(_usuario, _conversa, thread_id, user_text, "".join(resposta))
```

por:

```python
        _record_turn(_usuario, _conversa, thread_id, user_text, "".join(resposta), citations=sources)
```

- [ ] **Step 5: Implement — o redator alcança o trecho gravado**

`sanitize()` é "o ponto único de escrita da ADR-023" (a docstring dele diz isso), mas hoje ele
só redige `text` e `contents[].text`. O `snippet` que a Task 2 grava é conteúdo de documento e
passaria ao largo. Em `apps/backend/app/modules/conversations/internal/store.py`, dentro do laço
de `sanitize`, **depois** do bloco de `contents`, acrescentar:

```python
        # A CITAÇÃO TAMBÉM CARREGA CONTEÚDO. `annotations[].snippet` é trecho de documento, e
        # sem este ramo ele chegaria ao blob sem passar pelo redator — furando justamente o
        # ponto que esta função existe para ser. Título, url e índice não são conteúdo e ficam
        # como estão.
        anotacoes = copia.get("annotations")
        if isinstance(anotacoes, list):
            novas_anot = []
            for anot in anotacoes:
                if isinstance(anot, dict) and isinstance(anot.get("snippet"), str):
                    anot = dict(anot)
                    anot["snippet"], tipos = redact(anot["snippet"])
                    achados.extend(t for t in tipos if t not in achados)
                novas_anot.append(anot)
            copia["annotations"] = novas_anot
```

Acrescentar ao teste `citations_persisted_test.py`, antes do `print()` final, a verificação de
que o redator alcança o trecho — usando a mesma loja falsa, mas passando pelo `sanitize` real:

```python
    # O redator TEM de alcançar o trecho da citação. Sem isto, `annotations` seria o caminho
    # por onde conteúdo entra no blob sem passar pelo ponto único de escrita da ADR-023.
    from app.modules.conversations.internal.store import sanitize

    saneadas, tipos = sanitize([
        {"role": "assistant", "text": "ok",
         "annotations": [{"title": "d.md", "index": 1, "snippet": "contato: fulano@exemplo.com"}]},
    ])
    trecho_salvo = saneadas[0]["annotations"][0]["snippet"]
    check("o redator alcança annotations[].snippet", "fulano@exemplo.com" not in trecho_salvo)
    check("o redator reporta o tipo encontrado no trecho", len(tipos) > 0)
    check("título e índice atravessam intactos",
          saneadas[0]["annotations"][0]["title"] == "d.md"
          and saneadas[0]["annotations"][0]["index"] == 1)
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd apps/backend && uv run python -m tests.conversations.citations_persisted_test
```
Expected: `tudo certo`, exit 0. Se o redator não reconhecer e-mail, troque o valor do teste por
um que `app/modules/audit/public.redact` reconheça — leia a implementação dele antes de escolher.

- [ ] **Step 7: Rodar os gates de conversa**

```bash
cd apps/backend
uv run python -m tests.conversations.conversation_store_test
uv run python -m tests.conversations.provider_invoked_test
uv run python -m tests.conversations.usage_seam_test
uv run lint-imports --config importlinter.toml
```
Expected: os quatro passam. O `sanitize()` do store roda o redator sobre as mensagens — se ele reclamar de `annotations`, é porque ele só conhece `text`; nesse caso estenda o `sanitize` para preservar chaves desconhecidas em vez de descartá-las, e diga isso no commit.

- [ ] **Step 8: Commit**

```bash
git add apps/backend/app/modules/conversations/internal/listing.py \
        apps/backend/app/modules/conversations/internal/store.py \
        apps/backend/app/modules/grounded/internal/grounded.py \
        apps/backend/tests/conversations/citations_persisted_test.py
git commit -m "feat(backend): a conversa gravada guarda a evidência da resposta"
```

---

### Task 3: rota que serve o documento, reautorizando por usuário

**Files:**
- Create: `apps/backend/app/modules/knowledge/api.py`
- Modify: `apps/backend/app/modules/knowledge/public.py` (exporta `authorized_document`)
- Create: `apps/backend/app/modules/knowledge/internal/document.py`
- Modify: `apps/backend/app/registry.py` (campo `corpus_container` no `DomainSpec`; preencher nos três domínios; incluir o router)
- Test: `apps/backend/tests/knowledge/document_access_test.py`

**Interfaces:**
- Consumes: `retrieval._user_search_token(user)` (já existe, `apps/backend/app/modules/knowledge/internal/retrieval.py:118`), `domain_spec(id)` do registry.
- Produces:
  - `async def authorized_document(domain, name: str, user) -> tuple[str, str]` — devolve `(blob_url, conteúdo)`. Levanta `PermissionError` quando o trim devolve zero, `FileNotFoundError` quando o blob não existe, `ValueError` quando o nome é inválido.
  - Rota `GET /source/{domain_id}/{name}` → `{"name": str, "url": str, "content": str}`. A Task 6 consome.

**Contexto para quem implementa — leia antes de codar:**

Esta é a tarefa sensível do plano. Ela cria a **primeira** rota que devolve o conteúdo integral de um documento com controle de acesso por documento. Três armadilhas, todas já medidas:

1. **Nunca aceite URL do cliente.** Isso seria SSRF: alguém passa a URL de outra conta de storage e o backend a busca com a identidade da aplicação. A rota recebe o **nome** e constrói a URL a partir do container configurado do domínio.
2. **A autorização é o trim, não uma regra nossa.** Medido em 19/ago contra `selfwiki-docbundles-ks-index`: filtro `blob_url eq '<url>'` devolve 5 trechos com a identidade do usuário no header `x-ms-query-source-authorization`, **0** sem identidade, e **401** com token inválido. Zero ⇒ 403. Comparar grupos em código viola a RULE #6.
3. **`helpdesk` não tem `acl_group_map`** — não há trim para reaplicar. Ali sessão válida é a regra inteira, e o código diz isso explicitamente.

- [ ] **Step 1: Write the failing test**

Criar `apps/backend/tests/knowledge/document_access_test.py`:

```python
"""A rota de documento reautoriza — sempre, e com o MESMO trim da recuperação.

POR QUE ISTO EXISTE. Esta é a primeira rota do produto que devolve o conteúdo INTEGRAL de um
documento com controle de acesso por documento. Se ela não reautorizar, vira o caminho que
contorna a RULE #6: bastaria adivinhar um nome de arquivo.

O QUE ELE GUARDA, e por que cada um:
  · nome inválido é recusado ANTES de qualquer I/O — `..%2f` não pode virar caminho
  · zero resultados no trim ⇒ PermissionError, nunca "não achei" (fail-closed)
  · o domínio COM acl_group_map manda o header de identidade; o SEM, não
  · a URL é CONSTRUÍDA do container configurado, nunca aceita do chamador (SSRF)
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

from app.modules.knowledge.internal import document


def main() -> int:
    print("a rota de documento reautoriza por usuário")
    falhas: list[str] = []

    def check(nome: str, ok: bool) -> None:
        print(f"  {'ok  ' if ok else 'FALHA'} {nome}")
        if not ok:
            falhas.append(nome)

    com_acl = SimpleNamespace(
        id="selfwiki", search_index="selfwiki-docbundles-ks-index",
        search_endpoint="https://srch.example.net", corpus_container="selfwiki-corpus",
        acl_group_map={"app-users": "grupo-1"},
    )
    sem_acl = SimpleNamespace(
        id="helpdesk", search_index="helpdesk-runbooks-ks-index",
        search_endpoint="https://srch.example.net", corpus_container="corpus",
        acl_group_map=None,
    )

    # ── nome inválido é recusado antes de qualquer I/O ──────────────────────────────
    for ruim in ("../secreto.md", "a/b.md", "", "x" * 300, "arquivo com espaço.md"):
        try:
            asyncio.run(document.authorized_document(com_acl, ruim, None))
            check(f"recusa nome inválido {ruim[:18]!r}", False)
        except ValueError:
            check(f"recusa nome inválido {ruim[:18]!r}", True)
        except Exception as exc:
            check(f"recusa nome inválido {ruim[:18]!r} (veio {type(exc).__name__})", False)

    # ── o trim manda: zero resultados ⇒ PermissionError ─────────────────────────────
    chamadas: list[dict] = []

    async def busca_falsa(*, endpoint, index, filtro, token, user_token):
        chamadas.append({"index": index, "filtro": filtro, "user_token": user_token})
        return 0  # ninguém autorizado

    async def token_falso(user):
        return "token-do-usuario"

    document._contar_autorizado = busca_falsa
    document._user_search_token = token_falso
    document._token_app = lambda: asyncio.sleep(0, result="token-app")

    try:
        asyncio.run(document.authorized_document(com_acl, "page-11.md", object()))
        check("zero no trim levanta PermissionError", False)
    except PermissionError:
        check("zero no trim levanta PermissionError", True)
    except Exception as exc:
        check(f"zero no trim levanta PermissionError (veio {type(exc).__name__}: {exc})", False)

    ultima = chamadas[-1] if chamadas else {}
    check("o filtro é por blob_url construída, não por nome cru",
          "blob_url eq '" in str(ultima.get("filtro", "")))
    check("a URL construída aponta para o container configurado",
          "/selfwiki-corpus/page-11.md'" in str(ultima.get("filtro", "")))
    check("domínio COM acl manda a identidade do usuário",
          ultima.get("user_token") == "token-do-usuario")

    # ── domínio sem ACL não manda identidade ────────────────────────────────────────
    chamadas.clear()
    try:
        asyncio.run(document.authorized_document(sem_acl, "runbook-1.md", object()))
    except Exception:
        pass
    ultima = chamadas[-1] if chamadas else {}
    check("domínio SEM acl não manda identidade", ultima.get("user_token") is None)

    print()
    if falhas:
        print(f"FALHOU: {len(falhas)} verificação(ões)")
        return 1
    print("tudo certo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd apps/backend && uv run python -m tests.knowledge.document_access_test
```
Expected: `ModuleNotFoundError: No module named 'app.modules.knowledge.internal.document'`.

- [ ] **Step 3: Implement — o núcleo da autorização**

Criar `apps/backend/app/modules/knowledge/internal/document.py`:

```python
"""Serve o documento INTEGRAL, reautorizando a leitura a cada requisição.

A REAUTORIZAÇÃO É O MESMO TRIM DA RECUPERAÇÃO, e isso não é economia de código — é a RULE #6.
O acesso de cada documento é DADO (o campo `groups` que a ingestão carimba); comparar grupos
aqui seria uma segunda implementação da regra, que divergiria da primeira no dia em que uma
das duas mudasse. Reusar o filtro garante que não pode divergir, porque É a mesma.

Medido em 19/ago/2026 contra `selfwiki-docbundles-ks-index`:
    filtro blob_url eq '<url>' + x-ms-query-source-authorization do usuário  →  5 trechos
    o mesmo filtro sem identidade                                            →  0
    o mesmo filtro com token inválido                                        →  401

NUNCA ACEITA URL DO CHAMADOR. Recebe o NOME e constrói a URL a partir do container configurado
do domínio. Aceitar URL seria SSRF: bastaria apontar para outra conta de storage e o backend a
buscaria com a identidade da aplicação.

O DIREITO NÃO SE HERDA. Uma citação emitida ontem não autoriza abrir o documento hoje — por
isso a verificação acontece no acesso, nunca na emissão da citação.
"""

from __future__ import annotations

import re

from app.shared.settings import settings

# Nome de blob, e nada além disso: sem barra, sem `..`, sem espaço. Recusado ANTES de qualquer
# I/O — um nome que vira caminho é o começo de um path traversal.
_NOME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
_SEARCH_SCOPE = "https://search.azure.com/.default"
_API = "2025-05-01-preview"  # a mesma do retrieval (RULE #1: medida, não inventada)


async def _token_app() -> str:
    from azure.identity.aio import DefaultAzureCredential

    cred = DefaultAzureCredential()
    try:
        return (await cred.get_token(_SEARCH_SCOPE)).token
    finally:
        import contextlib

        with contextlib.suppress(Exception):
            await cred.close()


async def _user_search_token(user):
    """Delegado ao retrieval — uma implementação de OBO, não duas."""
    from app.modules.knowledge.internal.retrieval import _user_search_token as _obo

    return await _obo(user)


async def _contar_autorizado(*, endpoint, index, filtro, token, user_token) -> int:
    """Quantos trechos deste documento a identidade PODE ler. Zero ⇒ não pode."""
    import json

    import httpx

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if user_token:
        headers["x-ms-query-source-authorization"] = user_token
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.post(
            f"{endpoint.rstrip('/')}/indexes/{index}/docs/search?api-version={_API}",
            headers=headers,
            content=json.dumps({"search": "*", "filter": filtro, "top": 1, "count": True}),
        )
        r.raise_for_status()
        return int(r.json().get("@odata.count") or 0)


def _blob_url(domain, name: str) -> str:
    conta = settings.azure_storage_account or ""
    container = getattr(domain, "corpus_container", "") or ""
    return f"https://{conta}.blob.core.windows.net/{container}/{name}"


async def authorized_document(domain, name: str, user) -> tuple[str, str]:
    """`(url, conteúdo)` do documento — ou levanta, sem nunca devolver conteúdo não autorizado.

    `PermissionError` quando o trim não autoriza (fail-closed).
    `FileNotFoundError` quando o blob não existe.
    `ValueError` quando o nome não é um nome de blob.
    """
    if not name or not _NOME_OK.match(name):
        raise ValueError(f"nome de documento inválido: {name[:40]!r}")

    url = _blob_url(domain, name)

    # A identidade do USUÁRIO só viaja em domínio com ACL — espelha `retrieval.retrieve`.
    # Num domínio sem `acl_group_map` não há grupo declarado em documento nenhum, e sessão
    # válida (já exigida pela rota) é a regra inteira.
    user_token = await _user_search_token(user) if getattr(domain, "acl_group_map", None) else None
    quantos = await _contar_autorizado(
        endpoint=getattr(domain, "search_endpoint", "") or settings.azure_search_endpoint,
        index=getattr(domain, "search_index", ""),
        filtro=f"blob_url eq '{url}'",
        token=await _token_app(),
        user_token=user_token,
    )
    if quantos <= 0:
        # Fail-closed. Não distinguimos "não existe" de "não pode ler" DE PROPÓSITO: a
        # diferença entre as duas respostas é um oráculo que revela quais documentos existem.
        raise PermissionError(f"sem autorização de leitura para {name}")

    from azure.identity.aio import DefaultAzureCredential
    from azure.storage.blob.aio import BlobClient

    cred = DefaultAzureCredential()
    try:
        async with BlobClient.from_blob_url(url, credential=cred) as blob:
            from azure.core.exceptions import ResourceNotFoundError

            try:
                fluxo = await blob.download_blob()
                bruto = await fluxo.readall()
            except ResourceNotFoundError as exc:
                raise FileNotFoundError(name) from exc
    finally:
        import contextlib

        with contextlib.suppress(Exception):
            await cred.close()

    return url, bruto.decode("utf-8", errors="replace")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd apps/backend && uv run python -m tests.knowledge.document_access_test
```
Expected: `tudo certo`, exit 0.

- [ ] **Step 5: Implement — `corpus_container` no registry**

Em `apps/backend/app/registry.py`, adicionar o campo ao `DomainSpec` (depois de `search_endpoint`):

```python
    corpus_container: str = ""  # container do blob que guarda o documento integral (rota /source)
```

e preencher nos três domínios em `_domains()` — `helpdesk` com `cfg.azure_storage_container`, `techdocs` com `cfg.techdocs_storage_container`, `selfwiki` com `cfg.selfwiki_storage_container`.

- [ ] **Step 6: Implement — a rota**

Criar `apps/backend/app/modules/knowledge/api.py`:

```python
"""HTTP para confirmar evidência: o documento integral que sustenta uma citação.

MORA NO `knowledge` porque é ele o dono da ACL e da recuperação — só daqui dá para reusar o
trim sem cruzar fronteira. Pôr no `grounded` obrigaria a importar `knowledge.internal`, que o
contrato "knowledge internals are private" proíbe (importlinter.toml).

SÓ LEITURA. Não existe rota de escrita aqui e não deve existir.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.modules.knowledge.public import authorized_document
from app.shared.auth import auth_dependencies, current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/source", tags=["source"], dependencies=[*auth_dependencies()])


@router.get("/{domain_id}/{name}")
async def read_source(domain_id: str, name: str) -> dict:
    from app.registry import domain_spec

    try:
        domain = domain_spec(domain_id)
    except Exception:
        raise HTTPException(status_code=404, detail="domínio desconhecido") from None
    if getattr(domain, "kind", "") == "tool":
        raise HTTPException(status_code=404, detail="domínio não tem documentos")

    user = current_user()
    try:
        url, conteudo = await authorized_document(domain, name, user)
    except ValueError:
        raise HTTPException(status_code=400, detail="nome de documento inválido") from None
    except PermissionError:
        _auditar(domain_id, name, autorizado=False)
        # 403 e não 404: a pessoa está autenticada e a rota existe. Não vazamos se o documento
        # existe — `authorized_document` já não distingue os dois casos.
        raise HTTPException(status_code=403, detail="sem autorização para este documento") from None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="documento não encontrado") from None

    _auditar(domain_id, name, autorizado=True)
    return {"name": name, "url": url, "content": conteudo}


def _auditar(domain_id: str, name: str, *, autorizado: bool) -> None:
    """Registra a leitura — e TAMBÉM a negada, que é o sinal mais interessante da trilha.

    Fail-soft como o registro do `retrieve()`: ler é reversível, e negar a leitura por causa
    de um problema de infraestrutura de auditoria puniria o usuário. A ausência aparece como
    lacuna no relatório de verificação, que é onde deve aparecer.
    """
    import contextlib

    with contextlib.suppress(Exception):
        from app.modules.audit.public import actor, actor_detail, record

        record(
            scope="access",
            actor=actor(),
            kind="access",
            summary=f"documento {'aberto' if autorizado else 'NEGADO'}: {name}",
            ref=domain_id,
            detail={"document": name, "authorized": autorizado, **actor_detail()},
        )
```

Em `apps/backend/app/modules/knowledge/public.py`, adicionar ao import e ao `__all__`:

```python
from app.modules.knowledge.internal.document import authorized_document
```

Em `apps/backend/app/registry.py`, dentro de `include_routers`, importar `from app.modules.knowledge import api as knowledge` e incluí-lo na tupla de módulos.

- [ ] **Step 7: Run gates**

```bash
cd apps/backend
uv run python -m tests.knowledge.document_access_test
uv run python -m tests.smoke.routes_snapshot_test
uv run lint-imports --config importlinter.toml
uv run python -m tests.architecture.module_graph_test
```
Expected: os quatro passam. O `routes_snapshot_test` vai acusar a rota nova — **atualize o snapshot** e confira que ele lista `/source/{domain_id}/{name}` nos dois modos (`self_hosted` e `shared`).

- [ ] **Step 8: Commit**

```bash
git add apps/backend/app/modules/knowledge/ apps/backend/app/registry.py \
        apps/backend/tests/knowledge/document_access_test.py apps/backend/tests/smoke/
git commit -m "feat(backend): rota que serve o documento citado, reautorizando por usuário"
```

---

### Task 4: a evidência passa a ser da mensagem (frontend)

**Files:**
- Create: `apps/frontend/lib/citations.tsx`
- Modify: `apps/frontend/components/console/AssuranceConsole.tsx`
- Modify: `apps/frontend/components/console/EvidencePanel.tsx`

**Interfaces:**
- Consumes: o `CustomEvent` da Task 1 (`{message_id, citations}`).
- Produces:
  - `<CitationsProvider agentId={string}>` — assina o agente e mantém o mapa `messageId → Citation[]`.
  - `useCitationsFor(messageId: string): Citation[]`
  - `type Citation = { type?: "citation"; title: string; url?: string; snippet?: string; index: number }`
  - A Task 5 e a Task 6 consomem os dois hooks.

**Contexto para quem implementa:** a regra de ligação tem dois ramos e os dois são necessários. Evento **com** `message_id` (caminho grounded, emitido depois do texto) liga direto. Evento **sem** (caminho de workflow, emitido entre o retrieve e o resolve) fica pendente e liga na próxima mensagem que começa — que naquela posição é a resposta. Aceite também o formato antigo (array solto): uma aba aberta durante o deploy continua recebendo eventos do backend anterior, e um painel que esvazia no meio da conversa parece resposta sem fonte, que é falha grave com aparência de cosmética.

- [ ] **Step 1: Implement — o provider**

Criar `apps/frontend/lib/citations.tsx`:

```tsx
"use client";

// A EVIDÊNCIA É DA MENSAGEM, não da sessão.
//
// Antes daqui o painel guardava um array só e o RUN_STARTED o limpava a cada turno: rolar a
// conversa para cima mostrava respostas antigas sem fonte nenhuma. A causa raiz estava no
// backend — o evento não dizia a qual resposta pertencia (ver Task 1).
//
// DUAS REGRAS DE LIGAÇÃO, e as duas são necessárias:
//   · evento COM message_id  → liga direto (caminho grounded: emitido depois do texto)
//   · evento SEM message_id  → fica pendente e liga na PRÓXIMA mensagem que começa
//     (caminho de workflow: o executor emite entre o retrieve e o resolve, então a próxima
//      mensagem É o resolve — a ordem é o que torna a regra determinística)

import { useAgent } from "@copilotkit/react-core/v2";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";

export interface Citation {
  type?: "citation";
  title: string;
  url?: string;
  snippet?: string;
  index: number;
}

const Ctx = createContext<Record<string, Citation[]>>({});

// Aceita a forma nova {message_id, citations}, a antiga (array solto) e o vocabulário anterior
// ({source, content}). Uma aba aberta durante o deploy continua recebendo o formato antigo.
function normalizar(value: unknown): { messageId: string | null; citations: Citation[] } {
  const bruto = Array.isArray(value)
    ? { message_id: null, citations: value }
    : ((value ?? {}) as { message_id?: string | null; citations?: unknown[] });
  const lista = (bruto.citations ?? []) as (Citation & { source?: string; content?: string })[];
  return {
    messageId: bruto.message_id ?? null,
    citations: lista.map((c) => ({
      index: c.index,
      title: c.title ?? c.source ?? "",
      url: c.url,
      snippet: c.snippet ?? c.content,
    })),
  };
}

export function CitationsProvider({ agentId, children }: { agentId: string; children: ReactNode }) {
  const { agent } = useAgent({ agentId });
  const [porMensagem, setPorMensagem] = useState<Record<string, Citation[]>>({});
  // `ref` e não `state`: a pendência é lida dentro do próprio handler de evento, e um state
  // capturado no closure daria o valor do render anterior.
  const pendente = useRef<Citation[] | null>(null);

  useEffect(() => {
    if (!agent) return;
    const sub = agent.subscribe({
      onEvent: ({ event }: any) => {
        if (event?.type === "CUSTOM" && event?.name === "sources") {
          const { messageId, citations } = normalizar(event.value);
          if (!citations.length) return;
          if (messageId) setPorMensagem((m) => ({ ...m, [messageId]: citations }));
          else pendente.current = citations;
        } else if (event?.type === "TEXT_MESSAGE_START") {
          const esperando = pendente.current;
          const id = event?.messageId ?? event?.message_id;
          if (esperando && id) {
            pendente.current = null;
            setPorMensagem((m) => ({ ...m, [id]: esperando }));
          }
        }
      },
    });
    return () => sub.unsubscribe();
  }, [agent]);

  return <Ctx.Provider value={porMensagem}>{children}</Ctx.Provider>;
}

export function useCitationsFor(messageId: string | undefined): Citation[] {
  const mapa = useContext(Ctx);
  return (messageId && mapa[messageId]) || [];
}
```

- [ ] **Step 2: Implement — montar o provider em volta do chat**

Em `apps/frontend/components/console/AssuranceConsole.tsx`, importar e envolver o bloco do chat:

```tsx
import { CitationsProvider } from "@/lib/citations";
```

e trocar o conteúdo de `<div className="console-chat copilotkit-chat-host">` para que `CopilotChat` fique dentro de `<CitationsProvider agentId={activeAgentId}>…</CitationsProvider>`.

- [ ] **Step 3: Verify**

```bash
cd apps/frontend && npm run typecheck && npm run lint
```
Expected: ambos passam.

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/lib/citations.tsx apps/frontend/components/console/AssuranceConsole.tsx
git commit -m "feat(frontend): a evidência passa a pertencer à mensagem, não à sessão"
```

---

### Task 5: evidência sob cada resposta + `[n]` clicável

**Files:**
- Create: `apps/frontend/components/console/MessageEvidence.tsx`
- Modify: `apps/frontend/components/console/AssuranceConsole.tsx`
- Modify: `apps/frontend/messages/pt-BR.json`, `apps/frontend/messages/en.json`
- Modify: `apps/frontend/app/globals.css` (ou o arquivo de estilo onde vivem as classes `evidence-*`)

**Interfaces:**
- Consumes: `useCitationsFor` e `Citation` da Task 4.
- Produces: `<AssistantMessageComEvidencia>` passado ao slot `assistantMessage` do `CopilotChatMessageView`. Emite `window` custom event `"abrir-fonte"` com `{ detail: { domainId, name } }`, que a Task 6 escuta.

**Contexto para quem implementa:** os slots são API pública tipada do CopilotKit v2 — confira as assinaturas em `node_modules/@copilotkit/react-core/dist/copilotkit-D0aAnD3i.d.mts` antes de codar (`CopilotChatAssistantMessageProps` e `CopilotChatMessageViewProps`). O `markdownRenderer` recebe `{ content }` e devolve JSX; delegue ao renderizador padrão (`CopilotChatAssistantMessage.MarkdownRenderer`) e intervenha **só** no `[n]`, senão tabela e Mermaid — que os prompts pedem explicitamente — param de renderizar.

- [ ] **Step 1: Implement — o componente**

Criar `apps/frontend/components/console/MessageEvidence.tsx`:

```tsx
"use client";

// A evidência DA RESPOSTA, logo abaixo dela — e o [n] do texto levando até ela.
//
// Confirmar evidência é ver a fonte junto da afirmação, não num painel que já trocou de
// conteúdo. Antes daqui o painel lateral guardava só o último turno; rolar a conversa para
// cima mostrava respostas sem fonte.
//
// USA OS SLOTS CANÔNICOS do CopilotKit v2 — `assistantMessage` e, dentro dele,
// `markdownRenderer`. Nada de renderizador de chat próprio (MÁXIMA MAIOR). O renderizador
// padrão continua fazendo todo o trabalho de markdown; nós só trocamos o `[n]` por um botão.

import { CopilotChatAssistantMessage } from "@copilotkit/react-core/v2";
import { useTranslations } from "next-intl";
import { Fragment } from "react";
import { useCitationsFor, type Citation } from "@/lib/citations";

function abrirFonte(domainId: string, name: string, snippet?: string) {
  // O TRECHO VIAJA JUNTO porque é ele que o visualizador destaca. Sem ele o documento abre
  // inteiro e a pessoa caça em 9KB — que é o problema que este trabalho existe para resolver.
  window.dispatchEvent(new CustomEvent("abrir-fonte", { detail: { domainId, name, snippet } }));
}

// Troca `[n]` por um botão quando existe citação n. Índice órfão (o modelo escreveu [13] com
// 12 documentos) fica TEXTO SIMPLES — um link que não leva a lugar nenhum é pior que nenhum.
function ComMarcadores({ content, citations, domainId }: {
  content: string; citations: Citation[]; domainId: string;
}) {
  const porIndice = new Map(citations.map((c) => [c.index, c]));
  const partes = content.split(/(\[\d{1,3}\])/g);
  return (
    <>
      {partes.map((parte, i) => {
        const m = /^\[(\d{1,3})\]$/.exec(parte);
        const cit = m ? porIndice.get(Number(m[1])) : undefined;
        if (!cit) {
          return (
            <Fragment key={i}>
              <CopilotChatAssistantMessage.MarkdownRenderer content={parte} />
            </Fragment>
          );
        }
        return (
          <button key={i} type="button" className="cit-ref" title={cit.title}
                  onClick={() => abrirFonte(domainId, cit.title, cit.snippet)}>
            [{cit.index}]
          </button>
        );
      })}
    </>
  );
}

export function makeAssistantMessage(domainId: string) {
  return function AssistantMessageComEvidencia(props: any) {
    const te = useTranslations("evidence");
    const citations = useCitationsFor(props?.message?.id);

    return (
      <CopilotChatAssistantMessage
        {...props}
        markdownRenderer={({ content }: { content: string }) =>
          citations.length
            ? <ComMarcadores content={content} citations={citations} domainId={domainId} />
            : <CopilotChatAssistantMessage.MarkdownRenderer content={content} />
        }
      >
        {citations.length > 0 && (
          <div className="msg-evidence">
            <div className="msg-evidence-title">{te("sources")} ({citations.length})</div>
            <ol className="msg-evidence-list">
              {citations.map((c) => (
                <li key={c.index}>
                  <button type="button" className="msg-evidence-item"
                          onClick={() => abrirFonte(domainId, c.title, c.snippet)}>
                    <span className="cit-idx" aria-hidden>{c.index}</span>
                    <span className="cit-title">{c.title}</span>
                    <span className="cit-open" aria-hidden>↗</span>
                  </button>
                </li>
              ))}
            </ol>
          </div>
        )}
      </CopilotChatAssistantMessage>
    );
  };
}
```

- [ ] **Step 2: Implement — ligar o slot**

Em `AssuranceConsole.tsx`, dentro do `CitationsProvider`, passar o slot ao `CopilotChat`:

```tsx
<CopilotChat
  agentId={activeAgentId}
  threadId={threadId}
  messageView={{ assistantMessage: makeAssistantMessage(domain.id) }}
/>
```

Confira a forma exata do slot em `CopilotChatProps` antes de commitar — se a prop de slot não for aninhada assim, o `npm run typecheck` acusa.

- [ ] **Step 3: Implement — traduções e estilo**

Em `messages/pt-BR.json`, no bloco `evidence`, adicionar `"openSource": "Abrir o documento"`. Em `messages/en.json`, `"openSource": "Open the document"`.

Em `apps/frontend/styles/globals.css`, depois do bloco `.citation-link` (~linha 676), acrescentar — os tokens abaixo são os que o arquivo já define:

```css
/* ---------- Evidência sob a resposta ---------- */
.msg-evidence {
  margin-top: var(--space-3);
  padding-top: var(--space-2);
  border-top: 1px solid var(--line);
}

.msg-evidence-title {
  font-size: var(--text-xs);
  color: var(--muted);
  margin-bottom: var(--space-2);
}

.msg-evidence-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.msg-evidence-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  text-align: left;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
}
.msg-evidence-item:hover { border-color: var(--accent); background: var(--accent-wash); }
.msg-evidence-item:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }

.cit-idx {
  flex: 0 0 auto;
  min-width: 1.25rem;
  height: 1.25rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  background: var(--accent);
  color: var(--accent-ink);
  font-size: var(--text-xs);
}

.cit-title {
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  word-break: break-all;
}

.cit-open { margin-left: auto; color: var(--muted); font-size: var(--text-xs); }

/* O marcador [n] DENTRO do texto. `display:inline` de propósito: ele vive no meio de um
   parágrafo, e qualquer coisa que gere caixa quebraria a linha no meio da frase. */
.cit-ref {
  display: inline;
  padding: 0 0.15em;
  border: 0;
  background: none;
  color: var(--accent);
  font-size: 0.85em;
  vertical-align: super;
  line-height: 1;
  cursor: pointer;
}
.cit-ref:hover { text-decoration: underline; }
.cit-ref:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; border-radius: 2px; }
```

- [ ] **Step 4: Verify**

```bash
cd apps/frontend && npm run typecheck && npm run lint && npm run check:i18n && npm run build
```
Expected: os quatro passam.

- [ ] **Step 5: Commit**

```bash
git add apps/frontend/components/console/MessageEvidence.tsx \
        apps/frontend/components/console/AssuranceConsole.tsx \
        apps/frontend/messages/ apps/frontend/app/globals.css
git commit -m "feat(frontend): evidência sob cada resposta, com [n] clicável"
```

---

### Task 6: visualizador do documento com o trecho destacado

**Files:**
- Create: `apps/frontend/components/console/SourceViewer.tsx`
- Create: `apps/frontend/app/api/source/[domain]/[name]/route.ts`
- Modify: `apps/frontend/components/console/AssuranceConsole.tsx`
- Modify: `apps/frontend/messages/pt-BR.json`, `apps/frontend/messages/en.json`

**Interfaces:**
- Consumes: o evento `"abrir-fonte"` da Task 5; a rota `GET /source/{domain}/{name}` da Task 3.
- Produces: nada consumido por tarefas posteriores (é a última).

**Contexto para quem implementa:** o proxy Next existe pelo mesmo motivo das outras rotas em `app/api/` — o token do usuário é anexado no servidor, não no browser. Copie o padrão de `app/api/foundry/knowledge/route.ts`.

O realce (Step 2b) é **melhor-esforço e roda sobre o DOM já renderizado**, nunca sobre o markdown: marcar antes de renderizar quebraria bloco de código, tabela e link, que é onde o trecho cai em documento técnico. O trecho vem do índice e o documento vem do blob, então eles divergem em espaço em branco — a comparação é feita em texto normalizado e encurta o alvo pelo fim até achar. Não achou ⇒ documento aberto sem realce, nunca falha a visualização.

- [ ] **Step 1: Implement — o proxy**

Criar `apps/frontend/app/api/source/[domain]/[name]/route.ts`:

```ts
// Repassa o documento citado, com o token do chamador.
//
// Mesmo desenho dos outros proxies em app/api/: o browser não fala com o backend direto
// (origem diferente) e o token nunca sai do fluxo Entra.
//
// 403 E 404 ATRAVESSAM INTACTOS, e isso importa: a tela precisa distinguir "você não tem
// acesso" de "não existe". Achatar os dois em 502 transformaria uma negativa de autorização
// — que é informação legítima para o usuário — em erro de infraestrutura.
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

function statusFor(backendStatus: number): number {
  if (backendStatus === 401 || backendStatus === 403) return backendStatus;
  if (backendStatus === 400) return 400;
  if (backendStatus === 404) return 404;
  return 502;
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ domain: string; name: string }> },
) {
  const { domain, name } = await params;
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(
      `${BACKEND}/source/${encodeURIComponent(domain)}/${encodeURIComponent(name)}`,
      { cache: "no-store", headers: auth ? { Authorization: auth } : undefined },
    );
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      return NextResponse.json(
        { error: body?.detail ?? `backend ${r.status}` },
        { status: statusFor(r.status) },
      );
    }
    return NextResponse.json(body);
  } catch {
    return NextResponse.json({ error: "backend inacessível" }, { status: 502 });
  }
}
```

- [ ] **Step 2: Implement — o visualizador**

Criar `apps/frontend/components/console/SourceViewer.tsx`:

```tsx
"use client";

// O documento INTEIRO que sustenta a citação — porque ver um nome de arquivo não confirma nada.
//
// O DESTAQUE É MELHOR-ESFORÇO, de propósito: o trecho vem do ÍNDICE e o documento vem do BLOB,
// então eles podem divergir por normalização de espaço em branco. Não achou ⇒ mostra o
// documento sem destaque. Falhar a visualização por causa do realce seria trocar a
// funcionalidade por um enfeite.
//
// Escuta um evento de `window` em vez de receber props: quem dispara é um botão dentro do
// renderizador de mensagem do CopilotKit, que não tem como alcançar este componente pela
// árvore de React. É o mesmo caminho que o MermaidZoom ao lado já usa.

import { CopilotChatAssistantMessage } from "@copilotkit/react-core/v2";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

interface Aberto {
  domainId: string;
  name: string;
  snippet?: string;
}

export function SourceViewer() {
  const te = useTranslations("evidence");
  const [aberto, setAberto] = useState<Aberto | null>(null);
  const [estado, setEstado] = useState<"carregando" | "ok" | "403" | "404" | "erro">("carregando");
  const [conteudo, setConteudo] = useState("");

  useEffect(() => {
    const ao = (e: Event) => setAberto((e as CustomEvent).detail as Aberto);
    window.addEventListener("abrir-fonte", ao);
    return () => window.removeEventListener("abrir-fonte", ao);
  }, []);

  useEffect(() => {
    if (!aberto) return;
    let cancelado = false;
    setEstado("carregando");
    setConteudo("");
    fetch(`/api/source/${encodeURIComponent(aberto.domainId)}/${encodeURIComponent(aberto.name)}`)
      .then(async (r) => {
        if (cancelado) return;
        if (r.status === 403) return setEstado("403");
        if (r.status === 404) return setEstado("404");
        if (!r.ok) return setEstado("erro");
        const body = await r.json();
        setConteudo(String(body?.content ?? ""));
        setEstado("ok");
      })
      .catch(() => !cancelado && setEstado("erro"));
    return () => {
      cancelado = true;
    };
  }, [aberto]);

  if (!aberto) return null;

  const mensagem =
    estado === "carregando" ? te("sourceLoading")
    : estado === "403" ? te("sourceForbidden")
    : estado === "404" ? te("sourceMissing")
    : estado === "erro" ? te("sourceError")
    : "";

  return (
    <div className="source-viewer" role="dialog" aria-label={aberto.name}>
      <div className="source-viewer-head">
        <span className="source-viewer-name">{aberto.name}</span>
        <button type="button" className="source-viewer-close" onClick={() => setAberto(null)}
                aria-label={te("sourceClose")}>
          ×
        </button>
      </div>
      <div className="source-viewer-body">
        {mensagem ? (
          <p className="muted">{mensagem}</p>
        ) : (
          <CopilotChatAssistantMessage.MarkdownRenderer content={conteudo} />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2b: Implement — o realce, sobre o DOM já renderizado**

**Por que sobre o DOM e não sobre o markdown.** Inserir `<mark>` no texto markdown antes de
renderizar quebra a sintaxe quando o trecho cai dentro de um bloco de código, de uma tabela ou
no meio de um link — e é exatamente em documento técnico que isso acontece. Marcar **depois**
de renderizar não pode quebrar sintaxe nenhuma, porque não há mais sintaxe: só nós de texto.

Acrescentar a `SourceViewer.tsx`:

```tsx
/** Envolve o trecho em <mark> DEPOIS da renderização, andando pelos nós de texto.
 *
 * Marcar o markdown ANTES de renderizar quebraria bloco de código, tabela e link — e é em
 * documento técnico que o trecho cai nesses lugares. Aqui não há sintaxe para quebrar.
 *
 * A comparação é feita em texto NORMALIZADO (espaço colapsado) porque o trecho vem do ÍNDICE
 * e o documento vem do BLOB: eles divergem em quebra de linha e indentação. O mapa `posicoes`
 * é o que traduz um índice do texto normalizado de volta para (nó, deslocamento) reais.
 */
function realcar(raiz: HTMLElement, trecho: string): boolean {
  const alvo = trecho.replace(/\s+/g, " ").trim();
  if (alvo.length < 24) return false;

  const nos: Text[] = [];
  const caminhador = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT);
  for (let n = caminhador.nextNode(); n; n = caminhador.nextNode()) nos.push(n as Text);

  // Texto normalizado + posição de cada caractere no nó de origem.
  let plano = "";
  const posicoes: Array<{ no: Text; off: number }> = [];
  let espacoPendente = false;
  for (const no of nos) {
    const bruto = no.data;
    for (let i = 0; i < bruto.length; i++) {
      if (/\s/.test(bruto[i])) {
        espacoPendente = plano.length > 0;
        continue;
      }
      if (espacoPendente) {
        plano += " ";
        posicoes.push({ no, off: i });
        espacoPendente = false;
      }
      plano += bruto[i];
      posicoes.push({ no, off: i });
    }
  }

  // O maior prefixo do trecho que exista no documento — divergências de normalização entre
  // índice e blob costumam ficar no FIM do trecho, então encurtar pelo fim é o que resolve.
  let inicio = -1;
  let usados = 0;
  for (let corte = alvo.length; corte >= 24; corte -= Math.max(8, Math.floor(corte / 8))) {
    inicio = plano.indexOf(alvo.slice(0, corte));
    if (inicio >= 0) {
      usados = corte;
      break;
    }
  }
  if (inicio < 0) return false;

  // Marca por NÓ: um Range que cruza fronteira de elemento não aceita surroundContents.
  const fim = inicio + usados - 1;
  const porNo = new Map<Text, { de: number; ate: number }>();
  for (let i = inicio; i <= fim && i < posicoes.length; i++) {
    const { no, off } = posicoes[i];
    const faixa = porNo.get(no);
    if (!faixa) porNo.set(no, { de: off, ate: off });
    else faixa.ate = off;
  }

  let primeira: HTMLElement | null = null;
  for (const [no, faixa] of porNo) {
    const range = document.createRange();
    range.setStart(no, faixa.de);
    range.setEnd(no, Math.min(faixa.ate + 1, no.data.length));
    const marca = document.createElement("mark");
    marca.className = "source-hit";
    try {
      range.surroundContents(marca);
    } catch {
      continue; // nó já alterado por uma marca anterior — segue para o próximo
    }
    if (!primeira) primeira = marca;
  }

  primeira?.scrollIntoView({ block: "center", behavior: "smooth" });
  return primeira !== null;
}
```

e ligá-lo depois da renderização, com um `ref` no corpo do visualizador:

```tsx
  const corpo = useRef<HTMLDivElement>(null);

  // Roda DEPOIS da pintura, porque precisa dos nós que o renderizador criou. Falhar em achar
  // o trecho é normal e silencioso: o documento continua aberto e navegável, que é o essencial.
  useEffect(() => {
    if (estado !== "ok" || !aberto?.snippet || !corpo.current) return;
    const id = requestAnimationFrame(() => {
      if (corpo.current) realcar(corpo.current, aberto.snippet as string);
    });
    return () => cancelAnimationFrame(id);
  }, [estado, conteudo, aberto]);
```

O `<div className="source-viewer-body">` passa a levar `ref={corpo}`.

Respeite `prefers-reduced-motion` no `scrollIntoView`: se a pessoa pediu menos movimento,
`behavior: "auto"` em vez de `"smooth"`.

- [ ] **Step 3: Implement — montar e traduzir**

Montar `<SourceViewer />` em `AssuranceConsole.tsx`, ao lado de `<MermaidZoom />`.

Em `messages/pt-BR.json`, bloco `evidence`:

```json
"sourceLoading": "Abrindo o documento…",
"sourceForbidden": "Você não tem acesso a este documento.",
"sourceMissing": "Documento não encontrado.",
"sourceError": "Não foi possível abrir o documento.",
"sourceClose": "Fechar"
```

Em `messages/en.json`, bloco `evidence`:

```json
"sourceLoading": "Opening the document…",
"sourceForbidden": "You do not have access to this document.",
"sourceMissing": "Document not found.",
"sourceError": "Could not open the document.",
"sourceClose": "Close"
```

E em `styles/globals.css`, junto do bloco de evidência da Task 5:

```css
/* ---------- Visualizador do documento citado ---------- */
.source-viewer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: min(48rem, 92vw);
  z-index: var(--z-modal, 60);
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-left: 1px solid var(--border);
  box-shadow: -8px 0 24px rgb(0 0 0 / 12%);
}

.source-viewer-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  border-bottom: 1px solid var(--line);
}

.source-viewer-name {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  word-break: break-all;
}

.source-viewer-close {
  margin-left: auto;
  border: 0;
  background: none;
  color: var(--muted);
  font-size: 1.25rem;
  line-height: 1;
  cursor: pointer;
}
.source-viewer-close:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

.source-viewer-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-3);
}

/* O trecho que o agente citou, dentro do documento. Fundo em vez de cor de texto: o realce
   pode cair em cima de código, link ou célula de tabela, que já têm cor própria. */
.source-hit {
  background: var(--accent-wash);
  border-bottom: 2px solid var(--accent);
  color: inherit;
  padding: 0 0.05em;
}

@media (prefers-reduced-motion: no-preference) {
  .source-viewer { animation: source-viewer-in 160ms ease-out; }
  @keyframes source-viewer-in { from { transform: translateX(1rem); opacity: 0; } }
}
```

Confira se `--z-modal` existe em `globals.css`; se não existir, use o valor da escala que o arquivo já adota em vez de inventar um número solto.

- [ ] **Step 4: Verify**

```bash
cd apps/frontend && npm run typecheck && npm run lint && npm run check:i18n && npm run build
```
Expected: os quatro passam.

- [ ] **Step 5: Verificação manual — é o único jeito de provar esta parte**

Suba backend e frontend, entre em `/d/selfwiki` e pergunte "Como funciona o mecanismo de assurance?". Confira:

1. A evidência aparece **sob a resposta**.
2. Faça a **segunda** pergunta: a evidência da primeira **continua lá** ao rolar para cima. *(É o ponto 1 do pedido original.)*
3. Clique num `[n]` do texto: abre o documento. *(Ponto 3.)*
4. O documento aparece **inteiro**, com o trecho **destacado** e a página já rolada até ele. *(Ponto 2.)*
   Teste também um trecho que caia dentro de bloco de código ou tabela — é onde o realce falharia se fosse feito no markdown.
5. Recarregue a página e reabra a conversa: a evidência **volta**.
6. Faça uma pergunta com tabela e diagrama ("qual a arquitetura?") e confirme que tabela e Mermaid **continuam renderizando** — é a regressão mais provável do `markdownRenderer`.
7. Em `/d/helpdesk`, confirme que a evidência também aparece sob a resposta (é o caminho de workflow, que liga por `message_id: None`).

- [ ] **Step 6: Commit**

```bash
git add apps/frontend/components/console/SourceViewer.tsx \
        apps/frontend/app/api/source/ apps/frontend/components/console/AssuranceConsole.tsx \
        apps/frontend/messages/
git commit -m "feat(frontend): visualizador do documento citado, com o trecho destacado"
```

---

## Gates finais antes do PR

```bash
cd apps/backend
uv run python -m eval.run_eval --self-test
uv run python -m eval.prompt_contract_test
uv run lint-imports --config importlinter.toml
uv run python -m tests.smoke.routes_snapshot_test
uv run python -m tests.architecture.module_graph_test
uv run python -m tests.architecture.filesystem_anchors_test
uv run python -m tests.grounded.citation_vocabulary_test
uv run python -m tests.helpdesk.sources_event_test
uv run python -m tests.audit.trail_test
cd ../frontend && npm run typecheck && npm run lint && npm run check:i18n && npm run build
```

## Fora do escopo — registrado para não se perder

- **Resposta gravada em duplicidade** no caminho grounded (mensagens 1 e 2 idênticas no blob `bb82ca58-…`, 19/ago). Bug real, separado.
- **`SYNTHESIS_DIRECTIVE` mora no Python** (`grounded.py:41`) e é ele que institui o contrato do `[n]` — tensão com a RULE #7, que manda prompt viver no documento AgentSchema.
- **O caminho canônico MCP não aplica ACL por usuário** — medido em 19/ago: o `headers` do `MCPTool` é ignorado, token inválido devolve os mesmos 38 documentos. É o que sustenta o `retrieval.py` não ser reimplementação de capacidade da plataforma.
