"""Fecha o dia da trilha de auditoria — o comando que a agenda chama.

O QUE ELE FAZ, e por que precisa existir separado da API. A âncora existe desde a ADR-023, mas só
podia ser criada por um clique na tela — e âncora que depende de alguém lembrar é âncora que não
existe. Sem fecho diário, a cadeia continua internamente consistente e não tem NADA que impeça
alguém de reescrever o arquivo inteiro recalculando os hashes.

Ele é idempotente por construção do serviço: a âncora é write-once, então a segunda execução do
mesmo dia recebe `AnchorExists` e sai com sucesso, dizendo que já estava fechado. Um agendador
que dispara duas vezes não vira dois fechos nem um erro.

    uv run python -m cli.close_audit_day            # fecha os três escopos, hoje
    uv run python -m cli.close_audit_day --date …   # um dia específico (recuperar atraso)

SAI COM CÓDIGO ≠ 0 quando um escopo tem trilha VIOLADA. Não é frescura de exit code: uma trilha
adulterada não é ancorada (ancorá-la seria certificá-la), e o silêncio nesse caso transformaria a
descoberta mais importante que este sistema pode fazer num log que ninguém lê.
"""

from __future__ import annotations

import argparse
import sys

from app.modules.audit.internal.export import ESCOPOS
from app.modules.audit.public import AnchorExists, close_day


def main() -> int:
    parser = argparse.ArgumentParser(description="Fecha o dia da trilha de auditoria.")
    parser.add_argument("--date", default="", help="AAAA-MM-DD; vazio = hoje (UTC)")
    args = parser.parse_args()

    violados: list[str] = []
    print(f"Fechando o dia{' ' + args.date if args.date else ''} — {len(ESCOPOS)} escopos.\n")

    for escopo in ESCOPOS:
        try:
            r = close_day(escopo, args.date)
        except AnchorExists:
            print(f"  · {escopo:12} já fechado (write-once — nada a fazer)")
            continue
        except Exception as exc:  # noqa: BLE001 — um escopo ilegível não impede fechar os outros
            print(f"  ✗ {escopo:12} falhou: {type(exc).__name__}: {exc}")
            violados.append(escopo)
            continue

        if r.get("written"):
            print(f"  ✅ {escopo:12} {r['events']} eventos, digest {str(r['digest'])[:16]}…")
        elif r.get("refused"):
            print(f"  ✗ {escopo:12} NÃO ancorado: {r['refused']}")
            # Trilha violada é o caso grave; "sem storage" é ambiente local e não deve falhar.
            if "violada" in str(r["refused"]):
                violados.append(escopo)
        else:
            print(f"  · {escopo:12} sem eventos")

    if violados:
        print(f"\n❌ {len(violados)} escopo(s) não puderam ser ancorados: {', '.join(violados)}")
        print("   Trilha violada NÃO é ancorada — ancorar uma cadeia adulterada seria certificá-la.")
        return 1
    print("\n✅ dia fechado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
