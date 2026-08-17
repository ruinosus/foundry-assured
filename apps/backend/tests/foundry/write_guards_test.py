"""As guardas da escrita — nome de recurso, definição de agente, seleção de arquivo.

Escrita é onde o dano é irreversível, e as três guardas abaixo são código NOSSO (o SDK faz a
operação; decidir o que chega a ele é nosso). Cada uma existe por um motivo concreto:

  * **Nome.** `name` é o identificador NO SERVIÇO. Sem prefixo por tenant, um cliente sobrescreve
    a base do outro escrevendo o nome certo — escrita cruzada, não vazamento de leitura.
  * **Definição.** A spec dizia `create_version_from_manifest`; o SDK instalado mostrou que ele
    recebe `manifest_id` (referência), não documento. O caminho real é `create_version` com
    `PromptAgentDefinition`, e a tradução do documento AgentSchema para esses campos é nossa.
  * **Arquivo.** Travessia de diretório (`../`) num nome enviado pelo cliente escreveria fora do
    container previsto, porque o storage trata barra como hierarquia.

Offline: nada de rede, nada de credencial.

    uv run python -m tests.foundry.write_guards_test
"""

from __future__ import annotations

import sys

from app.modules.foundry.internal.agent_write import InvalidDefinition, parse_definition
from app.modules.foundry.internal.knowledge_write import (
    UploadRejected,
    _container_for,
    _safe_blob_name,
    check_upload,
)
from app.modules.foundry.internal.names import InvalidName, qualify, validate


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    def recusa(fn, exc=InvalidName) -> bool:
        try:
            fn()
        except exc:
            return True
        except Exception:  # noqa: BLE001 — outro tipo de erro É falha do teste, não sucesso
            return False
        return False

    print("— nome de recurso")
    check("nome válido passa", validate("minha-base") == "minha-base")
    check("vazio é recusado", recusa(lambda: validate("")))
    check("hífen no início é recusado", recusa(lambda: validate("-x")))
    check("hífen no fim é recusado", recusa(lambda: validate("x-")))
    check("espaço é recusado", recusa(lambda: validate("com espaço")))
    check("acima de 63 caracteres é recusado", recusa(lambda: validate("a" * 64)))
    check("caractere de caminho é recusado", recusa(lambda: validate("../outra")))
    # Em self_hosted não há prefixo: os recursos que existem hoje têm de continuar encontráveis.
    check("sem tenant resolvido o nome não ganha prefixo", qualify("kb") == "kb")

    print("\n— definição de agente")
    ok = parse_definition({"kind": "prompt", "model": "gpt-5-mini", "instructions": "Faça X."})
    check("documento mínimo válido vira definição", ok["definition"]["model"] == "gpt-5-mini")
    check("o tipo default é prompt", parse_definition({"model": "m", "instructions": "i"})["definition"]["kind"] == "prompt")
    check("model como objeto ({id}) é aceito",
          parse_definition({"model": {"id": "gpt-5-mini"}, "instructions": "i"})["definition"]["model"] == "gpt-5-mini")
    check("instructions em lista é juntado",
          "a\n\nb" == parse_definition({"model": "m", "instructions": ["a", "b"]})["definition"]["instructions"])
    check("sem model é recusado", recusa(lambda: parse_definition({"instructions": "i"}), InvalidDefinition))
    check("sem instructions é recusado", recusa(lambda: parse_definition({"model": "m"}), InvalidDefinition))
    check("tipo não suportado é recusado",
          recusa(lambda: parse_definition({"kind": "workflow", "model": "m", "instructions": "i"}), InvalidDefinition))
    # PowerFx sem runtime .NET voltaria literal e o agente falharia na primeira chamada.
    check("PowerFx (=Env.X) é recusado no load",
          recusa(lambda: parse_definition({"model": "=Env.MODEL", "instructions": "i"}), InvalidDefinition))
    check("campo desconhecido é REPORTADO, não silenciado",
          parse_definition({"model": "m", "instructions": "i", "inventado": 1})["ignored"] == ["inventado"])
    check("temperature/top_p passam quando presentes",
          parse_definition({"model": "m", "instructions": "i", "temperature": 0.2})["definition"]["temperature"] == 0.2)
    check("documento que não é objeto é recusado", recusa(lambda: parse_definition([1, 2]), InvalidDefinition))

    print("\n— arquivo e container")
    check("nome simples sobrevive", _safe_blob_name("runbook.md") == "runbook.md")
    # O ponto de segurança: barra é hierarquia no storage.
    check("travessia de diretório é achatada",
          _safe_blob_name("../../outra-base/segredo.md") == "segredo.md")
    check("caminho com barra perde o diretório", _safe_blob_name("docs/a/b.md") == "b.md")
    check("nome oculto (.env) é recusado", recusa(lambda: _safe_blob_name(".env"), UploadRejected))
    check("extensão não suportada é recusada",
          recusa(lambda: check_upload("binario.exe", 10), UploadRejected))
    check("arquivo grande é recusado",
          recusa(lambda: check_upload("grande.md", 50 * 1024 * 1024), UploadRejected))
    check("arquivo aceito devolve o nome de blob", check_upload("guia.pdf", 1024) == "guia.pdf")

    c = _container_for("minha-base")
    check("container começa com kb- e é minúsculo", c.startswith("kb-") and c == c.lower())
    check("container não passa de 63 caracteres", len(_container_for("a" * 63)) <= 63)
    check("container não termina em hífen", not _container_for("base-").endswith("-"))
    check("hífen duplo é colapsado", "--" not in _container_for("a__b"))

    if falhas:
        print(f"\n❌ {len(falhas)} asserção(ões) falharam.")
        return 1
    print("\n✅ as guardas de escrita recusam nome, definição e arquivo inválidos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
