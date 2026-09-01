# Glossário

## mcp-binding

Documento OKF do perfil `x-foundry-authoring` que liga uma intenção a um Toolbox do Foundry ou, excepcionalmente, a um servidor MCP direto aprovado. Ele referencia recursos oficiais e nunca armazena segredo.

## snapshot de descoberta

Evidência imutável de uma execução de `tools/list`, contendo identidade do servidor, versão do protocolo, tools, schemas, annotations, instante e hash. Não é catálogo operacional nem prova de autorização.

## drift de tool

Diferença entre o snapshot revisado e uma descoberta posterior, como remoção da tool, alteração de schema ou mudança de classificação.

## quarentena de tool

Estado que impede promoção e execução de uma tool específica até nova descoberta, classificação administrativa e revisão por Admin. As demais tools do binding podem continuar disponíveis quando não sofreram drift.

## classificação administrativa

Decisão tenant-local, feita somente por Admin, que classifica uma tool como leitura ou escrita. Sinais declarados pelo servidor não substituem essa decisão; o resultado mais restritivo sempre vence.
