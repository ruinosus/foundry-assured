---
type: formflow
title: "Novo agente"
description: "O formulário de criação de agente: seções, campos, regras, revisão legível e plano de publicação."
resource: agent
---

# Novo agente

O que a tela renderiza vem daqui. Nenhum campo, rótulo, regra ou linha de revisão está escrito
no componente — trocar este documento troca o wizard inteiro.

## Spec

```yaml
provenance: metadata.provenance   # os campos escritos pelo agente viajam por aqui (OKF v0.2)

sections:
  - id: identity
    title: Identidade
    help: Como o recurso se chama no projeto. O nome é a chave e não muda depois.
    fields:
      - id: name
        label: Nome
        type: text
        required: true
        ai: true
        placeholder: nome-do-agente
        help: Letras minúsculas, números e hífens no meio — por exemplo, suporte-rh.
        rules: [resourceName, max63, unique]
      - id: description
        label: Descrição da versão
        type: text
        ai: true
        placeholder: opcional
        help: Aparece no catálogo e no histórico de versões.

  - id: behavior
    title: Comportamento
    help: O que o agente faz e como responde. Escreva como quem explica a um colega novo.
    fields:
      - id: instructions
        label: Instruções
        type: longtext
        required: true
        ai: true
        rows: 9
        placeholder: "Você responde dúvidas de RH citando a política de origem…"
        help: É o texto que o modelo recebe em cada resposta.
      - id: model
        label: Modelo (deployment)
        type: text
        required: true
        initial: gpt-5-mini
        help: Nome do deployment como aparece no portal.

  - id: capabilities
    title: Capacidades
    optional: true          # opcional NUNCA trava — a regra do produto, dita no manifesto
    help: O que este agente pode alcançar. Sem nenhuma capacidade ele responde só do modelo, sem fonte.
    fields:
      - id: knowledge_base
        label: Base de conhecimento
        type: choice
        # O catálogo vem do serviço, não de uma lista aqui: duas listas divergem no primeiro
        # item novo, e a que diverge em silêncio é a da tela (SEGUNDA MÁXIMA).
        catalog: { source: /api/foundry/knowledge, key: bases }
        help: O agente busca nesta base e cita o documento de origem.
        emptyHelp: Nenhuma base criada ainda — crie uma em Conhecimento para o agente poder citar fontes.
      - id: toolbox
        label: Toolbox
        type: choice
        catalog: { source: /api/foundry/toolboxes, key: toolboxes }
        help: >-
          O toolbox é um servidor MCP e o agente o alcança pela URL — mas o endpoint exige uma
          connection do projeto para autenticar. Sem ela, o agente falha na primeira chamada.
          Verificado em teste.
        emptyHelp: Nenhum toolbox criado ainda. Um toolbox agrupa ferramentas e skills.
      - id: tools
        label: Ferramentas prontas
        type: multi
        # Verificadas no SDK: cada uma tem `type` como ÚNICO campo obrigatório. Oferecer aqui uma
        # que precise de configuração produziria um agente que falha na primeira chamada.
        options: [code_interpreter, web_search, image_generation]
      - id: mcp
        label: Servidor MCP externo
        type: pair
        parts:
          - { id: label, placeholder: rótulo }
          - { id: url, placeholder: "https://…/mcp" }
        help: >-
          Para um servidor MCP fora do Foundry. Ações de escrita nascem exigindo aprovação — mas
          quem aplica isso é o runtime do agente, não o servidor.

review:
  - label: Vai criar
    from: "o agente {name} e a sua primeira versão"
  - label: Vai responder
    from: "com {model} — sem base, então nenhuma resposta terá fonte"
    variant:
      when: knowledge_base
      then: "com {model}, buscando em {knowledge_base} e citando a fonte"
  - label: Vai poder
    fromCapabilities: true
  - label: Não vai poder
    const: "abrir chamado nem escrever sem aprovação do papel Approver"

plan:
  - id: create_agent
    title: Criar agente e publicar versão
    method: POST
    path: /api/foundry/agents/{name}
    approval: { required: true, role: Admin }
    note: cria o recurso e a versão 1
```
