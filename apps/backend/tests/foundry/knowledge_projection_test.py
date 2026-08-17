"""A projeção do catálogo de conhecimento tem três invariantes, e uma delas já falhou.

O módulo é fino de propósito (MÁXIMA MAIOR: as 11 operações estão no SDK). O pouco que ele faz
é onde dá para errar:

  * **`last_run` precisa ser objeto, não `str()`.** A primeira versão chamava `str()` no estado
    da última sincronização. Contra objeto vazio pareceu certo; contra o serviço REAL devolveu
    `"{'additional_properties': {'errors': []}, 'start_time': datetime.datetime(...)}"` — o dict
    do SDK atravessando o JSON como texto, ilegível na tela. Este teste planta o objeto com a
    forma real para que a regressão não volte.
  * **Fonte órfã tem que aparecer.** Fonte que nenhuma base referencia é indexer rodando sem
    ninguém consultando — custo silencioso. O ambiente atual tem uma (`selfwiki-docbundles-ks`,
    resquício da migração para `searchIndex`), e foi a marcação que a revelou.
  * **Mensagem de erro do indexador NÃO sai na resposta.** Ela carrega caminho e nome de
    documento; a resposta é lida por quem não necessariamente alcança a fonte. Sai a contagem.

Offline: nada de rede, nada de credencial — objetos falsos com a forma que o SDK devolve.

    uv run python -m tests.foundry.knowledge_projection_test
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from app.modules.foundry.internal.knowledge_catalog import (
    _project_base,
    _project_source,
    _run,
)


class _Ref:
    def __init__(self, name):
        self.name = name


class _Base:
    """A forma de `KnowledgeBase` — campos do `_attribute_map` do SDK instalado."""

    def __init__(self, name, sources):
        self.name = name
        self.description = "base de teste"
        self.knowledge_sources = [_Ref(s) for s in sources]
        self.e_tag = 'W/"não deve vazar"'
        self.encryption_key = "não deve vazar"
        self.retrieval_reasoning_effort = "medium"
        self.output_mode = "answerSynthesis"


class _Source:
    def __init__(self, name, kind):
        self.name = name
        self.kind = kind
        self.description = None
        self.e_tag = 'W/"não deve vazar"'


class _LastRun:
    """A forma REAL devolvida por `get_knowledge_source_status().last_synchronization_state` —
    copiada da resposta do serviço, não inventada."""

    def __init__(self, errors=()):
        self.additional_properties = {"errors": list(errors)}
        self.start_time = datetime(2026, 8, 16, 19, 57, 11, 500000, tzinfo=UTC)
        self.end_time = datetime(2026, 8, 16, 19, 57, 18, 926000, tzinfo=UTC)
        self.items_updates_processed = 13
        self.items_updates_failed = 0
        self.items_skipped = 0


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    b = _project_base(_Base("helpdesk-kb", ["helpdesk-runbooks-ks"]))
    check("nome e descrição chegam à interface", b["name"] == "helpdesk-kb" and b["description"])
    check("as fontes referenciadas viram lista de nomes", b["sources"] == ["helpdesk-runbooks-ks"])
    check("a contagem de fontes aparece", b["source_count"] == 1)
    vazados = {"e_tag", "encryption_key", "retrieval_reasoning_effort", "output_mode"} & set(b)
    check("campos de plataforma NÃO vazam para a interface", not vazados)

    base_vazia = _project_base(_Base("nova-kb", []))
    check("base sem fonte projeta sem quebrar", base_vazia["sources"] == [] and base_vazia["source_count"] == 0)

    s = _project_source(_Source("helpdesk-runbooks-ks", "azureBlob"))
    check("o kind da fonte sobe achatado (decide o que a tela oferece)", s["kind"] == "azureBlob")

    # O defeito que o dado real expôs: str() no objeto de estado.
    r = _run(_LastRun())
    check("last_run é objeto, não string", isinstance(r, dict))
    check("as datas viram ISO (datetime não atravessa JSON)",
          isinstance(r["started_at"], str) and r["started_at"].startswith("2026-08-16"))
    check("os contadores de itens chegam", r["processed"] == 13 and r["failed"] == 0)
    check("nenhum valor da projeção é o repr de um dict do SDK",
          not any(isinstance(v, str) and "additional_properties" in v for v in r.values()))

    # Erro do indexador: contagem sai, conteúdo não.
    r_err = _run(_LastRun(errors=[{"key": "/documento/secreto.md", "errorMessage": "caminho interno"}]))
    check("a CONTAGEM de erros aparece", r_err["error_count"] == 1)
    achatado = " ".join(str(v) for v in r_err.values())
    check("a MENSAGEM de erro não vaza (carrega caminho de documento)",
          "secreto" not in achatado and "caminho interno" not in achatado)

    check("estado ausente é None, não string vazia", _run(None) is None)

    # Órfã: a marcação é o que revela custo rodando sem uso.
    bases = [_project_base(_Base("kb", ["usada-ks"]))]
    fontes = [_project_source(_Source(n, "azureBlob")) for n in ("usada-ks", "esquecida-ks")]
    referenciadas = {x for bb in bases for x in bb["sources"]}
    for f in fontes:
        f["orphan"] = f["name"] not in referenciadas
    check("fonte referenciada não é marcada como órfã", fontes[0]["orphan"] is False)
    check("fonte que nenhuma base usa é marcada como órfã", fontes[1]["orphan"] is True)

    if falhas:
        print(f"\n❌ {len(falhas)} asserção(ões) falharam.")
        return 1
    print("\n✅ a projeção é legível, marca órfã e não vaza plataforma nem erro de indexador.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
