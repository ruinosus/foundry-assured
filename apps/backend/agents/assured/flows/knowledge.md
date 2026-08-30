---
type: formflow
title: "Nova base de conhecimento"
description: "O formulário de criação de base: identidade e alimentação, com o segundo passo travado até a base existir."
resource: knowledge
---

# Nova base de conhecimento

Duas coisas que este manifesto declara e os outros não: a procedência **não viaja** (o contrato de
criação não tem `metadata`), e a segunda seção fica **travada** até a primeira operação rodar — o
container onde os arquivos vão é derivado do nome.

## Spec

```yaml
# NULL, e dito. O contrato de criação da base não tem metadata, então a procedência do que o
# agente escreveu NÃO viaja com o recurso. O manifesto declara isso em vez de fingir que viaja.
provenance: null
provenanceNote: >-
  Este fluxo declara provenance: null. O contrato de criação da base não tem metadata, então a
  procedência do que o agente escreveu não viaja com o recurso.

sections:
  - id: identity
    title: Identidade
    help: A base precisa existir antes de receber conteúdo — o container vem do nome dela.
    fields:
      - id: name
        label: Nome
        type: text
        required: true
        ai: true
        placeholder: nome-da-base
        help: Mesma regra de nome de recurso.
        rules: [resourceName, max63, unique]
      - id: description
        label: Descrição
        type: text
        ai: true
        placeholder: o que existe nesta base
        help: >-
          É o texto que o AGENTE lê para decidir se consulta esta base — não é rótulo de vitrine.
          Dizer o que a base NÃO tem é o que evita consulta errada.

  - id: feed
    title: Alimentar
    optional: true
    lockedUntil: create_base
    lockedHelp: >-
      Travado até a base existir: o container onde os arquivos vão é derivado do nome. Publique a
      operação create_base primeiro.
    help: Por arquivos ou por repositório.
    fields:
      - id: files
        label: Arquivos
        type: files
        help: Enviados em multipart.
      - id: repo
        label: Repositório
        type: text
        placeholder: organizacao/repositorio
        help: Único caminho não-Microsoft deste produto.
      - id: token
        label: Token
        type: secret
        retain: false        # sai da memória do browser assim que a chamada termina
        placeholder: token de leitura

review:
  - label: Vai criar
    from: "a base {name} e o container derivado do nome"
  - label: Vai alimentar
    fromFiles: true
  - label: Procedência
    const: "não viaja: o contrato de criação não tem metadata"

plan:
  - id: create_base
    title: Criar base
    method: POST
    path: /api/foundry/knowledge
    approval: { required: true, role: Admin }
    note: o passo 2 depende desta operação
  - id: upload_files
    title: Enviar arquivos
    method: POST
    path: /api/foundry/knowledge/{name}/files
    encoding: multipart
    requires: [create_base]
  - id: import_repo
    title: Importar repositório
    method: POST
    path: /api/foundry/knowledge/{name}/github
    requires: [create_base]
    approval: { required: true, role: Admin, because: "lê token de terceiro" }
```
