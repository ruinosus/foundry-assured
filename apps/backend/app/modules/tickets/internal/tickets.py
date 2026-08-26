"""A real (persisted) ticket tool — replaces the simulated ticket id.

`create_ticket` is a genuine action: it persists a ticket to data/tickets.jsonl
and returns it. In the live workflow it's gated behind human approval and invoked
by the EscalationExecutor. Tickets are viewable via the backend `GET /tickets` and
the frontend `/tickets` page.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import app as _app

#: A RAIZ DO BACKEND, não o pacote `app` — e a diferença é onde os chamados sobrevivem.
#:
#: `infra/containerapps.bicep` monta o Azure Files em **`/app/data`**. No container,
#: `WORKDIR /app` + `COPY app ./app` põem o pacote em `/app/app/`, então:
#:
#:     Path(app.__file__).parent        → /app/app        → /app/app/data   ✗ disco efêmero
#:     Path(app.__file__).parent.parent → /app            → /app/data       ✓ o mount
#:
#: Este caminho já errou DUAS vezes, das duas por contagem: primeiro `parents[3]` a partir do
#: arquivo (que apontou para `app/modules/data/` quando a ADR-017 moveu o arquivo), depois a
#: correção que ancorou no pacote `app` em vez da raiz — trocando um lugar errado por outro. A
#: regra 9 manda ancorar; ela não diz em quê, e ancorar no lugar errado erra igual.
#:
#: O gate `tests/architecture/filesystem_anchors_test.py` não pega isto: o caminho existe, só não
#: é o do mount. Quem prova é `tests/tickets/store_path_test.py`, que compara com o bicep.
_STORE = Path(_app.__file__).resolve().parent.parent / "data" / "tickets.jsonl"


def _new_id() -> str:
    return f"HD-{uuid.uuid4().hex[:6].upper()}"


def create_ticket(summary: str, severity: str = "medium", *, domain: str = "") -> dict:
    """Open a helpdesk ticket for an action the runbooks can't resolve.

    Args:
        summary: One-line description of what needs to happen.
        severity: low | medium | high.
        domain: which assistant opened it (helpdesk, oncall, …). Keyword-only DE PROPÓSITO:
            é atribuição, não conteúdo, e o modelo não deve poder escolhê-la — quem sabe o
            domínio é o código que chama, não quem escreve o texto do chamado.

    Returns the created ticket (id, summary, severity, status, created_at, domain).
    """
    ticket = {
        "id": _new_id(),
        "summary": summary.strip() or "Escalation requested",
        "severity": severity if severity in ("low", "medium", "high") else "medium",
        "status": "open",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        # Sem isto, o painel de ROI contava TODOS os chamados para TODOS os casos: três
        # chamados de plantão zeravam o resultado do helpdesk. Atribuir por heurística (adivinhar
        # pelo texto) daria um número que parece preciso e não é.
        "domain": domain,
    }
    linha = json.dumps(ticket) + "\n"
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    with _STORE.open("a", encoding="utf-8") as fh:
        # ── DOIS PROCESSOS, UM ARQUIVO ───────────────────────────────────────────────────────
        #
        # Desde que o servidor MCP passou a abrir chamado, o backend e ele fazem append no MESMO
        # `tickets.jsonl`, no MESMO share SMB (`infra/containerapps.bicep` monta o volume `data`
        # nos dois — em `/app/data` aqui e em `/srv/backend/data` lá, porque a raiz do backend
        # difere entre as duas imagens). `O_APPEND` é atômico em disco local; sobre CIFS o cliente
        # não promete isso, e duas escritas simultâneas podem entrelaçar e produzir uma linha
        # ilegível — que `list_tickets` derrubaria com `JSONDecodeError`.
        #
        # `flock` é o conserto barato: o cliente CIFS do Linux o traduz para lock de faixa de
        # bytes do SMB (Azure Files suporta), e o lock some sozinho quando o descritor fecha ou o
        # processo morre — nada de lock órfão travando a escrita depois de um scale-to-zero.
        # `suppress(OSError)` cobre o sistema de arquivos que não implementa `flock` (e o
        # Windows, que não tem `fcntl`): ali o comportamento volta a ser exatamente o de antes
        # desta linha, nunca pior.
        with contextlib.suppress(ImportError, OSError, AttributeError):
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.write(linha)

    # ── A ESCRITA VIRA EVENTO (ADR-023) ──────────────────────────────────────────────────────
    #
    # AQUI e não em cada aprovação, e o motivo é cobertura: existem QUATRO caminhos que abrem
    # chamado — a escalação do helpdesk (que passa por `hitl.decide`), a tool do `oncall`, a do
    # `deepcall` e a aprovação nativa do `platform`. Três deles passam por middleware de
    # framework, cada um com o seu jeito de entregar a decisão. Todos, sem exceção, passam por
    # ESTA função.
    #
    # Registrar no recurso em vez de em cada porta é o que faz a trilha não depender de alguém
    # lembrar de instrumentar a próxima porta. A decisão de quem aprovou continua sendo evento
    # separado onde conseguimos capturá-la; este evento responde a outra pergunta, que é "o que
    # foi efetivamente escrito".
    #
    # O RESUMO NÃO ENTRA: ele é texto do modelo e pode conter o que o usuário colou. Entram o id,
    # a severidade e o domínio — o suficiente para achar o chamado e nada além disso.
    #
    # E O DIGESTO DA LINHA, que fecha um buraco de não-repúdio: `hitl` grava QUAIS campos o
    # aprovador corrigiu, nunca os valores, e o texto final só existe em `tickets.jsonl` — que
    # não é encadeado por hash e mora num share gravável. Quem auditasse depois não tinha como
    # saber se o resumo do chamado ainda era o que foi aprovado. `content_sha256` é o sha256 da
    # LINHA exata que acabou de ser anexada: quem audita recalcula sobre a linha do arquivo e
    # compara com o valor que está na trilha imutável. Prova o conteúdo sem guardar o conteúdo.
    with contextlib.suppress(Exception):
        from app.modules.audit.public import actor, actor_detail, record

        record(
            scope="approvals",
            actor=actor(),
            kind="write",
            summary=f"chamado {ticket['id']} aberto",
            ref=ticket["id"],
            detail={
                "severity": ticket["severity"],
                "domain": domain,
                "content_sha256": hashlib.sha256(linha.encode("utf-8")).hexdigest(),
                **actor_detail(),
            },
        )
    return ticket


def list_tickets(limit: int = 50, domain: str = "") -> list[dict]:
    """Most-recent-first list of created tickets (for the /tickets view).

    Com `domain`, devolve só os daquele assistente. Chamado ANTIGO, gravado antes deste campo
    existir, fica de fora de uma consulta filtrada — e isso é deliberado: não sabemos de qual
    caso ele veio, e incluí-lo em todos inflaria a escalação de cada um deles.
    """
    if not _STORE.exists():
        return []
    rows = [
        json.loads(line)
        for line in _STORE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if domain:
        rows = [r for r in rows if r.get("domain") == domain]
    rows.reverse()
    return rows[:limit]
