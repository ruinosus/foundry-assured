"""O marcador de compartilhamento — quem pode ler a conversa de outra pessoa.

POR QUE UM ÍNDICE SEPARADO, e não só metadata na própria conversa. Quem abre um link
compartilhado tem só o `conversation_id` — não sabe QUEM é o dono, e o caminho do blob da
conversa começa pelo object-id do dono (`{usuário}/{agente}/{conversa}.jsonl`, ver store.py).
Sem saber o dono, achar a conversa exigiria varrer o container inteiro procurando o id certo —
exatamente o que o pedido pede para NÃO fazer. Este índice resolve o inverso: `conversation_id`
→ dono + agente, um blob get, O(1), sem tocar em ninguém que não seja aquela conversa.

CAMINHO EXPLÍCITO E SEPARADO (o requisito central do pedido). A leitura de um terceiro nunca
passa por `find_conversation`/`get_conversation` (que filtram pelo usuário autenticado, e
continuam intocados) — passa por `read_shared_conversation()` em `listing.py`, que consulta ESTE
índice. Autorização aqui é o link em si — qualquer autenticado com o `conversation_id` lê, sem
lista de destinatários (decisão do produto) — mas o link só funciona enquanto o dono mantiver o
registro aqui; apagá-lo (revogar) é o que faz o link parar de funcionar.

O que este índice NUNCA guarda: conteúdo de mensagem, citação, documento. Só a ligação
`conversation_id → (owner, agent)` e quando ela nasceu — o suficiente para achar o blob da
conversa real, nada além disso.
"""

from __future__ import annotations

import contextlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime

SHARE_CONTAINER = "conversations-shared"

#: Mesmo formato de segmento aceito pelo store de conversas (store.py `_SEGMENTO`) — duplicado em
#: vez de importado porque é um detalhe de VALIDAÇÃO deste arquivo, não uma dependência do store.
_SEGMENTO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class InvalidShareKey(ValueError):
    """Identificador que não pode virar caminho — pego antes de tocar no storage."""


def _seguro(parte: str) -> str:
    if not _SEGMENTO.match(parte or ""):
        raise InvalidShareKey(f"conversation_id inválido para uso como caminho: {parte!r}")
    return parte


@dataclass(frozen=True)
class ShareRecord:
    conversation_id: str
    owner: str
    agent: str
    shared_at: str


def _agora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class InMemoryShareIndex:
    """Fake de dev/CI. Existe para o backend subir sem Azure — nunca em produção."""

    def __init__(self) -> None:
        self._registros: dict[str, dict] = {}

    def set(self, conversation_id: str, owner: str, agent: str) -> None:
        chave = _seguro(conversation_id)
        self._registros[chave] = {
            "conversation_id": chave,
            "owner": owner,
            "agent": agent,
            "shared_at": _agora(),
        }

    def get(self, conversation_id: str) -> ShareRecord | None:
        bruto = self._registros.get(_seguro(conversation_id))
        return ShareRecord(**bruto) if bruto else None

    def clear(self, conversation_id: str) -> None:
        self._registros.pop(_seguro(conversation_id), None)


class BlobShareIndex:
    """Um blob por conversa compartilhada, no container `conversations-shared`.

    Blob comum (não append): o registro é substituído por inteiro a cada `set()` — não há
    histórico a acumular, só "compartilhada agora, ou não". `DefaultAzureCredential`, sem chave
    (regra 2).
    """

    def __init__(self, account: str, credential) -> None:
        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import BlobServiceClient

        svc = BlobServiceClient(
            account_url=f"https://{account}.blob.core.windows.net", credential=credential
        )
        self._container = svc.get_container_client(SHARE_CONTAINER)
        with contextlib.suppress(ResourceExistsError):
            self._container.create_container()

    def _blob(self, conversation_id: str):
        return self._container.get_blob_client(f"{_seguro(conversation_id)}.json")

    def set(self, conversation_id: str, owner: str, agent: str) -> None:
        registro = {
            "conversation_id": conversation_id,
            "owner": owner,
            "agent": agent,
            "shared_at": _agora(),
        }
        self._blob(conversation_id).upload_blob(
            json.dumps(registro, ensure_ascii=False).encode("utf-8"), overwrite=True
        )

    def get(self, conversation_id: str) -> ShareRecord | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            bruto = self._blob(conversation_id).download_blob().readall()
        except ResourceNotFoundError:
            return None
        with contextlib.suppress(Exception):
            campos = json.loads(bruto.decode("utf-8"))
            return ShareRecord(
                conversation_id=campos["conversation_id"],
                owner=campos["owner"],
                agent=campos["agent"],
                shared_at=campos.get("shared_at", ""),
            )
        return None

    def clear(self, conversation_id: str) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        with contextlib.suppress(ResourceNotFoundError):
            self._blob(conversation_id).delete_blob()


#: Cache POR CONTA, nunca global — mesmo motivo do `_STORES` em store.py: no modo `shared` a
#: conta vem do tenant da requisição, e um cache global vazaria o índice de um tenant para outro.
_INDICES: dict[str, object] = {}


def share_index():
    """O índice de compartilhamento do tenant atual. Blob quando há conta; in-memory quando não."""
    import logging

    from app.modules.tenancy.public import tenant_config

    conta = (tenant_config().azure_storage_account or "").strip()
    chave = conta or "«memória»"
    if chave in _INDICES:
        return _INDICES[chave]

    if not conta:
        logging.getLogger(__name__).warning(
            "Sem AZURE_STORAGE_ACCOUNT — o índice de compartilhamento fica em memória e some "
            "no restart."
        )
        _INDICES[chave] = InMemoryShareIndex()
        return _INDICES[chave]

    from azure.identity import DefaultAzureCredential

    _INDICES[chave] = BlobShareIndex(conta, DefaultAzureCredential())
    return _INDICES[chave]
