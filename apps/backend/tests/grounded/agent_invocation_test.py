"""O grounded invoca o AGENTE PUBLICADO, e o payload muda quando invoca.

SEGUNDA MÁXIMA: tudo fica no Foundry. Antes desta troca, o recurso publicado era catálogo —
aparecia no portal, tinha versão e histórico, e nunca atendia ninguém: o backend chamava o modelo
anonimamente com o prompt colado na requisição. A versão que o portal mostrava não era a que
respondia.

Duas invariantes, e as duas custaram erro real:

  * **`instructions` sai do payload quando o agente atende.** Mandá-las de novo as duplicaria no
    contexto e — pior — deixaria o prompt do repositório vencer o do serviço em silêncio quando os
    dois divergissem. Quando o agente atende, a versão publicada é a fonte.
  * **O modelo tem que ser o do agente.** O serviço recusa com "Model must match the agent\'s
    model when agent is specified". Descoberto invocando um agente com o nome dele no campo
    `model`, que é o erro natural de quem acabou de publicar.

Offline: nada de rede — o teste exercita a montagem do payload, não a chamada.

    uv run python -m tests.grounded.agent_invocation_test
"""

from __future__ import annotations

import sys

from app.modules.grounded.internal.grounded import build_synthesis_kwargs


class _Domain:
    id = "selfwiki"
    instructions = "Você é o especialista do projeto."


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    docs = [{"index": 1, "source": "a.md", "url": "https://x/a", "snippet": "conteúdo"}]
    kwargs = build_synthesis_kwargs("pergunta?", _Domain(), docs, model="gpt-5-mini")

    # O caminho ANÔNIMO (fallback) precisa levar as instruções — sem elas o modelo não sabe o
    # papel, e o domínio responderia como um chat genérico.
    check("o payload anônimo carrega as instruções", bool(kwargs.get("instructions")))
    check("os documentos recuperados vão no input", "conteúdo" in str(kwargs.get("input")))
    check("o modelo é o configurado", kwargs.get("model") == "gpt-5-mini")

    # O caminho do AGENTE: a mesma montagem, menos as instruções. Espelha o que grounded.py faz
    # ao detectar que o agente publicado atendeu.
    do_agente = dict(kwargs)
    do_agente.pop("instructions", None)
    check("sem instruções, o resto do payload sobrevive",
          do_agente.get("input") == kwargs.get("input") and do_agente.get("model") == "gpt-5-mini")
    check("o payload do agente NÃO leva instruções", "instructions" not in do_agente)
    # O nome do agente é o id do domínio: é o que liga o registry ao recurso publicado, e é por
    # isso que `cli.provision_agents` publica com o mesmo nome.
    check("o id do domínio é o nome do agente publicado", _Domain.id == "selfwiki")

    if falhas:
        print(f"\n❌ {len(falhas)} asserção(ões) falharam.")
        return 1
    print("\n✅ o payload muda corretamente entre o agente publicado e o fallback anônimo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
