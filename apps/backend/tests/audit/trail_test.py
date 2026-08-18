"""A trilha detecta adulteração, o redator distingue documento de número, e aprovar sem registro
não roda a ação (ADR-023).

    uv run python -m tests.audit.trail_test

POR QUE ESTE GATE. A camada de evidência tem três propriedades que, se falharem, falham em
SILÊNCIO — que é o pior modo para uma auditoria:

  1. uma cadeia que não detecta adulteração parece íntegra;
  2. um redator que mascara demais estraga dado legítimo e é desligado na primeira semana; um que
     mascara de menos deixa passar o que existe para barrar;
  3. uma aprovação cuja gravação falhou, mas que roda a ação mesmo assim, produz escrita sem
     rastro — exatamente o buraco que a trilha existe para não ter.

Roda offline, sobre o fake em memória: o que está travado é o CONTRATO, não o SDK do Azure.
"""

from __future__ import annotations

import sys

from app.modules.audit.internal.redact import redact
from app.modules.audit.internal.trail import GENESIS, InMemoryTrail, verify

failures: list[str] = []


def check(nome: str, cond: bool) -> None:
    print(f"  {'✓' if cond else '✗'} {nome}")
    if not cond:
        failures.append(nome)


def main() -> int:
    print("trilha de auditoria — contrato\n")

    # ── cadeia ────────────────────────────────────────────────────────────────
    t = InMemoryTrail()
    for i in range(4):
        t.append("s", f"human:oid-{i}", "approval", f"aprovou {i}", ref=f"HD-{i}")
    ev = t.read("s")

    check("os eventos são numerados a partir de 1", [e["seq"] for e in ev] == [1, 2, 3, 4])
    check("o primeiro aponta para genesis", ev[0]["prev"] == GENESIS)
    check("cada um aponta para o hash do anterior", all(ev[i]["prev"] == ev[i - 1]["hash"] for i in range(1, 4)))
    check("a cadeia íntegra verifica", verify(ev)["ok"])

    # ADULTERAÇÃO NO MEIO — o caso que importa. Uma cadeia que só detecta mudança no último
    # evento é inútil: quem adultera escolhe o meio.
    alterado = [dict(e) for e in ev]
    alterado[1]["summary"] = "aprovou outra coisa"
    r = verify(alterado)
    check("adulteração no meio é detectada", not r["ok"])
    check("e ela aponta o seq exato", r["broken_at"] == 2)

    # REMOÇÃO — tirar um evento quebra o encadeamento do seguinte.
    removido = [e for e in ev if e["seq"] != 2]
    check("remover um evento é detectado", not verify(removido)["ok"])

    # ── redator ───────────────────────────────────────────────────────────────
    saida, achados = redact("CPF 529.982.247-25 e mail a@b.com")
    check("CPF válido é mascarado", "cpf" in achados and "529.982.247-25" not in saida)
    check("e-mail é mascarado", "email" in achados and "a@b.com" not in saida)
    check("CPF inválido NÃO é mascarado", not redact("000.000.000-00")[1])
    check("protocolo de 11 dígitos NÃO é mascarado", not redact("protocolo 12345678901")[1])
    check("cartão por Luhn é mascarado", "cartao" in redact("4111 1111 1111 1111")[1])
    check("texto sem documento passa intacto", redact("reiniciar o serviço de faturamento") == ("reiniciar o serviço de faturamento", []))

    # O redator devolve TIPOS, nunca o valor — é o que permite registrar "havia um CPF" sem pôr
    # o CPF na trilha imutável.
    check("os achados são tipos, não valores", all(a.isalpha() for a in redact("CPF 529.982.247-25")[1]))

    # ── fail-closed ───────────────────────────────────────────────────────────
    from app.modules.hitl.public import ApprovalRequest, NotAuthorized, decide
    import app.modules.hitl.public as hitl

    pedido = ApprovalRequest(action="create_ticket", args={}, allowed_decisions=("approve", "reject"))

    quebrado = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("storage fora do ar"))  # noqa: E731
    original = hitl._registrar
    try:
        hitl._registrar = lambda req, dec: quebrado()
        try:
            decide(pedido, "approve")
            check("approve com trilha quebrada NÃO passa", False)
        except Exception as exc:
            check("approve com trilha quebrada NÃO passa", isinstance(exc, (NotAuthorized, RuntimeError)))
    finally:
        hitl._registrar = original

    # ── âncora ────────────────────────────────────────────────────────────────
    from app.modules.audit.internal.anchor import build_anchor

    a = build_anchor("s", ev, "2026-08-18")
    check("a âncora carrega o hash de cabeça", a["digest"] == ev[-1]["hash"])
    check("e o número de eventos", a["events"] == 4 and a["seq"] == 4)
    check("trilha íntegra é ancorável", a["verified"])
    # TRILHA VIOLADA NÃO É ANCORADA: ancorar uma cadeia adulterada seria certificá-la.
    check("trilha violada NÃO é ancorável", not build_anchor("s", alterado, "2026-08-18")["verified"])
    # Os slots de prova temporal existem e nascem VAZIOS — omiti-los faria o auditor supor que a
    # prova existe, e a omissão seria a mentira.
    check("os slots de prova temporal são declarados e nulos", a["tsr"] is None and a["ledger_receipt"] is None)

    # ── pacote ────────────────────────────────────────────────────────────────
    import io
    import json
    import zipfile

    from app.modules.audit.public import build_package, build_report

    rel = build_report()
    check("o relatório nomeia as provas que faltam", rel["missing_proofs"] == ["rfc3161_timestamp", "ledger_receipt"])

    z = zipfile.ZipFile(io.BytesIO(build_package()))
    nomes = z.namelist()
    check("o pacote traz o relatório", "verificacao.json" in nomes)
    check("o pacote ensina a verificar sem o produto", "LEIA-ME.md" in nomes)
    leiame = z.read("LEIA-ME.md").decode()
    check("e diz o que NÃO prova", "Não prova" in leiame and "RFC 3161" in leiame)
    check("a fórmula do hash está no LEIA-ME", "sha256(prev" in leiame)

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ a cadeia detecta adulteração e remoção, o redator distingue documento de número,")
    print("   e uma aprovação sem registro não roda a ação.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
