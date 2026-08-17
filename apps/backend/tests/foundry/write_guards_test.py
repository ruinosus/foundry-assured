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
from app.modules.foundry.internal.skills import (
    InvalidSkill,
    _ensure_frontmatter,
    _project,
    parse_skill,
)
from app.modules.foundry.internal.toolboxes import (
    InvalidToolbox,
    mcp_url,
    parse_toolbox,
)


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

    print("\n— tools: a ponte entre agente e base")
    # Sem `tools` o agente criado não alcança nada — nem a base que o usuário acabou de criar.
    # Era a lacuna mais grave: o produto tinha as duas metades e nenhuma ponte.
    com_kb = parse_definition({"model": "m", "instructions": "i", "knowledge_base": "minha-kb"})
    tools = com_kb["definition"]["tools"]
    check("o atalho knowledge_base vira uma tool de busca", len(tools) == 1)
    check("a tool aponta para o índice da base",
          tools[0]["azure_ai_search"]["indexes"][0]["index_name"] == "minha-kb")
    check("o tipo da tool é azure_ai_search", tools[0]["type"] == "azure_ai_search")
    # Nome de tool não aceita hífen no serviço; o atalho normaliza.
    check("o nome da tool troca hífen por underscore", "-" not in tools[0]["name"])
    # O atalho ADICIONA: quem já manda tools próprias não as perde.
    ambos = parse_definition({"model": "m", "instructions": "i", "knowledge_base": "kb",
                              "tools": [{"type": "mcp", "server_label": "learn"}]})
    check("tools do documento SOBREVIVEM ao atalho", len(ambos["definition"]["tools"]) == 2)
    check("MCP passa cru (é tool de primeira parte, não precisa de tradução)",
          any(t.get("type") == "mcp" for t in ambos["definition"]["tools"]))
    # O segundo atalho: `toolbox: <nome>` vira o `mcp` tool com a URL. É o vínculo que a pesquisa
    # revelou — o toolbox É um servidor MCP, e o agente aponta para ele pela URL.
    com_tb = parse_definition({"model": "m", "instructions": "i", "toolbox": "minha-tb"})
    check("o atalho toolbox vira um mcp tool", com_tb["definition"]["tools"][0]["type"] == "mcp")
    check("a URL do toolbox é a consumer (sem versão fixa)",
          "/versions/" not in com_tb["definition"]["tools"][0]["server_url"])
    dois = parse_definition({"model": "m", "instructions": "i", "knowledge_base": "kb", "toolbox": "tb"})
    check("os dois atalhos convivem", len(dois["definition"]["tools"]) == 2)
    check("toolbox que não é texto é recusado",
          recusa(lambda: parse_definition({"model": "m", "instructions": "i", "toolbox": 1}), InvalidDefinition))
    check("knowledge_base que não é texto é recusado",
          recusa(lambda: parse_definition({"model": "m", "instructions": "i", "knowledge_base": 1}), InvalidDefinition))
    # Os 10 campos de PromptAgentDefinition, menos os 3 tratados à parte: nenhum fica de fora.
    todos = parse_definition({"model": "m", "instructions": "i", "temperature": 1, "top_p": 1,
                              "tools": [], "tool_choice": "auto", "reasoning": {}, "text": {},
                              "structured_inputs": []})
    check("nenhum campo do tipo é ignorado em silêncio", todos["ignored"] == [])

    print("\n— skill (formato agentskills.io)")
    ok_skill = parse_skill({"instructions": "Como revisar um PR.", "description": "Revisão de PR"})
    check("documento mínimo de skill é aceito", ok_skill["content"]["instructions"].startswith("Como"))
    check("sem instructions é recusado", recusa(lambda: parse_skill({}), InvalidSkill))
    # Descoberto contra o serviço: `description` é obrigatório, embora o SDK o declare opcional.
    # Sem ele o Foundry devolve "invalid_payload: The request field is required" — sem nomear o
    # campo. Recusar aqui transforma isso numa frase que diz o que preencher.
    check("sem description é recusado (o serviço exige, o SDK não diz)",
          recusa(lambda: parse_skill({"instructions": "i"}), InvalidSkill))
    check("PowerFx é recusado em skill também",
          recusa(lambda: parse_skill({"instructions": "=Env.X", "description": "d"}), InvalidSkill))
    check("campos do padrão aberto passam",
          "license" in parse_skill({"instructions": "i", "description": "d", "license": "MIT"})["content"])

    class _Skill:
        def __init__(self, d, l):
            self.name, self.id, self.description, self.created_at = "s", "sk_1", None, None
            self.default_version = type("V", (), {"version": d, "description": None, "created_at": None})()
            self.latest_version = type("V", (), {"version": l, "description": None, "created_at": None})()

    # A pergunta "publiquei e nada mudou, por quê?" — respondida por dois campos SEPARADOS.
    check("default igual a latest é sinalizado como sincronizado",
          _project(_Skill("2", "2"))["latest_is_default"] is True)
    check("default DIFERENTE de latest é sinalizado (a nova versão não está em uso)",
          _project(_Skill("1", "2"))["latest_is_default"] is False)

    # O upload multipart falha sem frontmatter YAML no SKILL.md — exigência do serviço que o SDK
    # não declara, e cuja mensagem fala de um formato que o usuário final não conhece.
    gerado = _ensure_frontmatter("revisar-pr", "Revisão de PR", b"# Conteudo\n").decode()
    check("frontmatter é gerado quando falta", gerado.startswith("---\nname: revisar-pr"))
    check("a descrição entra no frontmatter", "description: Revisão de PR" in gerado)
    # Com aspas o serviço responde invalid_payload — é o parser dele, não estilo.
    check("o valor não leva aspas", '"' not in gerado.split("---")[1])
    ja_tem = b"---\nname: outro\ndescription: ja tinha\n---\n\n# X\n"
    check("frontmatter existente é respeitado",
          _ensure_frontmatter("revisar-pr", "nova", ja_tem) == ja_tem)
    check("sem descrição, o nome vira a descrição",
          "description: revisar-pr" in _ensure_frontmatter("revisar-pr", "", b"# X").decode())

    print("\n— toolbox: onde skill e tool viram um pacote")
    # Skill NÃO entra em PromptAgentDefinition.tools. Um toolbox é o único caminho de uma skill
    # até um agente — sem ele a skill criada é decorativa.
    tb = parse_toolbox({"tools": [{"type": "mcp", "server_label": "learn"}], "skills": ["revisar-pr"]})
    check("nome solto de skill vira referência", tb["skills"] == [{"name": "revisar-pr"}])
    check("a tool do pedido é preservada", tb["tools"][0]["type"] == "mcp")
    com_versao = parse_toolbox({"skills": [{"name": "s", "version": "2"}]})
    check("skill com versão explícita mantém a versão", com_versao["skills"][0]["version"] == "2")
    # Sem versão o serviço usa a default da skill — é por isso que a tela de skills mostra
    # `default` e `latest` lado a lado.
    check("skill sem versão não inventa uma", "version" not in parse_toolbox({"skills": ["s"]})["skills"][0])
    check("toolbox vazio é recusado (não entrega nada)",
          recusa(lambda: parse_toolbox({}), InvalidToolbox))
    check("skill malformada é recusada",
          recusa(lambda: parse_toolbox({"skills": [{"sem_nome": 1}]}), InvalidToolbox))
    check("tools que não é lista é recusado",
          recusa(lambda: parse_toolbox({"tools": "mcp"}), InvalidToolbox))

    # O vínculo agente↔toolbox é a URL: o toolbox É um servidor MCP. Sem versão, o endpoint serve
    # a default_version — é o que faz promover uma skill valer sem tocar no agente.
    consumer = mcp_url("minha-toolbox")
    check("a URL consumer não fixa versão (segue a default)",
          "/versions/" not in consumer["url"] and consumer["url"].endswith("/mcp?api-version=v1"))
    check("a URL developer fixa a versão pedida", "/versions/2/mcp" in mcp_url("minha-toolbox", "2")["url"])
    check("o tool pronto é do tipo mcp", consumer["tool"]["type"] == "mcp")
    # server_label não aceita hífen no serviço.
    check("server_label troca hífen por underscore", "-" not in consumer["tool"]["server_label"])
    # A doc é explícita: o endpoint NÃO bloqueia tools/call. O default seguro é declarar always.
    check("require_approval nasce em always", consumer["tool"]["require_approval"] == "always")
    check("nome inválido é recusado antes de montar URL",
          recusa(lambda: mcp_url("../outro"), InvalidName))

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
