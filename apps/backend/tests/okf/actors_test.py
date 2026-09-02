"""Strings de ator e timestamps no vocabulário do OKF v0.2 (§5 e §7).

SPEC.md:489-501 — `<produtor>/<versão>` para agente ou ferramenta, `human:<id>` para
pessoa, `process:<id>` para processo automatizado. O trust tier (SPEC.md:403-407) é
derivado do prefixo `human:`, então um ator de máquina que o carregue forja uma revisão
humana — é a única falha aqui que é silenciosa e cara.

SPEC.md:284-285 — todo timestamp é ISO 8601 com offset UTC explícito. Data pura não serve.

    uv run python -m tests.okf.actors_test
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta, timezone

from app.modules.okf.public import (
    agent_actor,
    generated_block,
    human_actor,
    okf_timestamp,
    process_actor,
    verified_entry,
)


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    def levanta(nome: str, fn) -> None:
        try:
            fn()
        except ValueError:
            check(nome, True)
        else:
            check(nome, False)

    check("agente é <produtor>/<versão>", agent_actor("openwiki", "0.4.3") == "openwiki/0.4.3")
    check("processo sem versão", process_actor("wiki-verifier") == "process:wiki-verifier")
    check(
        "processo com versão",
        process_actor("wiki-verifier", "1") == "process:wiki-verifier/1",
    )
    check("pessoa é human:<id>", human_actor("jefferson") == "human:jefferson")

    check(
        "ator de agente nunca reivindica human:",
        not agent_actor("openwiki", "0.4.3").startswith("human:"),
    )
    check(
        "ator de processo nunca reivindica human:",
        not process_actor("wiki-verifier", "1").startswith("human:"),
    )

    levanta("produtor vazio é recusado", lambda: agent_actor("", "0.4.3"))
    levanta("versão vazia é recusada", lambda: agent_actor("openwiki", ""))
    levanta("produtor com `/` é recusado", lambda: agent_actor("open/wiki", "0.4.3"))
    levanta("produtor com `:` é recusado", lambda: agent_actor("open:wiki", "0.4.3"))
    levanta("nome de processo vazio é recusado", lambda: process_actor("  "))

    utc = okf_timestamp(datetime(2026, 9, 2, 14, 30, 0, tzinfo=UTC))
    check("timestamp é ISO com offset", utc == "2026-09-02T14:30:00+00:00")
    levanta(
        "datetime ingênuo é recusado",
        lambda: okf_timestamp(datetime(2026, 9, 2, 14, 30, 0)),  # noqa: DTZ001
    )
    recife = timezone(timedelta(hours=-3))
    check(
        "outro offset é normalizado para UTC",
        okf_timestamp(datetime(2026, 9, 2, 11, 30, 0, tzinfo=recife)) == "2026-09-02T14:30:00+00:00",
    )
    agora = okf_timestamp()
    check("sem argumento usa o agora, com offset", agora.endswith("+00:00"))

    check(
        "generated tem a forma {by, at}",
        generated_block("openwiki/0.4.3", "2026-09-02T14:30:00+00:00")
        == {"by": "openwiki/0.4.3", "at": "2026-09-02T14:30:00+00:00"},
    )
    levanta("generated.by é obrigatório (SPEC.md:377)", lambda: generated_block(""))
    check(
        "verified tem a forma {by, at}",
        verified_entry("process:wiki-verifier/1", "2026-09-02T14:31:00+00:00")
        == {"by": "process:wiki-verifier/1", "at": "2026-09-02T14:31:00+00:00"},
    )
    levanta("verified[].by é obrigatório", lambda: verified_entry(" "))

    print(f"\n{'❌' if falhas else '✅'} {len(falhas)} failure(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
