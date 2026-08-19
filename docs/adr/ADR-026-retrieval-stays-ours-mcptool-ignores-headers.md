# ADR-026 — A recuperação com ACL fica nossa: o `MCPTool` canônico ignora `headers`, medido

*Proposed.*

## Contexto

A MÁXIMA MAIOR deste repositório inverte o ônus da prova: se existe capacidade equivalente no
Azure / Foundry / AI Search / Agent Framework / MCP oficial, ela ganha do código nosso **por
definição** — escrever código próprio exige demonstrar que se procurou e não existe. Sob essa
régua, `app/modules/knowledge/internal/retrieval.py` (`retrieve()`, o seam único que todo domínio
grounded usa) é suspeito à primeira vista: ele busca com controle de acesso por documento, e o
Foundry oferece exatamente esse tipo de coisa de fábrica — um agente com a base de conhecimento
anexada via ferramenta MCP, que planeja, decompõe a pergunta, busca, reordena e sintetiza com
citações nativas. Sem uma medição registrada, a próxima leitura da MÁXIMA MAIOR concluiria,
corretamente, que `retrieval.py` deveria ser apagado a favor do caminho canônico.

Essa medição foi feita em 19/ago/2026 e só existia até agora no histórico de uma conversa. Esta
ADR a registra.

### O caminho canônico

Foi publicado no Foundry um agente de teste (`selfwiki-mcp-probe`) com a knowledge base anexada
via `MCPTool`, apontando para o endpoint MCP de `selfwiki-si-kb` — o caminho documentado pela
Microsoft: project connection do tipo `RemoteTool` com `ProjectManagedIdentity`, e
`allowed_tools=["knowledge_base_retrieve"]`.

O caminho canônico **funciona muito bem no que ele faz**. Depois que os documentos foram
carimbados com a ACL, o agente respondeu corretamente três perguntas que antes não sabia
responder — o planejamento, a decomposição da pergunta e a síntese com citações nativas
entregaram o que prometem. Esta ADR não é sobre ele ser ruim.

### O que ele não faz

O que ele não faz é aplicar ACL **por usuário**. Medido com a mesma pergunta, variando só o header
de identidade:

```
sem header de identidade              → 38 documentos recuperados
com o token do usuário                → 38 documentos recuperados
com um token deliberadamente INVÁLIDO → 38 documentos recuperados
```

O campo `headers` do `MCPTool` é **ignorado**. E, estruturalmente, ele fica gravado na versão
publicada do agente — então nem por requisição ele varia. Foi verificado também que passar a
ferramenta MCP **inline na requisição** (em vez de na versão publicada do agente), com o header
na própria chamada, não muda o resultado: os mesmos 38 documentos voltam de qualquer forma.

Para comparação, no mesmo dia e contra o mesmo índice (`selfwiki-docbundles-ks-index`, com
`permissionFilterOption: enabled`), o caminho próprio (`retrieve()` → `_native_retrieve`, que
carrega `x-ms-query-source-authorization`) filtrando com a identidade do chamador:

```
com a identidade do usuário → 5 trechos
sem identidade               → 0    (fail-closed)
com token inválido           → 401  (rejeitado pelo próprio Search)
```

O mesmo endpoint de busca, chamado por dois caminhos diferentes, discorda sobre se a identidade do
usuário importa. O caminho MCP do agente não a lê; a chamada direta ao Search a impõe.

## Decisão

**Manter `retrieval.py`** como o seam de recuperação de todo domínio grounded. Ele não é a
reimplementação que a MÁXIMA MAIOR proíbe — é a única forma medida de aplicar o trim por usuário
que a RULE #6 deste projeto exige ("controle de acesso é DADO — os grupos de leitura de cada
fonte — nunca lógica de classificação no código"). Um produto que serve documento com grupo de
leitura declarado não pode rotear por um caminho que ignora esse grupo. Isso coloca
`retrieval.py` ao lado da camada de assurance, na mesma exceção que o `CLAUDE.md` já calibra:
produto segue a máxima sem exceção, mas a peça que resolve citação e controla acesso é nossa
porque foi pesquisada e medida, não porque preferimos escrever.

**O que NÃO muda:** o planejamento/decomposição/síntese do agente continuam sendo trabalho do
framework em todo o resto do sistema — nada aqui reabre essa parte. A decisão é estritamente sobre
qual caminho decide **quais documentos entram no contexto do modelo**.

## Consequências

- **+** O trim por usuário continua correto e fail-closed (0 documentos sem identidade, 401 com
  token inválido) — o comportamento que a RULE #6 exige e que o caminho canônico, medido, não tem.
- **+** A leitura seguinte da MÁXIMA MAIOR encontra uma medição registrada em vez de precisar
  refazer o experimento (ou, pior, apagar `retrieval.py` por suspeita razoável e sem prova).
- **−** `retrieval.py` continua sendo código nosso a manter: dois motores (native KB retrieve +
  fallback de busca direta), decodificação de `docKey`, dedup — tudo fora do caminho que o
  Foundry mantém por nós.
- **−** A decisão depende do estado atual de uma peça de terceiro (`MCPTool.headers`). Nada aqui
  força a Microsoft a fechar essa lacuna.

### Gatilho de reavaliação

Revisitar esta decisão se **qualquer uma** destas condições passar a valer, verificada pela mesma
medição (variar o header de identidade, comparar a contagem de documentos):

- o `MCPTool` passar a honrar `headers` por requisição (a versão publicada do agente refletir o
  header, ou o inline reagir a ele);
- surgir qualquer outra forma documentada de passar a identidade do usuário ao endpoint MCP de
  uma knowledge base do Foundry (por exemplo, um parâmetro de escopo de identidade na conexão, ou
  suporte a OBO no `RemoteTool`).

Se qualquer uma ocorrer, o caminho canônico volta a ser candidato para os domínios grounded, e a
comparação deve ser refeita, não assumida.

## Referências

- `apps/backend/app/modules/knowledge/internal/retrieval.py` — o seam (`retrieve()`), com o
  `x-ms-query-source-authorization` como o mecanismo de trim por usuário
- `apps/backend/app/modules/knowledge/internal/secure_search.py` — a segunda camada de defesa em
  profundidade (trim client-side sobre a recuperação agêntica), mesmo motivo
- `CLAUDE.md` — MÁXIMA MAIOR (ônus da prova invertido) e RULE #6 (controle de acesso é dado)
- [MCP tools in Agent Framework / Foundry](https://learn.microsoft.com/agent-framework/) —
  `MCPTool`, `RemoteTool`, `ProjectManagedIdentity`, `allowed_tools`
- Medição de 19/ago/2026 — agente de teste `selfwiki-mcp-probe`, KB `selfwiki-si-kb`, índice
  `selfwiki-docbundles-ks-index` (`permissionFilterOption: enabled`)
