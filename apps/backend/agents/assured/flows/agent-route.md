---
type: formflow
title: "Nova proposta de agente"
description: "Escolha uma rota de autoria e registre um agent-binding sem publicar ou executar o recurso."
resource: agent-binding
---

# Nova proposta de agente

As três rotas produzem o mesmo tipo autorável. O que muda é a definição externa referenciada e
onde ela poderá executar depois de publicada e materializada.

## Spec

```yaml
sections:
  - id: route
    title: Rota de autoria
    help: A escolha define a fonte da implementação; esta etapa registra somente o contrato.
    fields:
      - id: authoring_route
        label: Rota
        type: choice
        required: true
        initial: prompt
        options: [prompt, workflow, container]
        help: Prompt roda no Foundry; workflow depende do harness do backend; container depende de imagem e implantação próprias.

  - id: identity
    title: Identidade do binding
    fields:
      - id: name
        label: Nome
        type: text
        required: true
        ai: true
        placeholder: agente-de-suporte
        rules: [resourceName, max63]
      - id: version
        label: Versão pretendida
        type: text
        required: true
        initial: "1"
        help: A publicação futura criará ou selecionará esta versão; nada é publicado agora.
      - id: justification
        label: Justificativa
        type: longtext
        required: true
        ai: true
        rows: 4

  - id: implementation
    title: Referência técnica
    help: A referência identifica a definição externa; código e credenciais nunca entram no documento.
    fields:
      - id: prompt_definition
        label: Documento AgentSchema
        type: text
        required: true
        rules: [agentSchemaReference]
        placeholder: agents/assured/meu-agente.yaml
        visibleWhen: { field: authoring_route, equals: prompt }
      - id: workflow_definition
        label: Documento de workflow
        type: text
        required: true
        rules: [workflowReference]
        placeholder: workflows/meu-fluxo.yaml
        visibleWhen: { field: authoring_route, equals: workflow }
        help: O documento pode ser revisado e publicado como contrato; F05 não o apresenta como executável.
      - id: container_image
        label: Referência da imagem
        type: text
        required: true
        rules: [containerImageReference]
        placeholder: registry.example/app@sha256:...
        visibleWhen: { field: authoring_route, equals: container }
        help: Apenas a referência imutável é registrada; build, credencial e implantação ficam fora do ChangeSet.

review:
  - label: Binding
    from: "agent-binding {name} na versão {version}"
  - label: Rota
    from: "{authoring_route}"
  - label: Execução
    const: "Esta proposta não publica nem executa o recurso."

plan:
  - id: prepare_changeset
    title: Preparar proposta para o ChangeSet
    note: a interface salva o documento proposed pelo contrato de autoria; nenhuma capacidade é publicada ou executada
```