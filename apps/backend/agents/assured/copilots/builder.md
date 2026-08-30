---
type: copilot
title: "Assistente do formulário"
description: "O copiloto que ajuda a preencher os formulários de criação — propõe texto de campo, e nunca publica."
resource: builder
---

# Assistente do formulário

O primeiro copiloto declarado deste produto, e ele descreve algo que JÁ EXISTE: o assistente do
wizard, que hoje vive como agente (`agents/assured/builder.yaml`) mais um punhado de decisões
espalhadas em código — em quais telas ele aparece, em que campos pode escrever, o que ele nunca
faz.

Este documento não substitui o agente: o agente é QUEM RESPONDE (prompt, modelo), e o copiloto é
ONDE ELE ATUA e O QUE ELE PODE TOCAR. Um cita o outro em `engine.agent`.

## Spec

```yaml
# ONDE ele aparece. Fora das telas declaradas ele não existe — não há copiloto onipresente por
# acidente.
surface:
  mount: dock lateral
  screens: [/agents, /skills, /knowledge]
  openByDefault: false

# QUEM executa. O agente é outro documento; este copiloto se monta sobre ele sem código novo.
engine:
  agent: builder
  protocol: AG-UI
  # `backend`, não `foundry`: quem executa é o nosso adapter, porque este agente precisa enxergar
  # as tools do CLIENTE (`propose_field`) — e só o adapter oficial as repassa (medido). Dizer isso
  # é a SEGUNDA MÁXIMA: um recurso que mente sobre onde executa é pior que um recurso ausente.
  runtime: backend

# DE ONDE ele tira o que escreve. Vazio, e isso é uma afirmação: este agente não consulta base
# nenhuma (nenhuma tool de servidor), então o que ele declara como fonte é o que ele diz ter
# usado — e a tela mostra as fontes como fichas, não como links, exatamente por isso.
grounding:
  bases: []
  citation: optional
  refuseWithoutSource: false

# EM QUE CAMPOS ele escreve. O alvo é um `type: formflow` e os campos DELE — não uma lista
# inventada aqui. O gate prova que todo campo citado existe no formulário e é `ai: true`.
targets:
  - flow: agent
    writes: [name, description, instructions]
    validateAgainst: field.rules
  - flow: skill
    writes: [name, description, instructions]
    validateAgainst: field.rules
  - flow: knowledge
    writes: [name, description]
    validateAgainst: field.rules

tools:
  read: []
  # NENHUMA tool de escrita, e é o ponto do recurso: tudo que ele faz é propor. Uma tool de
  # escrita aqui transformaria o assistente do formulário numa via de publicação sem revisão — o
  # que a ADR-022 recusou.
  write: []

voice:
  language: pt-BR
  declareBeforeActing: true

measurement:
  record: POST /builder-assist/proposals
  outcomes: [accepted, edited, discarded]

policy: hitl
```
