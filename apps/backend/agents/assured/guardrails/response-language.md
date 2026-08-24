---
# Application data — deliberately NOT AgentSchema (see grounded-citation.md).
name: response-language
description: O idioma da resposta segue quem pergunta — regra transversal, não texto repetido em cada agente
severity: error
---
- Responda no idioma do usuário. Se a preferência de idioma vier nas instruções desta requisição, siga-a; caso contrário, responda no mesmo idioma da pergunta.
- O idioma da resposta NÃO muda o idioma das citações: cite o trecho e o nome do documento exatamente como estão na fonte. Traduzir uma citação destrói a procedência, que é o produto.
