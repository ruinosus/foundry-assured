"""Onde uma conversa fica depois que a aba fecha.

O QUE FALTAVA, medido antes de escrever isto: os 10 agentes publicados somavam **zero** sessões
no Foundry, e o motivo está no nosso próprio código — `grounded/internal/per_request.py` diz
`use_service_session=False`, então `create_session`/`get_session` existem só para satisfazer o
protocolo e nunca são chamados. O runtime executa aqui. Nada persistia transcrição: a memória do
Foundry guarda fatos extraídos (preferências, resoluções), não a conversa, e o frontend só guarda
tema e idioma. O `thread_id` era `uuid4()` novo a cada request.

Consequência que ninguém via: o painel de ROI contava conversas por `list_sessions`, que devolvia
zero sempre — logo `resolvidos = 0` e a economia estimada era R$ 0,00 em qualquer cenário.

POR QUE BLOB DE APÊNDICE, e não tabela. Histórico é append-only, que é exatamente o que um
`AppendBlobClient` faz — apêndice atômico, sem ler-modificar-escrever, sem corrida entre dois
turnos da mesma conversa. Tabela imporia o teto de 64KB por propriedade, e uma resposta longa com
citações passa disso; partir a mensagem em linhas resolveria o teto criando um problema pior
(remontagem). E o prefixo do nome do blob dá a listagem por usuário e por agente de graça:

    conversations/{usuário}/{agente}/{conversa}.jsonl

Uma linha JSON por mensagem, no formato do próprio framework (`Message.to_dict()`), para o que
volta ser a mensagem que saiu — não uma projeção nossa que perde papel, anexo ou tool call.

PRIVACIDADE. O conteúdo é do usuário: o container é privado, o acesso é por
`DefaultAzureCredential` (nunca chave), e o object-id do usuário é segmento do caminho — validado
em `_seguro()`, porque um segmento com `..` deixaria uma conversa cair na pasta de outro.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote, unquote

CONTAINER = "conversations"

#: Segmento de caminho aceitável. Object-id do Entra é GUID e passa; o resto é recusado em vez de
#: saneado, porque "sanear" um identificador produziria dois usuários com o mesmo caminho.
_SEGMENTO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class InvalidKey(ValueError):
    """Identificador que não pode virar caminho — pego antes de tocar no storage."""


def _seguro(parte: str, campo: str) -> str:
    if not _SEGMENTO.match(parte or ""):
        raise InvalidKey(f"{campo} inválido para uso como caminho: {parte!r}")
    return parte


@dataclass(frozen=True)
class ConversationMeta:
    """O suficiente para montar a lista lateral, sem abrir nenhuma conversa."""

    id: str
    agent: str
    title: str
    updated_at: str
    messages: int
    #: A sessão do Foundry equivalente, quando o agente executa LÁ. Vazio quando executa aqui —
    #: e é assim que a listagem consegue juntar as duas origens sem inventar uma delas.
    foundry_session_id: str = ""


def _blob_name(user: str, agent: str, conv: str) -> str:
    return f"{_seguro(user, 'usuário')}/{_seguro(agent, 'agente')}/{_seguro(conv, 'conversa')}.jsonl"


def _agora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class InMemoryConversationStore:
    """Fake de dev/CI. Existe para o backend subir sem Azure — nunca em produção."""

    def __init__(self) -> None:
        self._linhas: dict[str, list[dict]] = {}
        self._meta: dict[str, dict] = {}

    def append(self, user: str, agent: str, conv: str, messages: list[dict]) -> None:
        chave = _blob_name(user, agent, conv)
        messages, _ = sanitize(messages)
        self._linhas.setdefault(chave, []).extend(messages)
        meta = self._meta.setdefault(chave, {"title": "", "created_at": _agora()})
        meta["updated_at"] = _agora()
        if not meta["title"]:
            meta["title"] = _titulo(messages)

    def read(self, user: str, agent: str, conv: str) -> list[dict]:
        return list(self._linhas.get(_blob_name(user, agent, conv), []))

    def add_usage(
        self, user: str, agent: str, conv: str, incoming: int, outgoing: int, references: int = 0
    ) -> None:
        meta = self._meta.setdefault(_blob_name(user, agent, conv), {})
        meta["in_tokens"] = int(meta.get("in_tokens", 0)) + max(incoming, 0)
        meta["out_tokens"] = int(meta.get("out_tokens", 0)) + max(outgoing, 0)
        meta["refs"] = int(meta.get("refs", 0)) + max(references, 0)

    def totals(self, agent: str = "") -> dict:
        conversas = incoming = outgoing = refs = com_refs = 0
        for chave, meta in self._meta.items():
            if agent and chave.split("/")[1] != agent:
                continue
            conversas += 1
            incoming += int(meta.get("in_tokens", 0))
            outgoing += int(meta.get("out_tokens", 0))
            n = int(meta.get("refs", 0))
            refs += n
            com_refs += 1 if n else 0
        return {
            "conversations": conversas,
            "input_tokens": incoming,
            "output_tokens": outgoing,
            "references": refs,
            "conversations_with_references": com_refs,
        }

    def list(self, user: str, agent: str = "") -> list[ConversationMeta]:
        prefixo = f"{_seguro(user, 'usuário')}/" + (f"{_seguro(agent, 'agente')}/" if agent else "")
        saida = []
        for chave, linhas in self._linhas.items():
            if not chave.startswith(prefixo):
                continue
            _, ag, arquivo = chave.split("/", 2)
            m = self._meta.get(chave, {})
            saida.append(
                ConversationMeta(
                    id=arquivo.removesuffix(".jsonl"),
                    agent=ag,
                    title=m.get("title", ""),
                    updated_at=m.get("updated_at", ""),
                    messages=len(linhas),
                )
            )
        return sorted(saida, key=lambda c: c.updated_at, reverse=True)


def sanitize(messages: list[dict]) -> tuple[list[dict], list[str]]:
    """Saneia as mensagens ANTES de gravar. É o ponto único de escrita da ADR-023.

    POR QUE AQUI e não no chamador: existem dois caminhos que gravam conversa (o
    `HistoryProvider` do agent-framework e o `record_turn` do grounded), e um saneamento que
    depende de cada chamador lembrar de chamá-lo é decoração. Aqui os dois passam por cima
    obrigatoriamente, porque `append` é a única porta.

    POR QUE ANTES e não numa faxina depois: uma passada de limpeza sobre o que já foi gravado
    significa que o valor cru existiu num blob — e, com a política de retenção travada, existiria
    para sempre. Redigir depois é redigir uma cópia.

    Devolve `(mensagens saneadas, tipos encontrados)`. Os TIPOS sobem para o chamador registrar na
    trilha; o conteúdo, não.
    """
    from app.modules.audit.public import redact

    achados: list[str] = []
    saidas: list[dict] = []
    for m in messages:
        copia = dict(m)
        for campo in ("text",):
            if isinstance(copia.get(campo), str):
                copia[campo], tipos = redact(copia[campo])
                achados.extend(t for t in tipos if t not in achados)
        # O formato do agent-framework guarda o texto em `contents[].text`.
        partes = copia.get("contents")
        if isinstance(partes, list):
            novas = []
            for parte in partes:
                if isinstance(parte, dict) and isinstance(parte.get("text"), str):
                    parte = dict(parte)
                    parte["text"], tipos = redact(parte["text"])
                    achados.extend(t for t in tipos if t not in achados)
                novas.append(parte)
            copia["contents"] = novas
        saidas.append(copia)
    return saidas, achados


def _titulo(messages: list[dict]) -> str:
    """A primeira fala do usuário, cortada — é o que a lista mostra.

    Sem isto a lista seria uma coluna de GUIDs, e ninguém reconhece a própria conversa por GUID.
    """
    for m in messages:
        if (m.get("role") or "").lower() != "user":
            continue
        texto = m.get("text") or ""
        if not texto:
            for parte in m.get("contents") or []:
                if isinstance(parte, dict) and parte.get("text"):
                    texto = parte["text"]
                    break
        texto = " ".join(str(texto).split())
        if texto:
            return texto[:120]
    return ""


class BlobConversationStore:
    """Append blobs no Storage do tenant. Sem chave: `DefaultAzureCredential` (regra 2)."""

    def __init__(self, account: str, credential) -> None:
        from azure.storage.blob import BlobServiceClient

        self._svc = BlobServiceClient(
            account_url=f"https://{account}.blob.core.windows.net", credential=credential
        )
        self._container = self._svc.get_container_client(CONTAINER)
        # O container precisa existir ANTES do primeiro append — criar sob demanda no append
        # esconderia um 404 de permissão atrás de um erro de escrita.
        from azure.core.exceptions import ResourceExistsError

        try:
            self._container.create_container()
        except ResourceExistsError:
            pass

    def append(self, user: str, agent: str, conv: str, messages: list[dict]) -> None:
        if not messages:
            return
        messages, achados = sanitize(messages)
        if achados:
            # O que foi barrado vira EVENTO, não silêncio: uma redação invisível faz o operador
            # concluir que ninguém nunca colou documento no chat. Só os TIPOS entram — pôr o
            # valor na trilha trocaria um vazamento por um vazamento imutável.
            with _silencio():
                from app.modules.audit.public import record

                record(
                    scope="redactions",
                    actor=f"human:{user}",
                    kind="redaction",
                    summary=f"{len(achados)} tipo(s) de dado pessoal barrados antes de gravar",
                    ref=f"{agent}/{conv}",
                    detail={"types": achados},
                )
        blob = self._container.get_blob_client(_blob_name(user, agent, conv))
        from azure.core import MatchConditions
        from azure.core.exceptions import ResourceExistsError, ResourceModifiedError

        # `create_append_blob()` SEM condição SOBRESCREVE um blob que já existe — não levanta
        # ResourceExistsError, como eu havia assumido. O efeito era o pior possível: cada turno
        # zerava a conversa, e a leitura devolvia só o último turno. Um teste pegou; nenhum erro
        # aparecia.
        #
        # `MatchConditions.IfMissing` SOZINHO é a forma correta — vira `If-None-Match: *` e o
        # serviço recusa quando o blob já está lá. Passar `etag="*"` junto (que a docstring do
        # SDK sugere) faz o kwarg vazar até o transporte: `Session.request() got an unexpected
        # keyword argument 'etag'`. Verificado nas duas formas contra o serviço.
        primeira = False
        try:
            blob.create_append_blob(match_condition=MatchConditions.IfMissing)
            primeira = True
        except (ResourceExistsError, ResourceModifiedError):
            pass

        corpo = "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in messages)
        blob.append_block(corpo.encode("utf-8"))

        # O título só é escrito UMA vez, na criação: reescrevê-lo a cada turno faria a lista
        # renomear conversas sozinha. `quote` porque metadata de blob é cabeçalho HTTP e não
        # aceita acento — sem isso, a primeira pergunta em português quebraria a gravação.
        atual = {"updated_at": _agora()}
        if primeira:
            atual["title"] = quote(_titulo(messages)[:120])
        else:
            with _silencio():
                atual["title"] = blob.get_blob_properties().metadata.get("title", "")
        blob.set_blob_metadata({k: v for k, v in atual.items() if v})

    def add_usage(
        self, user: str, agent: str, conv: str, incoming: int, outgoing: int, references: int = 0
    ) -> None:
        """Soma tokens e REFERÊNCIAS de conhecimento à conversa. No METADATA do blob, não no corpo.

        Assim o total de uma conversa é lido no `list_blobs` junto com o resto — o painel de ROI
        soma o custo de mil conversas sem abrir nenhuma, e sem ler o conteúdo de ninguém.

        `refs` existe porque é o INSUMO PRINCIPAL da fórmula Agent Assisted Hours da Microsoft:
        cada referência de conhecimento citada conta uma vez e vale o multiplicador de tempo. O
        detector de citação do `eval/assertions.py` responde "citou ou não" — booleano, que serve
        de gate e não serve de conta. A contagem tem que ser gravada quando o número está em mãos,
        e o único lugar onde ele está é o fim do stream, aqui.
        """
        if incoming <= 0 and outgoing <= 0 and references <= 0:
            return
        blob = self._container.get_blob_client(_blob_name(user, agent, conv))
        with _silencio():
            atual = blob.get_blob_properties().metadata or {}
            atual["in_tokens"] = str(int(atual.get("in_tokens", 0) or 0) + max(incoming, 0))
            atual["out_tokens"] = str(int(atual.get("out_tokens", 0) or 0) + max(outgoing, 0))
            atual["refs"] = str(int(atual.get("refs", 0) or 0) + max(references, 0))
            blob.set_blob_metadata(atual)

    def totals(self, agent: str = "") -> dict:
        """Agregado de TODOS os usuários: conversas e tokens. Para o painel de ROI.

        Varre a lista de blobs porque o agente é o SEGUNDO segmento do caminho — o layout é
        `{usuário}/{agente}/…`, otimizado para a listagem interativa (as minhas conversas), que
        precisa ser rápida. O agregado é de painel administrativo e pode varrer.

        Lê só METADATA: nomes, contagens e tokens. Nenhum conteúdo de conversa é aberto aqui.
        """
        conversas = incoming = outgoing = refs = com_refs = 0
        for b in self._container.list_blobs(include=["metadata"]):
            partes = b.name.split("/")
            if len(partes) != 3 or (agent and partes[1] != agent):
                continue
            conversas += 1
            meta = b.metadata or {}
            incoming += int(meta.get("in_tokens", 0) or 0)
            outgoing += int(meta.get("out_tokens", 0) or 0)
            # `refs` ausente é conversa gravada ANTES deste campo existir, e some do numerador
            # sem sumir do denominador. Quem soma isto tem de saber: ver `references_partial`
            # em `usecases/internal/outcomes.py`.
            n = int(meta.get("refs", 0) or 0)
            refs += n
            com_refs += 1 if n else 0
        return {
            "conversations": conversas,
            "input_tokens": incoming,
            "output_tokens": outgoing,
            "references": refs,
            "conversations_with_references": com_refs,
        }

    def read(self, user: str, agent: str, conv: str) -> list[dict]:
        from azure.core.exceptions import ResourceNotFoundError

        blob = self._container.get_blob_client(_blob_name(user, agent, conv))
        try:
            bruto = blob.download_blob().readall().decode("utf-8")
        except ResourceNotFoundError:
            return []
        saida = []
        for linha in bruto.splitlines():
            if not linha.strip():
                continue
            # Uma linha corrompida não derruba a conversa inteira — o resto do histórico ainda
            # é útil, e perder tudo por causa de um turno seria pior.
            with _silencio():
                saida.append(json.loads(linha))
        return saida

    def list(self, user: str, agent: str = "") -> list[ConversationMeta]:
        prefixo = f"{_seguro(user, 'usuário')}/" + (f"{_seguro(agent, 'agente')}/" if agent else "")
        saida = []
        for b in self._container.list_blobs(name_starts_with=prefixo, include=["metadata"]):
            partes = b.name.split("/")
            if len(partes) != 3:
                continue
            meta = b.metadata or {}
            saida.append(
                ConversationMeta(
                    id=partes[2].removesuffix(".jsonl"),
                    agent=partes[1],
                    title=unquote(meta.get("title", "")),
                    updated_at=meta.get("updated_at", "")
                    or (b.last_modified.isoformat() if b.last_modified else ""),
                    messages=0,  # contar exigiria abrir cada blob; a lista não precisa disso
                )
            )
        return sorted(saida, key=lambda c: c.updated_at, reverse=True)


def _silencio():
    import contextlib

    return contextlib.suppress(Exception)


#: Cache POR CONTA, nunca global.
#:
#: Um cache global seria um vazamento entre tenants: no modo `shared` a conta de storage vem de
#: `tenant_config()`, que é por request, e guardar o primeiro store construído entregaria as
#: conversas do tenant A para o tenant B — sem erro nenhum aparecer. A chave é a conta
#: justamente porque é ela que muda entre tenants.
_STORES: dict[str, object] = {}


def store():
    """O store do tenant atual. Blob quando há conta de storage; in-memory quando não há.

    A ausência de conta é registrada em log: cair no fake em produção significa perder conversa,
    e isso não pode acontecer em silêncio.
    """
    import logging

    from app.modules.tenancy.public import tenant_config

    conta = (tenant_config().azure_storage_account or "").strip()
    chave = conta or "«memória»"
    if chave in _STORES:
        return _STORES[chave]

    if not conta:
        logging.getLogger(__name__).warning(
            "Sem AZURE_STORAGE_ACCOUNT — conversas ficam APENAS em memória e somem no restart."
        )
        _STORES[chave] = InMemoryConversationStore()
        return _STORES[chave]

    from azure.identity import DefaultAzureCredential

    _STORES[chave] = BlobConversationStore(conta, DefaultAzureCredential())
    return _STORES[chave]


def conversation_user() -> str:
    """O segmento de caminho do usuário — o object-id do Entra.

    Sem prefixo de tenant DE PROPÓSITO: no modo `shared` a conta de storage já vem do
    `tenant_config()` do tenant, então o isolamento é a própria conta e um prefixo aqui só
    repetiria a informação. Isto é o oposto de `memory_scope()`, que precisa do prefixo porque
    todos os tenants dividem o mesmo memory store.
    """
    from app.shared.auth import current_user

    user = current_user()
    return (user.oid if user is not None and user.oid else "") or "dev-local"
