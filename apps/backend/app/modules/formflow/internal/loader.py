"""Carrega os manifestos de FormFlow — os formulários do produto, como documento.

POR QUE ELE EXISTE. Os wizards de agente, skill e base eram três componentes React escritos à
mão, cada um com os seus campos, as suas regras e o seu texto de revisão em código. Três cópias
da mesma máquina: acrescentar uma validação num deles não acrescentava nos outros, e a diferença
só aparecia quando alguém publicava com o nome errado pelo formulário que ainda não checava.

O manifesto é um documento **OKF** (`type: formflow`) em `agents/assured/flows/`, ao lado dos
documentos AgentSchema — mesmo diretório, mesma publicação sem rebuild (ADR-014). O corpo carrega
o `spec` em YAML; o frontmatter é o que faz dele um documento de bundle e não um arquivo solto.

O QUE ESTE MÓDULO NÃO FAZ: validar o preenchimento. As regras (`resourceName`, `max63`, `unique`)
são NOMES aqui — quem as aplica é a tela, no campo, enquanto a pessoa digita, e o backend na
fronteira. Um validador aqui seria uma terceira implementação da mesma regra.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

import app as _app

#: Ancorado no pacote `app`, nunca em `parents[N]` a partir deste arquivo (regra 9): três caminhos
#: quebraram assim durante a ADR-017, dois em silêncio.
BACKEND_ROOT = Path(_app.__file__).resolve().parent.parent

#: O bloco ```yaml do corpo do documento. O `spec` vive no CORPO e não no frontmatter porque o
#: frontmatter é transporte OKF (`type`, `title`) — misturar as duas coisas faria o documento
#: deixar de ser legível como markdown, que é metade do ponto do formato.
_FENCE = "```yaml"


class FlowNotFound(Exception):
    """Não existe manifesto com esse nome. Dito alto: uma tela sem manifesto não tem o que
    renderizar, e cair num formulário vazio esconderia a causa."""


class FlowInvalid(Exception):
    """O manifesto existe e não serve. Também alto — um `spec` torto vira um formulário sem os
    campos que ele deveria ter, e ninguém percebe até alguém publicar sem preencher."""


def _base_dir() -> Path:
    """A raiz dos documentos declarativos. `AGENTS_DIR` a move junto com os prompts (ADR-014):
    são a mesma classe de artefato — definição publicável sem rebuild."""
    externo = os.getenv("AGENTS_DIR", "").strip()
    return Path(externo) if externo else BACKEND_ROOT / "agents" / "assured"


def flows_dir() -> Path:
    """Onde os manifestos de formulário moram."""
    return _base_dir() / "flows"


def copilots_dir() -> Path:
    """Onde os copilotos e as políticas moram.

    MESMO MECANISMO, outro diretório: um copiloto é um documento OKF com um bloco `spec` em YAML,
    exatamente como um formflow. O que muda é o que o `spec` significa — e é por isso que o
    loader é genérico e a VALIDAÇÃO é por tipo.
    """
    return _base_dir() / "copilots"


def _extrair_spec(texto: str, nome: str) -> dict[str, Any]:
    """O YAML de dentro do bloco cercado. Sem bloco, sem formulário — e isso é dito."""
    inicio = texto.find(_FENCE)
    if inicio == -1:
        raise FlowInvalid(f"{nome}: nenhum bloco {_FENCE} no corpo do documento")
    inicio += len(_FENCE)
    fim = texto.find("```", inicio)
    if fim == -1:
        raise FlowInvalid(f"{nome}: bloco {_FENCE} sem fechamento")
    try:
        spec = yaml.safe_load(texto[inicio:fim])
    except yaml.YAMLError as exc:
        raise FlowInvalid(f"{nome}: spec não é YAML válido: {exc}") from exc
    if not isinstance(spec, dict):
        raise FlowInvalid(f"{nome}: o spec precisa ser um mapa")
    return spec


def _validar(spec: dict, nome: str) -> None:
    """O mínimo que a tela precisa para renderizar alguma coisa.

    Deliberadamente raso: o manifesto é dado de produto, e um schema completo aqui viraria uma
    segunda especificação a manter ao lado do documento. O que se checa é o que, faltando,
    produz um formulário SILENCIOSAMENTE vazio — o modo de falha que não se anuncia.
    """
    secoes = spec.get("sections")
    if not isinstance(secoes, list) or not secoes:
        raise FlowInvalid(f"{nome}: sem `sections` — não há formulário a renderizar")
    vistos: set[str] = set()
    conditions: list[tuple[str, dict[str, Any]]] = []
    for i, sec in enumerate(secoes):
        if not isinstance(sec, dict) or not sec.get("id"):
            raise FlowInvalid(f"{nome}: seção {i} sem `id`")
        campos = sec.get("fields")
        if not isinstance(campos, list) or not campos:
            raise FlowInvalid(f"{nome}: seção '{sec['id']}' sem campos")
        for campo in campos:
            if not isinstance(campo, dict) or not campo.get("id"):
                raise FlowInvalid(f"{nome}: campo sem `id` na seção '{sec['id']}'")
            cid = campo["id"]
            # Id repetido é a falha mais cara aqui: dois campos com o mesmo `id` compartilham
            # valor, e a proposta do agente cairia nos dois. Silencioso no render, óbvio aqui.
            if cid in vistos:
                raise FlowInvalid(f"{nome}: campo '{cid}' declarado duas vezes")
            vistos.add(cid)
            if not campo.get("type"):
                raise FlowInvalid(f"{nome}: campo '{cid}' sem `type`")
            if "visibleWhen" in campo:
                condition = campo["visibleWhen"]
                if not isinstance(condition, dict) or set(condition) != {"field", "equals"}:
                    raise FlowInvalid(f"{nome}: campo '{cid}' tem `visibleWhen` inválido")
                conditions.append((cid, condition))
    for cid, condition in conditions:
        if condition.get("field") not in vistos:
            raise FlowInvalid(
                f"{nome}: campo '{cid}' depende de campo inexistente em `visibleWhen`"
            )
        if not isinstance(condition.get("equals"), str) or not condition["equals"]:
            raise FlowInvalid(f"{nome}: campo '{cid}' tem `visibleWhen.equals` inválido")


@lru_cache(maxsize=32)
def load_copilot(nome: str) -> dict[str, Any]:
    """Um copiloto declarado: onde ele monta, sobre qual agente roda, em que campos escreve.

    NÃO valida os alvos contra os formulários — isso é `verificar_alvos`, chamado por quem tem os
    dois em mãos. Um loader que fosse buscar o outro documento acoplaria os dois carregamentos, e
    um copiloto com alvo torto deixaria de carregar em vez de carregar e reprovar.
    """
    return _carregar(copilots_dir(), nome)


@lru_cache(maxsize=32)
def load_flow(nome: str) -> dict[str, Any]:
    """O manifesto de um formulário, pronto para a tela.

    Em cache porque é leitura de disco por requisição de tela e o documento só muda por deploy ou
    por publicação no mount do Azure Files — o mesmo raciocínio dos prompts. `AGENTS_DIR` entra na
    resolução, não na chave: trocar o diretório em runtime não é um caso que exista.
    """
    return _carregar(flows_dir(), nome, validar=_validar)


def _frontmatter(texto: str) -> dict[str, Any]:
    """O frontmatter OKF do documento: `type`, `title`, `description`.

    ELE PRECISA CHEGAR À TELA, e não chegava. O loader devolvia só o `spec` do bloco YAML, então
    o catálogo mostrava `builder` onde o documento diz "Assistente do formulário" — o título
    existia no arquivo e sumia no caminho. Encontrado rodando a tela.

    Frontmatter torto NÃO derruba o documento: o `spec` é o que a tela precisa para renderizar, e
    um `title:` mal escrito não é motivo para a tela não abrir. A conformidade do frontmatter é
    do verificador OKF (`tests.knowledge.okf_conformance_test`), que é quem deve reclamar dele.
    """
    if not texto.startswith("---"):
        return {}
    fim = texto.find("\n---", 3)
    if fim == -1:
        return {}
    try:
        meta = yaml.safe_load(texto[3:fim])
    except yaml.YAMLError:
        return {}
    return meta if isinstance(meta, dict) else {}


def _carregar(diretorio: Path, nome: str, validar=None) -> dict[str, Any]:
    """Um documento declarativo: frontmatter OKF + `spec` no bloco YAML do corpo."""
    # O nome vira CAMINHO, então ele é conferido antes: um `../../.env` que virasse `Path` seria
    # leitura arbitrária de arquivo.
    if not nome.replace("-", "").replace("_", "").isalnum():
        raise FlowNotFound(f"nome de documento inválido: {nome!r}")
    caminho = diretorio / f"{nome}.md"
    if not caminho.is_file():
        raise FlowNotFound(f"nenhum documento '{nome}' em {diretorio}")
    texto = caminho.read_text(encoding="utf-8")
    spec = _extrair_spec(texto, nome)
    if validar:
        validar(spec, nome)
    meta = _frontmatter(texto)
    # O `spec` vence o frontmatter num conflito de chave: ele é o que descreve o comportamento, e
    # o frontmatter é transporte. `name` vence os dois — é o nome do ARQUIVO, e um `resource:`
    # divergente no frontmatter não pode fazer a tela buscar outro documento.
    return {
        **{k: meta[k] for k in ("title", "description") if k in meta},
        **spec,
        "name": nome,
    }


def list_flows() -> list[str]:
    """Os formulários publicados, em ordem. Vazio quando o diretório não existe — a tela
    distingue "não há" de "não consegui ler" pelo erro da rota, não por uma lista vazia."""
    d = flows_dir()
    return sorted(p.stem for p in d.glob("*.md")) if d.is_dir() else []


def list_copilots() -> list[str]:
    """Os copilotos e políticas publicados, em ordem."""
    d = copilots_dir()
    return sorted(p.stem for p in d.glob("*.md")) if d.is_dir() else []


def campos_propostaveis() -> list[str]:
    """Todo campo que um copiloto PODE declarar como alvo, no formato `formulario.campo`.

    POR QUE ISTO EXISTE, e é a peça que torna a tela de criação segura. Um formulário que pedisse
    os alvos como TEXTO deixaria a pessoa digitar `agent.instrucoes` (que não existe) ou
    `agent.model` (que existe e não aceita proposta) — e o erro só apareceria depois, quando
    alguém usasse o copiloto. Derivando a lista dos formulários reais, declarar um alvo inválido
    deixa de ser possível: a opção não está lá.

    É a mesma regra que já vale para base de conhecimento e toolbox no wizard de agente — a lista
    vem do SERVIÇO, não de uma lista escrita na tela (SEGUNDA MÁXIMA). Aqui o "serviço" são os
    outros documentos do bundle.

    Só campos `ai: true`: propor num campo que não aceita proposta produz um card que a pessoa não
    tem como aceitar.
    """
    saida: list[str] = []
    for nome in list_flows():
        try:
            flow = load_flow(nome)
        except (FlowNotFound, FlowInvalid):
            # Um formulário torto não derruba a lista dos outros: quem edita o copiloto ainda
            # precisa dos alvos que funcionam. O formulário quebrado aparece no gate dele.
            continue
        for secao in flow["sections"]:
            for campo in secao["fields"]:
                if campo.get("ai"):
                    saida.append(f"{nome}.{campo['id']}")
    return sorted(saida)


def alvos_de(selecionados: list[str]) -> list[dict[str, Any]]:
    """Agrupa `formulario.campo` no bloco `targets:` do manifesto.

    A tela trabalha com uma lista plana (é o que um seletor múltiplo produz); o documento pede um
    alvo por formulário, com os campos dentro. A conversão é aqui e não na tela porque é a FORMA
    do manifesto, e o manifesto é do backend.
    """
    por_flow: dict[str, list[str]] = {}
    for item in selecionados:
        flow, _, campo = str(item).partition(".")
        if flow and campo:
            por_flow.setdefault(flow, []).append(campo)
    return [
        {"flow": f, "writes": sorted(cs), "validateAgainst": "field.rules"}
        for f, cs in sorted(por_flow.items())
    ]


def verificar_alvos(copiloto: dict[str, Any]) -> list[str]:
    """Os problemas dos alvos de um copiloto. Lista vazia = tudo confere.

    ESTA É A CHECAGEM QUE FAZ O `type: copilot` VALER A PENA. Um copiloto declara em que campos
    pode escrever; sem conferir, ele declara o que quiser — e o erro aparece quando alguém usa a
    tela, na forma de uma proposta para um campo que não existe. São três coisas:

    1. o formulário citado em `flow:` existe;
    2. todo campo em `writes:` existe NAQUELE formulário;
    3. todo campo em `writes:` é `ai: true` — propor para um campo que não aceita proposta é uma
       proposta que a pessoa não tem como aceitar.

    Devolve a lista em vez de levantar na primeira: quem edita um copiloto quer ver os três
    problemas de uma vez, não descobrir o segundo depois de corrigir o primeiro.
    """
    problemas: list[str] = []
    for alvo in copiloto.get("targets") or []:
        nome = alvo.get("flow")
        if not nome:
            problemas.append("um alvo sem `flow`")
            continue
        try:
            flow = load_flow(str(nome))
        except (FlowNotFound, FlowInvalid) as exc:
            problemas.append(f"alvo '{nome}': {exc}")
            continue
        campos = {c["id"]: c for s in flow["sections"] for c in s["fields"]}
        for campo in alvo.get("writes") or []:
            if campo not in campos:
                problemas.append(f"alvo '{nome}': o campo '{campo}' não existe nesse formulário")
            elif not campos[campo].get("ai"):
                problemas.append(
                    f"alvo '{nome}': o campo '{campo}' não é `ai: true` — o agente não pode propor nele"
                )
    return problemas
