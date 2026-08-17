"""Casos de uso — a camada de negócio sobre os agentes.

Existe porque a lista de agentes é vocabulário de máquina: `triage`, `retrieve`, `resolve` são
peças, e quem é de negócio precisa ver "o helpdesk". Nada aqui é uma tabela nova — o caso de uso
é uma LEITURA sobre o registry, os agentes publicados e os fluxos do repositório, mais um punhado
de campos no `metadata` do agente (SEGUNDA MÁXIMA: tudo fica no Foundry).
"""

from app.modules.usecases.internal.outcomes import outcomes, parse_assumption
from app.modules.usecases.internal.usecases import (
    get_use_case,
    list_use_cases,
    read_flow,
    rename_use_case,
    write_flow,
)

__all__ = [
    "get_use_case",
    "list_use_cases",
    "outcomes",
    "parse_assumption",
    "read_flow",
    "rename_use_case",
    "write_flow",
]
