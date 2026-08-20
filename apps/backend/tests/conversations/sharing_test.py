"""Compartilhar uma conversa é um caminho EXPLÍCITO e SEPARADO do filtro por dono — nunca uma
relaxação dele.

    uv run python -m tests.conversations.sharing_test

O QUE ESTE TESTE TRAVA, e por que cada ponto importa:

  1. conversa NÃO compartilhada continua ilegível para outro usuário — é o não-regressão: se
     algum dia `read_shared_conversation` passasse a devolver algo sem um registro de
     compartilhamento, este é o primeiro lugar que acusaria.
  2. conversa compartilhada é legível por outro usuário autenticado — e SÓ depois de
     `share_conversation`, nunca antes.
  3. a leitura por terceiro NÃO devolve conteúdo de documento — só o que a conversa já tinha
     gravado (nome/url/trecho da citação). Quem lê pelo link ainda precisa passar por `/source`
     (fora deste módulo) para o documento em si, reautorizado com a PRÓPRIA identidade.
  4. revogar volta ao estado 1 — e só o dono revoga; outro usuário não consegue.
  5. cada transição (compartilhar, revogar, ler por terceiro) grava o evento certo na trilha —
     `write`/`approvals` para as duas primeiras, `access`/`access` para a leitura, os mesmos
     tipos que `/source` e a abertura de chamado já usam (`internal/trail.py` KINDS).

Roda offline, sobre os fakes em memória do próprio módulo (`InMemoryConversationStore`,
`InMemoryShareIndex`, `InMemoryTrail`) — o que está sendo travado é o CONTRATO de posse e
compartilhamento, não o SDK do Azure.

PROVA POR MUTAÇÃO (rodada manualmente ao implementar, documentada no relatório): comentar a
checagem `registro.owner != user_id` em `unshare_conversation` faz "outro usuário não revoga o
que não é dele" falhar; restaurá-la faz voltar a passar. Da mesma forma, comentar a checagem
`not store().read(...)` em `share_conversation` faz "outro usuário não compartilha o que não é
dele" falhar.
"""

from __future__ import annotations

import sys

from app.modules.audit.internal.trail import InMemoryTrail
from app.modules.conversations.internal import listing
from app.modules.conversations.internal.sharing import InMemoryShareIndex
from app.modules.conversations.internal.store import InMemoryConversationStore

failures: list[str] = []


def check(nome: str, condicao: bool) -> None:
    marca = "✓" if condicao else "✗"
    print(f"  {marca} {nome}")
    if not condicao:
        failures.append(nome)


def main() -> int:
    print("conversas — compartilhamento é caminho explícito e separado\n")

    store_fake = InMemoryConversationStore()
    indice_fake = InMemoryShareIndex()
    trilha_fake = InMemoryTrail()

    store_original = listing.store
    indice_original = listing.share_index
    listing.store = lambda: store_fake
    listing.share_index = lambda: indice_fake

    import app.modules.audit.public as audit_public

    trail_original = audit_public.trail
    audit_public.trail = lambda: trilha_fake

    try:
        store_fake.append("alice", "helpdesk", "conv-1", [{"role": "user", "text": "oi"}])
        store_fake.append(
            "alice",
            "helpdesk",
            "conv-2",
            [
                {"role": "user", "text": "qual doc fundamenta isso?"},
                {
                    "role": "assistant",
                    "text": "resposta [1]",
                    "annotations": [
                        {"type": "citation", "title": "doc.md", "url": "https://x/doc.md", "index": 1}
                    ],
                },
            ],
        )

        # ── 1. NÃO compartilhada é ilegível para outro usuário (não-regressão) ────────────
        check(
            "find_conversation (dono) continua enxergando a própria conversa",
            bool(listing.find_conversation("alice", "conv-1")),
        )
        check(
            "find_conversation (outro usuário) não vê a conversa de alice",
            listing.find_conversation("bob", "conv-1") == {},
        )
        check(
            "read_shared_conversation devolve vazio ANTES de qualquer compartilhamento",
            listing.read_shared_conversation("conv-1") == {},
        )
        check(
            "só o dono pode ligar o compartilhamento",
            listing.share_conversation("bob", "helpdesk", "conv-1") is False,
        )

        # ── 2. compartilhada é legível por outro usuário autenticado ──────────────────────
        ligou = listing.share_conversation("alice", "helpdesk", "conv-1")
        check("o dono liga o compartilhamento", ligou is True)

        lida = listing.read_shared_conversation("conv-1")
        check("o terceiro lê pelo caminho compartilhado", lida.get("agent") == "helpdesk")
        check(
            "o texto gravado chega ao terceiro",
            len(lida.get("messages") or []) == 1 and lida["messages"][0]["text"] == "oi",
        )

        # O FILTRO ORIGINAL NÃO MUDOU — mesmo com a conversa compartilhada, `find_conversation`
        # de quem não é dono continua vazio. Se isto quebrasse, seria a relaxação proibida pelo
        # pedido: compartilhamento virando afrouxamento do filtro por usuário.
        check(
            "find_conversation de outro usuário continua vazio mesmo com a conversa compartilhada "
            "(o filtro por dono não foi relaxado)",
            listing.find_conversation("bob", "conv-1") == {},
        )

        # ── 3. leitura por terceiro NÃO dá acesso ao documento citado ──────────────────────
        listing.share_conversation("alice", "helpdesk", "conv-2")
        lida2 = listing.read_shared_conversation("conv-2")
        assistente = next((m for m in lida2["messages"] if m.get("role") == "assistant"), {})
        anotacao = (assistente.get("annotations") or [{}])[0]
        check(
            "a citação chega como referência (título/url/índice), não como documento",
            anotacao.get("title") == "doc.md" and anotacao.get("url") == "https://x/doc.md",
        )
        check(
            "nenhum campo de CONTEÚDO de documento (o `/source` é quem reautoriza e devolve isso)",
            "content" not in anotacao and "full_text" not in anotacao,
        )

        # ── 4. revogar volta ao estado 1 ───────────────────────────────────────────────────
        check(
            "outro usuário não revoga o que não é dele",
            listing.unshare_conversation("bob", "helpdesk", "conv-1") is False,
        )
        check(
            "depois da tentativa de terceiro, a conversa continua acessível pelo link (não revogou)",
            listing.read_shared_conversation("conv-1") != {},
        )
        desligou = listing.unshare_conversation("alice", "helpdesk", "conv-1")
        check("o dono revoga", desligou is True)
        check(
            "o terceiro deixa de ler depois da revogação (volta ao estado 1)",
            listing.read_shared_conversation("conv-1") == {},
        )
        check(
            "o dono continua lendo a própria conversa depois de revogar",
            bool(listing.find_conversation("alice", "conv-1")),
        )
        check("is_shared reflete a revogação", listing.is_shared("helpdesk", "conv-1") is False)
        check("is_shared reflete o que continua ligado", listing.is_shared("helpdesk", "conv-2") is True)

        # ── 5. cada transição grava o evento certo na trilha ───────────────────────────────
        # Eventos de `approvals` até aqui: share(bob,conv-1)→recusado (nenhum), share(alice,conv-1)
        # →1, share(alice,conv-2)→1, unshare(bob,conv-1)→recusado (nenhum), unshare(alice,conv-1)
        # →1. Três eventos reais, nenhum das duas tentativas recusadas.
        aprovacoes = trilha_fake.read("approvals")
        acessos = trilha_fake.read("access")

        ligados = [e for e in aprovacoes if "ligado" in e["summary"]]
        revogados = [e for e in aprovacoes if "revogado" in e["summary"]]
        leituras = [e for e in acessos if "terceiro" in e["summary"]]

        check("compartilhar grava um evento `write` em `approvals`", len(ligados) == 2)  # conv-1 + conv-2
        check("revogar grava um evento `write` em `approvals`", len(revogados) == 1)
        check(
            "as tentativas recusadas (bob compartilhando/revogando o que não é dele) não gravam "
            "evento nenhum — só os 3 sucessos aparecem na trilha",
            len(aprovacoes) == 3,
        )
        check(
            "cada evento de compartilhamento aponta para agent/conversation_id",
            {e["ref"] for e in ligados} == {"helpdesk/conv-1", "helpdesk/conv-2"}
            and revogados[0]["ref"] == "helpdesk/conv-1",
        )
        # As leituras por terceiro somam 3 chamadas reais neste teste (conv-1 duas vezes — a
        # segunda para confirmar que a tentativa de bob não revogou nada —, conv-2 uma vez); as
        # DUAS tentativas ANTES de compartilhar (conv-1 vazia no início, conv-1 vazia após
        # revogar) não geram evento, porque não há o que auditar sem registro de compartilhamento.
        check(
            "a leitura por terceiro grava um evento `access` em `access`, com o par certo",
            len(leituras) == 3 and {e["ref"] for e in leituras} == {"helpdesk/conv-1", "helpdesk/conv-2"},
        )

        # A cadeia da trilha continua íntegra depois de todas as transições — não é só "gravou
        # algo", é "gravou de um jeito verificável" (ver eval/audit.public.check).
        from app.modules.audit.internal.trail import verify

        check("a cadeia de `approvals` verifica", verify(aprovacoes)["ok"])
        check("a cadeia de `access` verifica", verify(acessos)["ok"])

    finally:
        listing.store = store_original
        listing.share_index = indice_original
        audit_public.trail = trail_original

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print(
        "\n✅ compartilhamento é um caminho explícito e separado: não regride o filtro por dono, "
        "libera leitura de terceiro só depois de ligado, nunca expõe documento, volta ao estado "
        "original ao revogar, e cada transição fica na trilha."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
