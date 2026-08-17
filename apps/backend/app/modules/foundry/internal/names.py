"""Nome de recurso: validação e prefixo por tenant.

Isto existe porque a spec lista "nomes globais" como risco, e ele é real: `name` de agente ou de
base é o identificador NO SERVIÇO, não na nossa base de dados. Dois clientes que escolhem
"vendas" colidem — e a colisão não dá erro bonito, ela sobrescreve.

Duas regras, e a segunda é de segurança:

  1. **Formato.** O serviço exige começar e terminar em alfanumérico, hífens no meio, até 63
     caracteres (documentado em `create_version`). Validar antes de chamar transforma um 400 do
     Azure com mensagem de plataforma num erro nosso que diz o que fazer.
  2. **Prefixo por tenant.** No modo `shared` o nome recebe o prefixo do tenant. Sem isso, um
     cliente apagaria a base do outro escrevendo o nome certo — não é vazamento de leitura, é
     escrita cruzada, que é pior.

O prefixo é aplicado na ESCRITA e na LEITURA por nome, sempre pelas mesmas funções, porque
prefixar só num lado criaria recursos que ninguém encontra depois.
"""

from __future__ import annotations

import re

from app.modules.tenancy.public import current_tenant_id

# O que o serviço aceita, do docstring de `create_version` no SDK instalado.
_VALID = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
_MAX = 63


class InvalidName(ValueError):
    """Nome que o serviço recusaria — pego antes da chamada, com mensagem útil."""


def validate(name: str) -> str:
    """O nome, cru, se o serviço o aceitaria. Levanta `InvalidName` com o motivo se não."""
    name = (name or "").strip()
    if not name:
        raise InvalidName("O nome é obrigatório.")
    if len(name) > _MAX:
        raise InvalidName(f"O nome passa de {_MAX} caracteres (tem {len(name)}).")
    if not _VALID.match(name):
        raise InvalidName(
            "O nome deve começar e terminar com letra ou número, e só pode ter hífens no meio."
        )
    return name


def _prefix() -> str:
    """O prefixo do tenant, ou vazio no modo single-tenant.

    `current_tenant_id()` só devolve algo quando há tenant resolvido por request (modo
    `shared`). Em `self_hosted` não há prefixo — e não deve haver, ou os recursos que já existem
    no ambiente de hoje deixariam de ser encontrados pelo nome que têm.
    """
    tid = current_tenant_id()
    return f"{tid}-" if tid else ""


def qualify(name: str) -> str:
    """O nome como ele existe NO SERVIÇO: validado e, no modo shared, prefixado.

    O prefixo entra depois da validação e é contado no teto: um nome válido de 63 caracteres
    ficaria inválido ao receber prefixo, e falhar aqui é melhor que falhar no Azure.
    """
    validate(name)
    full = f"{_prefix()}{name}"
    if len(full) > _MAX:
        raise InvalidName(
            f"Com o prefixo do tenant o nome passa de {_MAX} caracteres — use um nome mais curto."
        )
    return full
