"""Frontmatter YAML de um documento de conhecimento: separar do corpo, ler o que declara.

POR QUE ISTO É UM MÓDULO. A mesma separação já existia em `adapt_openwiki._split_front_matter` e
em `tests/knowledge/session_container_test`, e o ingest do corpus ia virar a terceira cópia. Três
parsers do mesmo formato divergem no primeiro formato novo — e divergem em SILÊNCIO, porque cada
um simplesmente deixa de ver o que o outro vê.

O CONTRATO DE ACESSO, que é o motivo de `declared_groups` existir separado de `parse`:

    chave AUSENTE  → None → "esta fonte não declara acesso" (quem consome decide)
    `groups: []`   → []   → "declara que NENHUM grupo lê" (fail-closed explícito)

`None ≠ []` é a mesma distinção que o `docbundle.schema.json` carrega e que
`ingest_docbundles` já respeita. Colapsar as duas é como um bundle sem ACL vira um bundle
aberto: a ausência de declaração passa a ser lida como permissão.
"""

from __future__ import annotations

import re

import yaml

_BLOCO = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


def split(texto: str) -> tuple[str, str]:
    """(frontmatter cru, corpo). Sem bloco inicial, devolve ("", texto)."""
    m = _BLOCO.match(texto)
    return (m.group(1), texto[m.end() :]) if m else ("", texto)


class FrontmatterInvalido(ValueError):
    """Existe um bloco `---` … `---`, e ele não é um mapa YAML válido."""


def parse(texto: str) -> tuple[dict, str]:
    """(metadados, corpo). Sem bloco → ({}, texto). Bloco QUEBRADO → levanta.

    LEVANTAR É O PONTO. A primeira versão devolvia `{}` para um bloco torto, e aí "escrevi
    `groups:` errado" ficava indistinguível de "não declarei acesso" — os dois liam como
    ausência, e ausência é o que o consumidor interpreta como "decide você". Um erro de digitação
    num YAML viraria permissão em silêncio, que é exatamente o modo de falha que a Regra #6
    existe para impedir.

    Quem só quer o corpo (levantar um título, indexar o texto) usa `split`, que não interpreta
    nada. Quem lê METADADO usa `parse` e aceita falhar alto."""
    cru, corpo = split(texto)
    if not cru.strip():
        return {}, corpo
    try:
        dados = yaml.safe_load(cru)
    except yaml.YAMLError as exc:
        raise FrontmatterInvalido(f"frontmatter não é YAML válido: {exc}") from exc
    if not isinstance(dados, dict):
        raise FrontmatterInvalido(f"frontmatter não é um mapa, e sim {type(dados).__name__}")
    return dados, corpo


def declared_groups(meta: dict) -> list[str] | None:
    """Os grupos que a FONTE declara poder ler o documento — ou None se ela não declara.

    Aceita `groups: [a, b]`, `groups:\\n  - a`, e `groups: a` (um só, sem lista). Valor presente
    mas de tipo inesperado vira `[]` (fail-closed): declarar errado não pode virar "sem
    restrição"."""
    if "groups" not in meta:
        return None
    valor = meta["groups"]
    if valor is None:
        return []
    if isinstance(valor, str):
        return [valor.strip()] if valor.strip() else []
    if isinstance(valor, (list, tuple)):
        return [str(g).strip() for g in valor if str(g).strip()]
    return []
