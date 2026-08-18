"""A trilha de auditoria — encadeada por hash, append-only, verificável fora daqui.

A DIVISÃO DE TRABALHO (ADR-023): a **imutabilidade é do Azure**, o **evento é nosso**.

  Azure   política de retenção do container com `allowProtectedAppendWrites`: bloco novo pode
          ser anexado, bloco existente não pode ser alterado nem apagado. Com a política
          TRAVADA, nem quem tem RBAC do storage consegue — a recusa é da plataforma, não da
          nossa boa vontade. (Declarado em `infra/`, não aqui.)
  Nosso   o encadeamento por hash. Não é redundante com o WORM: o WORM protege o ARMAZENAMENTO,
          a cadeia protege o REGISTRO — e só a cadeia viaja. Um pacote exportado é verificável
          por quem não tem acesso nenhum à nossa conta de storage.

`hash = sha256(prev + payload canônico)`. `prev` do primeiro evento é `"genesis"`. Verificar é
reconstruir a cadeia e apontar o `seq` exato onde ela quebra — não "está íntegra ou não", mas
"quebrou aqui".

O QUE NUNCA ENTRA: conteúdo cru de conversa, argumento de tool com dado do usuário, segredo. O
evento diz O QUE aconteceu, QUEM fez e QUANDO, com referência ao recurso. Gravar o conteúdo
tornaria a trilha o maior repositório de dado sensível do produto — e imutável, o que é pior.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

CONTAINER = "audit"
GENESIS = "genesis"

#: Os tipos de evento. Fechado de propósito: um verbo livre transforma a trilha num log genérico,
#: e a pergunta "o que este sistema é capaz de registrar" deixa de ter resposta.
KINDS = (
    "approval",   # decisão humana num gate de escrita (RULE #5)
    "write",      # recurso criado ou alterado por ação de agente
    "redaction",  # dado pessoal barrado antes da gravação
    "access",     # leitura de recurso controlado por ACL
)

_SEGMENTO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class InvalidEvent(ValueError):
    """Evento que não pode entrar na trilha, com o motivo."""


@dataclass(frozen=True)
class Event:
    """Uma linha da trilha. Os campos são os do modelo que o Diligo usa, e não por imitação: são
    o mínimo que responde 'quem fez o quê, quando, e isto ainda é o que foi escrito?'."""

    seq: int
    at: str
    actor: str      # "human:<oid>" | "agent:<nome>" | "process:<nome>"
    kind: str
    summary: str
    ref: str = ""   # o recurso a que o evento se refere
    detail: dict = field(default_factory=dict)
    prev: str = GENESIS
    hash: str = ""


def _canonico(e: Event) -> str:
    """A carga que entra no hash. `sort_keys` porque ordem de dict não pode mudar o hash — dois
    processos com a mesma informação precisam produzir a mesma cadeia."""
    d = asdict(e)
    d.pop("hash", None)
    return json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def chain(e: Event) -> Event:
    """O evento com o hash calculado a partir do anterior."""
    from dataclasses import replace

    digest = hashlib.sha256((e.prev + _canonico(e)).encode("utf-8")).hexdigest()
    return replace(e, hash=digest)


def verify(eventos: list[dict]) -> dict:
    """Reconstrói a cadeia. Devolve `{ok, length, broken_at, reason}`.

    Aponta O ONDE, não só o se: numa trilha de mil eventos, "está quebrada" não é acionável e
    "quebrou no seq 412" é.
    """
    prev = GENESIS
    for i, bruto in enumerate(eventos):
        try:
            e = Event(**{k: v for k, v in bruto.items() if k in Event.__dataclass_fields__})
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "length": i, "broken_at": i, "reason": f"evento ilegível: {exc}"}
        if e.prev != prev:
            return {
                "ok": False, "length": i, "broken_at": e.seq,
                "reason": f"prev esperado {prev[:12]}…, veio {e.prev[:12]}…",
            }
        esperado = chain(e).hash
        if e.hash != esperado:
            return {
                "ok": False, "length": i, "broken_at": e.seq,
                "reason": "o hash não corresponde ao conteúdo — o evento foi alterado",
            }
        prev = e.hash
    return {"ok": True, "length": len(eventos), "broken_at": None, "reason": ""}


def actor() -> str:
    """O ator da requisição atual: `human:<e-mail>` quando há, senão `human:<oid>`.

    A PREFERÊNCIA VEM DO DNA-CLOUD, que já resolveu isto: e-mail → oid → sub. O e-mail é legível
    e dispensa consultar diretório na hora de auditar; o oid é durável e sobrevive a troca de
    e-mail. Guardar SÓ o oid transforma toda leitura de trilha numa consulta ao Entra; guardar só
    o e-mail perde a identidade quando ele muda.

    Por isso os DOIS vão: o e-mail no `actor` (que é o que a tela mostra) e o oid no detalhe do
    evento (que é o que resolve quem é, para sempre).
    """
    from app.shared.auth import current_user

    user = current_user()
    if user is None:
        return "process:app"
    email = (getattr(user, "email", "") or getattr(user, "preferred_username", "") or "").strip()
    if email:
        return f"human:{email}"
    return f"human:{user.oid}" if user.oid else "human:dev-local"


def actor_detail() -> dict:
    """O oid junto do e-mail — a identidade durável ao lado da legível."""
    from app.shared.auth import current_user

    user = current_user()
    if user is None:
        return {}
    saida = {}
    if user.oid:
        saida["oid"] = user.oid
    email = (getattr(user, "email", "") or getattr(user, "preferred_username", "") or "").strip()
    if email:
        saida["email"] = email
    return saida


def _seguro(parte: str, campo: str) -> str:
    if not _SEGMENTO.match(parte or ""):
        raise InvalidEvent(f"{campo} inválido para a trilha: {parte!r}")
    return parte


def _agora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class InMemoryTrail:
    """Fake de dev/CI. Existe para o backend subir sem Azure — nunca em produção."""

    def __init__(self) -> None:
        self._por_escopo: dict[str, list[dict]] = {}

    def append(self, scope: str, actor: str, kind: str, summary: str, ref: str = "", detail: dict | None = None) -> dict:
        linhas = self._por_escopo.setdefault(_seguro(scope, "escopo"), [])
        e = chain(
            Event(
                seq=len(linhas) + 1, at=_agora(), actor=actor, kind=kind,
                summary=summary, ref=ref, detail=detail or {},
                prev=linhas[-1]["hash"] if linhas else GENESIS,
            )
        )
        linhas.append(asdict(e))
        return asdict(e)

    def read(self, scope: str) -> list[dict]:
        return list(self._por_escopo.get(_seguro(scope, "escopo"), []))


class BlobTrail:
    """Append blob por escopo, no Storage do tenant. Sem chave: `DefaultAzureCredential`."""

    def __init__(self, account: str, credential) -> None:
        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import BlobServiceClient

        svc = BlobServiceClient(
            account_url=f"https://{account}.blob.core.windows.net", credential=credential
        )
        self._container = svc.get_container_client(CONTAINER)
        with contextlib.suppress(ResourceExistsError):
            self._container.create_container()

    def _blob(self, scope: str):
        return self._container.get_blob_client(f"{_seguro(scope, 'escopo')}.jsonl")

    def read(self, scope: str) -> list[dict]:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            bruto = self._blob(scope).download_blob().readall().decode("utf-8")
        except ResourceNotFoundError:
            return []
        saida = []
        for linha in bruto.splitlines():
            if linha.strip():
                with contextlib.suppress(Exception):
                    saida.append(json.loads(linha))
        return saida

    def append(self, scope: str, actor: str, kind: str, summary: str, ref: str = "", detail: dict | None = None) -> dict:
        from azure.core import MatchConditions
        from azure.core.exceptions import ResourceExistsError, ResourceModifiedError

        blob = self._blob(scope)
        # `IfMissing` SOZINHO — `create_append_blob()` sem condição SOBRESCREVE, e num arquivo de
        # auditoria isso seria apagar a trilha ao gravar o próximo evento. (Verificado contra o
        # serviço quando o store de conversas teve exatamente esse defeito.)
        with contextlib.suppress(ResourceExistsError, ResourceModifiedError):
            blob.create_append_blob(match_condition=MatchConditions.IfMissing)

        # A leitura antes do append é o que dá `seq` e `prev`. Numa corrida, dois eventos podem
        # ler o mesmo topo — e a VERIFICAÇÃO detecta, que é o ponto: a trilha não promete
        # serialização perfeita, promete que adulteração e desordem são detectáveis.
        anteriores = self.read(scope)
        e = chain(
            Event(
                seq=len(anteriores) + 1, at=_agora(), actor=actor, kind=kind,
                summary=summary, ref=ref, detail=detail or {},
                prev=anteriores[-1]["hash"] if anteriores else GENESIS,
            )
        )
        blob.append_block((json.dumps(asdict(e), ensure_ascii=False) + "\n").encode("utf-8"))
        return asdict(e)


_TRILHAS: dict[str, object] = {}


def trail():
    """A trilha do tenant atual. Cache POR CONTA, nunca global — global entregaria a trilha de um
    cliente para outro no modo `shared`."""
    import logging

    from app.modules.tenancy.public import tenant_config

    conta = (tenant_config().azure_storage_account or "").strip()
    chave = conta or "«memória»"
    if chave in _TRILHAS:
        return _TRILHAS[chave]

    if not conta:
        logging.getLogger(__name__).warning(
            "Sem AZURE_STORAGE_ACCOUNT — a trilha de auditoria fica APENAS em memória e some no "
            "restart. Isto não é auditoria; é o modo local."
        )
        _TRILHAS[chave] = InMemoryTrail()
        return _TRILHAS[chave]

    from azure.identity import DefaultAzureCredential

    _TRILHAS[chave] = BlobTrail(conta, DefaultAzureCredential())
    return _TRILHAS[chave]
