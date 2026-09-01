---
type: formflow
title: "Novo copiloto"
description: "O formulário que cria um copiloto — renderizado pelo mesmo motor que ele mesmo vai usar."
resource: copilot
---

# Novo copiloto

O formulário que cria um copiloto é ele mesmo um `type: formflow`, renderizado pelo mesmo motor.
Não é elegância: é o teste. Se o motor não desse conta de descrever o próprio produto, ele não
daria conta do quarto domínio que alguém quisesse acrescentar.

**Os alvos não são digitados.** `catalog: /api/flows/-/writable-fields` traz a lista dos campos
`ai: true` dos formulários que EXISTEM — declarar um alvo inválido deixa de ser possível, porque
a opção não está lá. Um campo de texto aqui aceitaria `agent.instrucoes` (que não existe) e
`agent.model` (que existe e não aceita proposta), e o erro só apareceria quando alguém usasse o
copiloto.

## Spec

```yaml
provenance: null
provenanceNote: >-
  O copiloto é um documento do bundle, não um recurso do Foundry — não há metadata onde a
  procedência viaje. O que o agente escrever aqui fica no documento, e o documento fica no
  repositório, onde o histórico é o do git.

sections:
  - id: identity
    title: Identidade
    help: O identificador vira o caminho do documento. O título e a frase são o que outra pessoa lê para saber se este copiloto serve.
    fields:
      - id: name
        label: Identificador
        type: text
        required: true
        ai: true
        placeholder: atendimento-rh
        help: Minúsculas, números e hífens no meio — ele é o nome do arquivo.
        rules: [resourceName, max63]
      - id: title
        label: Título
        type: text
        required: true
        ai: true
        placeholder: Copiloto de RH
      - id: description
        label: Uma frase
        type: text
        ai: true
        help: O que ele faz, em uma linha. É o que aparece no catálogo.

  - id: surface
    title: Onde ele atua
    help: Superfície e telas. Fora das telas declaradas ele não existe — não há copiloto onipresente por acidente.
    fields:
      - id: mount
        label: Monta como
        type: choice
        required: true
        initial: dock lateral
        options: [dock lateral, console, ancorado no campo, página própria]
      - id: screens
        label: Nas telas
        type: multi
        options: [/agents, /skills, /knowledge, /usecases, /copilots]

  - id: engine
    title: Quem executa
    help: O agente é outro documento. O copiloto se monta sobre ele sem código novo.
    fields:
      - id: agent
        label: Agente
        type: text
        required: true
        placeholder: builder
        help: O nome do documento de agente que responde por este copiloto.
      - id: runtime
        label: Runtime
        type: choice
        required: true
        initial: backend
        options: [backend, foundry]
        help: >-
          Onde ele EXECUTA de verdade. Um recurso que mente sobre isso é pior que um recurso
          ausente — a tela mostra o que este campo diz.

  - id: targets
    title: Em que campos ele escreve
    optional: true          # um copiloto sem alvo conversa e não escreve — é válido
    help: >-
      A lista vem dos formulários publicados, não deste formulário. Só aparecem campos que aceitam
      proposta; declarar um alvo que não existe deixa de ser possível.
    fields:
      - id: writes
        label: Campos
        type: multi
        catalog: { source: /api/flows/-/writable-fields, key: fields }
        emptyHelp: Nenhum formulário publicado declara campo que aceite proposta.

review:
  - label: Vai criar
    from: "o copiloto {name} — {title}"
  - label: Vai aparecer
    from: "como {mount}, nas telas {screens}"
  - label: Vai poder escrever
    fromCapabilities: true
    # DECLARADO: sem esta linha a revisão varreria todo campo de escolha e diria "vai poder
    # escrever: dock lateral, backend" — que são a superfície e o runtime, não alvos.
    fields: [writes]
  - label: Não vai poder
    const: "escrever sem gesto humano, nem tocar campo fora dos alvos declarados"

plan:
  - id: montar_documento
    title: Montar o documento OKF
    note: >-
      Sem chamada de serviço. O copiloto é um documento do bundle, e a saída desta tela é o
      documento — não um push.
```
