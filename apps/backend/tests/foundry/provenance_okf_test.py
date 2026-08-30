"""A procedência que chega ao evento fala OKF v0.2 — e o formato antigo não some no caminho.

POR QUE ESTE TESTE EXISTE. `metadata.provenance` é o elo entre "de onde veio este texto" e "quando
ele entrou num recurso publicado" (ADR-023). Ele acabou de trocar de vocabulário: era um mapa
`{campo: [fontes]}` inventado aqui, passou a ser o `generated`/`sources`/`verified` do **OKF
v0.2**, a spec aberta do Google Cloud que este repositório já produz em `openwiki/`.

Uma troca de formato num campo de auditoria tem uma falha característica, e ela é silenciosa:
recursos publicados ANTES continuam carregando o formato antigo — documento publicado não é
reescrito —, e uma leitura que só entendesse o formato novo faria a procedência deles desaparecer
da trilha, sem erro nenhum, no dia em que alguém os republicasse.

O que este teste guarda:

1. o formato novo atravessa intacto;
2. o formato antigo é CONVERTIDO, e a conversão **não inventa** o que o formato antigo não sabia
   (quem escreveu, quando) — preencher com o agente de hoje produziria um registro que parece
   medido e é chute;
3. `verified` é carimbado no backend, com `actor()` — e é dele que o consumidor OKF deriva o
   trust tier, pelo prefixo `human:` (SPEC §5.2);
4. a identidade **não** vem do documento: mesmo que a tela mande um `verified`, quem decide é
   `actor()`. Um documento que pudesse declarar quem o verificou seria um documento capaz de
   forjar a própria revisão;
5. lixo não vira procedência.

    uv run python -m tests.foundry.provenance_okf_test
"""

from __future__ import annotations

import json
import sys

from app.modules.foundry.internal.audited import _procedencia
from app.shared import auth


class _User:
    def __init__(self, email: str = "", oid: str = ""):
        self.email = email
        self.oid = oid
        self.preferred_username = ""
        self.roles = ()
        self.access_token = ""


def _doc(prov) -> dict:
    """Um documento como o que a tela publica: a procedência viaja SERIALIZADA (o Foundry exige
    valores de metadata em string — medido, 400 com o objeto cru)."""
    return {"kind": "prompt", "metadata": {"provenance": json.dumps(prov)}}


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    novo = {
        "okf_version": "0.2",
        "fields": {
            "instructions": {
                "generated": {"by": "builder", "at": "2026-08-30T12:00:00+00:00"},
                "sources": [{"id": "rh-politicas", "resource": "rh-politicas"}],
            },
            # Campo escrito pelo agente SEM fonte: honesto, e o formato antigo não sabia dizer.
            "description": {"generated": {"by": "builder", "at": "2026-08-30T12:01:00+00:00"}},
        },
    }

    try:
        auth._current_user.set(_User(email="ana@contoso.com"))

        # --- 1 · o formato novo atravessa intacto ----------------------------------------
        saida = _procedencia(_doc(novo))["provenance"]
        check("okf_version preservado", saida["okf_version"] == "0.2")
        check("os campos atravessam", set(saida["fields"]) == {"instructions", "description"})
        check(
            "generated atravessa como veio",
            saida["fields"]["instructions"]["generated"]["by"] == "builder",
        )
        check(
            "campo sem fonte NÃO ganha uma lista vazia",
            "sources" not in saida["fields"]["description"],
        )

        # --- 3 · verified é carimbado aqui, com actor() ----------------------------------
        ver = saida["verified"]
        check("verified é uma lista de eventos", isinstance(ver, list) and len(ver) == 1)
        check("…e o ator é human:<e-mail> (convenção OKF §7)", ver[0]["by"] == "human:ana@contoso.com")
        check("…com instante ISO 8601 e offset explícito", ver[0]["at"].endswith("+00:00"))

        # --- 4 · o documento NÃO pode declarar quem o verificou --------------------------
        forjado = {**novo, "verified": [{"by": "human:chefe@contoso.com", "at": "2020-01-01T00:00:00+00:00"}]}
        saida_forjada = _procedencia(_doc(forjado))["provenance"]
        check(
            "um verified vindo do documento é SOBRESCRITO por actor()",
            saida_forjada["verified"] == [
                {"by": "human:ana@contoso.com", "at": saida_forjada["verified"][0]["at"]}
            ],
        )

        # --- 2 · o formato ANTIGO continua chegando à trilha -----------------------------
        antigo = {"description": ["rh-politicas"], "instructions": ["rh-politicas/ferias.md"]}
        conv = _procedencia(_doc(antigo))["provenance"]
        check("o formato antigo vira OKF v0.2", conv["okf_version"] == "0.2")
        check("…sem perder nenhum campo", set(conv["fields"]) == {"description", "instructions"})
        check(
            "…nem nenhuma fonte",
            conv["fields"]["description"]["sources"] == [
                {"id": "rh-politicas", "resource": "rh-politicas"}
            ],
        )
        check(
            "…e NÃO inventa quem escreveu nem quando",
            conv["fields"]["description"]["generated"] == {"legacy": True},
        )

        # --- 5 · lixo não vira procedência -----------------------------------------------
        check("documento sem metadata", _procedencia({"kind": "prompt"}) == {})
        check("metadata sem provenance", _procedencia({"metadata": {"x": "1"}}) == {})
        check("string ilegível", _procedencia({"metadata": {"provenance": "{nao é json"}}) == {})
        check("provenance vazia", _procedencia({"metadata": {"provenance": "{}"}}) == {})
        check("documento que não é dict", _procedencia("texto") == {})

        # --- 3b · sem usuário resolvido o tier é machine-confirmed, e isso é a verdade ---
        auth._current_user.set(None)
        sem_user = _procedencia(_doc(novo))["provenance"]
        check("job/script sai como process:app", sem_user["verified"][0]["by"] == "process:app")
        check(
            "…e process: NÃO é human: — o tier não sobe sozinho",
            not sem_user["verified"][0]["by"].startswith("human:"),
        )
    finally:
        auth._current_user.set(None)

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ a procedência fala OKF v0.2, o formato antigo sobrevive, e o tier vem do servidor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
