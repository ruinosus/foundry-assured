---
type: formflow
title: "Nova skill"
description: "O formulário de criação de skill: identidade, instruções, arquivos e o plano de duas operações."
resource: skill
---

# Nova skill

A skill tem uma particularidade que o manifesto declara em vez de esconder: ela é publicada em
DUAS operações, e a segunda pode falhar com a primeira feita. `plan` diz isso, e a revisão conta.

## Spec

```yaml
provenance: metadata.provenance

sections:
  - id: identity
    title: Identidade
    help: Nome e descrição. Aqui a descrição é obrigatória — o serviço recusa a skill sem ela.
    fields:
      - id: name
        label: Nome
        type: text
        required: true
        ai: true
        placeholder: nome-da-skill
        help: Mesma regra de nome de recurso.
        rules: [resourceName, max63, unique]
      - id: description
        label: Descrição
        type: text
        required: true      # o SDK a declara opcional; o Foundry recusa sem ela
        ai: true
        placeholder: o que a skill faz
        help: Obrigatória pelo serviço — pedida aqui para não falhar na publicação.

  - id: instructions
    title: Instruções
    help: O procedimento que a skill executa, passo a passo.
    fields:
      - id: instructions
        label: Instruções
        type: longtext
        required: true
        ai: true
        rows: 9
        placeholder: "Para reverter um deploy…"
        help: Vira o conteúdo da versão default da skill.

  - id: files
    title: Arquivos
    optional: true
    help: Scripts que a skill executa e referências que ela consulta. O grupo vira pasta no bundle.
    fields:
      - id: scripts
        label: scripts
        type: files
        rules: [safeFilename]
        help: Nome de arquivo sem barra, sem ponto inicial.
      - id: references
        label: references
        type: files
        rules: [safeFilename]
        help: Documentos que a skill cita.

review:
  - label: Vai criar
    from: "a skill {name} com a versão default inline"
  - label: Vai anexar
    fromFiles: true
  - label: Se falhar
    const: "a skill já existirá e só o bundle falha — a tela diz as duas coisas, para você não tentar criar de novo"

plan:
  - id: create_skill
    title: Criar skill e versão default
    method: POST
    path: /api/foundry/skills/{name}
    approval: { required: true, role: Admin }
    note: instruções inline; obrigatória antes do bundle
  - id: upload_bundle
    title: Subir bundle de arquivos
    method: POST
    path: /api/foundry/skills/{name}
    encoding: multipart
    requires: [create_skill]      # a dependência é DADO
    onFailure: partialSucceeded   # e a falha parcial também
    note: depende de create_skill; falha aqui deixa a skill criada
```
