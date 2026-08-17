"""Triagem de plantão em deepagents — o gêmeo do `oncall`, para comparação prática.

Existe porque a escolha de harness é uma APOSTA em aberto, e apostas se resolvem medindo. Os dois
domínios resolvem o mesmo problema, com as mesmas tools, o mesmo contrato de HITL e o MESMO
documento de prompt; a única variável é o harness. Qualquer diferença observada tem uma causa só.

O que se pretende medir, quando os dois estiverem no ar:
  * qualidade da resposta com o mesmo prompt;
  * latência e custo de contexto (o deep agent carrega system prompt e tools que o gêmeo não tem);
  * o comportamento do HITL editável nos dois — se o card aparece igual e se o resume funciona;
  * e o que motivou a aposta: se o `SkillsMiddleware` entrega bundles (scripts, referências) que o
    direct injection do Foundry não alcança.
"""

from app.modules.deepcall.internal.graph import (
    build_deepcall_graph,
    deepcall_configured,
)

__all__ = ["build_deepcall_graph", "deepcall_configured"]
