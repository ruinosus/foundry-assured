---
# Application data — deliberately NOT AgentSchema (see grounded-citation.md).
name: mermaid-syntax
description: Sintaxe de diagrama que o parser aceita — regra transversal aos agentes que desenham, não texto repetido em cada um
severity: error
---
- Inclua um diagrama **Mermaid** quando a resposta envolver arquitetura ou fluxo de dados, sempre dentro de um bloco de código com a linguagem declarada (```mermaid).
- Envolva TODO rótulo em aspas duplas, em qualquer forma de nó: `A["Knowledge pipeline / KB"]`, `C{"Emite evento 'sources'"}`, `D["/api/source/{domain}/{name}"]`. Sem as aspas envolvendo, caracteres comuns em nomes de código encerram o rótulo cedo e o diagrama inteiro deixa de renderizar: `(` `)` `{` `}` `/` `:` `,` `&` `<` `>` `-`.
- Nunca use aspas duplas DENTRO do rótulo — use aspas simples. `C{"Emite "sources""}` quebra o parser; `C{"Emite 'sources'"}` funciona.
- Um diagrama que não parseia é pior que nenhum diagrama: ocupa o lugar da explicação e mostra ao usuário o erro cru do parser. Na dúvida entre um rótulo rico e um que parseia, escolha o que parseia e descreva o detalhe no texto ao redor.
