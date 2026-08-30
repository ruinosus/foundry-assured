---
type: policy
title: "HITL — um gate, quatro lugares"
description: "A política de decisão humana, herdada por todo copiloto e todo formulário do bundle."
resource: hitl
---

# hitl.md

Os quatro gates num bloco só. Herdado por todo `type: copilot` e todo `type: formflow` deste
bundle — não copiado. Um gate copiado em N documentos diverge no primeiro que alguém editar, e a
divergência não dá erro: só faz um caminho ficar mais frouxo que o outro sem ninguém decidir isso.

## Spec

```yaml
hitl:
  # 1 · o agente PROPÕE um campo; quem decide é a pessoa.
  fieldProposal:
    tool: propose_field
    # A tool responde NA HORA e não fica pendente. Medido: o caminho do Foundry é stateful, e uma
    # chamada pendente faz a requisição seguinte levar uma função sem resultado — o serviço recusa
    # com "No tool output found for function call". O trabalho do agente é propor; se a pessoa
    # aceita não é assunto do turno dele.
    respond: immediately
    decide: [use, edit, discard]
    validateAgainst: field.rules
    record: POST /builder-assist/proposals

  # 2 · toda operação que publica passa por aprovação, com o papel declarado na própria operação.
  publishOperation:
    approval: always
    show: payload          # o payload EXIBIDO é o que será executado, nunca um resumo
    role: from(operation.approval.role)

  # 3 · tool de escrita do agente publicado nasce exigindo aprovação.
  agentWriteTool:
    require_approval: always
    role: Approver

  # 4 · a escalação do workflow para numa pessoa.
  workflowEscalation:
    interrupt: request_info
    editable: [summary]
    # Recusar EXIGE motivo: uma recusa em branco obriga quem pediu a adivinhar o que corrigir, e o
    # modelo a tentar de novo igual. A trilha registra QUE houve motivo e o tamanho, nunca o texto.
    rejectReason: required
```
