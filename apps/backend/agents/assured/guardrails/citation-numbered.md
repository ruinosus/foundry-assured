---
# Application data — deliberately NOT AgentSchema (see grounded-citation.md).
#
# POR QUE ESTE ARQUIVO NÃO É COMPOSTO EM `metadata.x-foundry-assured.guardrails` DE NENHUM
# AGENTE — ao contrário dos outros arquivos desta pasta. O texto abaixo não é uma regra
# permanente de um agente publicado; é a instrução que o caminho `grounded` (RULE #4) cola
# JUNTO com os documentos recuperados, NA MESMA mensagem, a cada requisição —
# `app/modules/grounded/internal/grounded.py` (stream_grounded) e
# `.../retrieval_provider.py` (GroundedRetrieval, usado por helpdesk/retrieve, techdocs e
# selfwiki). É esse `[n]` numerado que sustenta a evidência clicável do frontend:
# `apps/frontend/lib/rehype-citations.ts` casa o `[n]` do texto renderizado com o campo
# `index` da citação — sem ele o painel de evidências não tem o que destacar.
#
# "Fornecidos abaixo" se refere aos documentos que vêm logo depois, NA MESMA mensagem de
# síntese. Compor este texto nas instructions ESTÁTICAS de um agente (publicadas no Foundry)
# quebraria essa proximidade — e techdocs.yaml/selfwiki.yaml já têm instrução própria de
# citação por componente/documento, que competiria com esta por citação numerada. Trocar o
# ponto de injeção é mudança de comportamento de modelo que não dá para medir sem credencial
# Azure (ausente neste ambiente) — então ele fica fora do escopo desta migração. O que muda
# aqui é só a FONTE do texto (RULE #7: documento, não literal em Python); o LOCAL de injeção
# em runtime permanece o mesmo.
name: citation-numbered
description: >-
  Numbered citation contract ([n]) the clickable evidence panel depends on — glued to the
  retrieved documents at synthesis time by the grounded archetype (helpdesk retrieve step,
  techdocs, selfwiki); not composed into any agent's static instructions (see the comment
  above for why).
severity: error
---
Responda APENAS com base nos DOCUMENTOS fornecidos abaixo — nunca use conhecimento próprio. Cite a fonte de cada afirmação pelo seu número entre colchetes, ex.: [1]. Se os documentos não contiverem a resposta, diga que não sabe.
