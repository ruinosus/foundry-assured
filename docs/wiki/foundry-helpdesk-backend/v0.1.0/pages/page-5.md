## Base de Conhecimento e Ingestão (Knowledge)

Visão geral
- Objetivo: construir e ingerir uma base de conhecimento (KB) de runbooks e políticas internas para suporte — fase de ingestão descrita em app/knowledge/ingest.py. (app/knowledge/ingest.py)  
- Por que: o código cria um *knowledge source* que permite auto-chunking e embeddings e há um componente separado que aplica ACLs documentais no índice de busca. (app/knowledge/ingest.py) (app/knowledge/acl_setup.py)  
- Escopo desta página: fluxo de ingestão, formato de bundle gerado pelo adaptador deep-wiki, e a aplicação de ACLs documentais na camada de busca. (app/knowledge/ingest.py) (app/knowledge/adapt_deepwiki.py) (app/knowledge/acl_setup.py)

Resumo rápido
| Área | O que faz | Artefato principal | Fonte |
|------|----------:|-------------------|-------|
| Upload do corpus | Envia .md → Blob Storage | blobs no container configurado | (app/knowledge/ingest.py) |
| Fonte de conhecimento | Registra AzureBlobKnowledgeSource (configura embedding deployment) | knowledge source `helpdesk-runbooks-ks` | (app/knowledge/ingest.py) |
| Knowledge base | Cria objeto KnowledgeBase com modelo e instruções de resposta | KnowledgeBase via SDK | (app/knowledge/ingest.py) |
| Adaptação Copilot deep-wiki | Converte `wiki/**/*.md` → bundle ingestível | `manifest.json`, `pages/page-N.md`, `llms.txt` | (app/knowledge/adapt_deepwiki.py) |
| ACL por documento | Adiciona campo `groups` no índice e popula grupos por documento | script `setup_acl()` | (app/knowledge/acl_setup.py) |

Arquitetura (visão de alto nível)
- Componentes observáveis no código:
  - Corpus: arquivos markdown em app/knowledge/corpus (`CORPUS_DIR`). (app/knowledge/ingest.py)
  - Blob container: destino onde cada `.md` é enviado via BlobServiceClient. (app/knowledge/ingest.py)
  - Knowledge Source: `AzureBlobKnowledgeSource` apontando para o container, configurado para usar o endpoint de embedding e o deployment definido nas settings. (app/knowledge/ingest.py)
  - Knowledge Base: objeto `KnowledgeBase` que inclui modelos (Azure OpenAI parameters) e instruções de resposta. (app/knowledge/ingest.py)
  - Índice de busca: script que adiciona o campo `groups` ao índice e controla `permissionFilterOption`. (app/knowledge/acl_setup.py)
  - Ingest bundle: estrutura `<out>/<component>/<version>/{manifest.json, pages/, llms.txt}` escrita pelo adaptador deep-wiki. (app/knowledge/adapt_deepwiki.py)

Componentes detalhados

Resumo das peças e onde olhar no código
| Componente | Responsabilidade | Ponto no repositório |
|-----------|------------------|----------------------|
| Upload corpus | Envia todos os `corpus/*.md` para o container configurado | (app/knowledge/ingest.py) |
| Criar knowledge source | Registra `AzureBlobKnowledgeSource` com parâmetros de embedding | (app/knowledge/ingest.py) |
| Criar knowledge base | Cria `KnowledgeBase` com modelo e `answer_instructions` | (app/knowledge/ingest.py) |
| Adaptação Deep-Wiki | Converte output do Copilot CLI (`wiki/**/*.md`, `llms.txt`) para o bundle de ingest | (app/knowledge/adapt_deepwiki.py) |
| ACL por documento | Adiciona campo `groups` ao índice e popula grupos por documento (merge/upload) | (app/knowledge/acl_setup.py) |

Detalhes por componente

1) Upload do corpus
- O que: `upload_corpus(credential: TokenCredential) -> int` envia cada `.md` presente em `CORPUS_DIR` para o container configurado; aborta se não houver arquivos. (app/knowledge/ingest.py)  
- Como: usa `BlobServiceClient(account_url=..., credential=credential)` e `container_client.upload_blob(..., overwrite=True)`. (app/knowledge/ingest.py)  
- Observação de contexto: o módulo documenta que a autenticação é feita com `DefaultAzureCredential` ao longo do script. (app/knowledge/ingest.py)

2) Criando a Knowledge Source e Knowledge Base
- `create_knowledge_source(index_client)` constrói um `AzureBlobKnowledgeSource` com `KnowledgeSourceIngestionParameters` que referenciam o endpoint de embedding e o deployment configurado em settings. (app/knowledge/ingest.py)  
- `create_knowledge_base(index_client)` cria um `KnowledgeBase` com `KnowledgeBaseAzureOpenAIModel` e define `answer_instructions` (o trecho disponível mostra essas construções). (app/knowledge/ingest.py)  
- As chamadas de criação/atualização usam um wrapper `_with_timeout` para impor um tempo limite de chamada. (app/knowledge/ingest.py)

3) Adaptação Deep-Wiki → Bundle de ingestão
- Propósito: adaptar a saída do plugin `deep-wiki` em um bundle consumível pelo pipeline de ingest descrito no repositório. (app/knowledge/adapt_deepwiki.py)  
- Função chave: `adapt(repo: Path, component: str, version: str, out_dir: Path, wiki_dir: str | None, language: str) -> Path` — resolve o diretório wiki, ordena páginas (usa `llms.txt` quando presente) e escreve `pages/page-N.md`, `manifest.json` e `llms.txt` no bundle. (app/knowledge/adapt_deepwiki.py)  
- Regras de ordenação: `_ordered_pages` processa `llms.txt` procurando links Markdown para `.md` (regex `_LINK_RE`) e, se não houver `llms.txt`, retorna as páginas ordenadas alfabeticamente. (app/knowledge/adapt_deepwiki.py)  
- O `manifest` escrito inclui campos como `key`, `title`, `source`, `language`, `model` (setado como `"github-copilot-cli/deep-wiki"` no adaptador), `generatedAt`, `component`, `componentVersion` e a lista `pages`. (app/knowledge/adapt_deepwiki.py)

4) Controle de acesso documental (ACL)
- Princípio no cabeçalho do módulo: "document-level ACL on the KB index (access follows the SOURCE)". O código não realiza classificação — aplica os grupos declarados pela origem ou por um mapa externo. (app/knowledge/acl_setup.py)  
- Campo no índice: se o campo `groups` não existir, o script adiciona um campo com `"type": "Collection(Edm.String)"`, `filterable: True`, `retrievable: True`, `searchable: False` e `permissionFilter: "groupIds"`, e usa `permissionFilterOption` para habilitar/desabilitar a filtragem. (app/knowledge/acl_setup.py)  
- Resolução de nomes: `_resolve(names)` converte nomes de grupo para IDs (GUIDs) usando `settings.acl_group_map`; entradas que já são GUIDs passam direto; nomes desconhecidos são descartados. (app/knowledge/acl_setup.py)  
- Fonte externa: `_load_external()` lê JSON a partir de `COCKPIT_ACL_CLASSIFICATION` (variável de ambiente) ou `settings.cockpit_acl_classification`, retornando um mapa `{ document-key: [group-name,…] }` quando presente. (app/knowledge/acl_setup.py)  
- Janela de manutenção: o script desabilita a opção de permissão (`permissionFilterOption = "disabled"`) antes de escrever os grupos e re-habilita (`"enabled"`) no bloco `finally`. (app/knowledge/acl_setup.py)  
- Comportamento de fail-closed: o código contabiliza documentos cuja lista de IDs resolvidos fica vazia (`fail_closed` incrementado) e grava o campo `groups` (que pode ser lista vazia) no lote; quando a filtragem de permissões está habilitada, documentos sem grupos resolvíveis ficam invisíveis nas consultas autorizadas. (app/knowledge/acl_setup.py)  
- Extração de chave do componente: `_component(blob_url)` deriva uma chave determinística do nome do blob segundo regras definidas no código (remoção de `.md` sufixos, split por `__`, e canonicalização). (app/knowledge/acl_setup.py)

Trajeto de código: como os grupos são aplicados (resumido)
1. Carrega `component_groups` passado a `setup_acl(...)` ou usa `_load_external()`. (app/knowledge/acl_setup.py)  
2. Obtém um token via `DefaultAzureCredential().get_token(_SEARCH_SCOPE).token`. (app/knowledge/acl_setup.py)  
3. Lê o índice (`GET indexes/{index}`). (app/knowledge/acl_setup.py)  
4. Se `groups` não existir, acrescenta o campo e chama `_set_option(token, index, "enabled")`. (app/knowledge/acl_setup.py)  
5. Chama `_set_option(..., "disabled")` antes de atualizar documentos. (app/knowledge/acl_setup.py)  
6. Enumera documentos via paginação `GET indexes/{index}/docs?...&$select=uid,blob_url`. (app/knowledge/acl_setup.py)  
7. Para cada doc: calcula `key = _component(blob_url)`, obtém nomes `names = access.get(key, default_groups)`, resolve IDs `gids = _resolve(names)`, e adiciona item `{"@search.action":"mergeOrUpload","uid":uid,"groups":gids}` a um lote. (app/knowledge/acl_setup.py)  
8. Envia batches via `POST indexes/{index}/docs/index` e, no `finally`, reativa a filtragem com `_set_option(..., "enabled")`. (app/knowledge/acl_setup.py)

Observações e exemplos práticos
- `_component` normaliza nomes de blob conforme a função e sua docstring; manifeste `key` gerado pelo adaptador é `f"{component}-{version}"` — o adaptador grava `pages/page-N.md` e `manifest.json` nesse padrão. (app/knowledge/acl_setup.py) (app/knowledge/adapt_deepwiki.py)  
- O módulo de ingest refere-se a variáveis e campos em `app.core.settings` (por exemplo `azure_storage_account`, `azure_storage_container`, `azure_storage_resource_id`, `azure_ai_openai_endpoint`, `foundry_embedding_model`, `foundry_model`, `azure_search_knowledge_base`). (app/knowledge/ingest.py)  
- `_with_timeout` envolve chamadas SDK com um executor de thread e chama `os._exit(1)` se a chamada exceder o tempo limite configurado. (app/knowledge/ingest.py)

Exemplos de documentos do corpus (amostra)
- app/knowledge/corpus/oncall-handoff.md — runbook de handoff de on-call. (app/knowledge/corpus/oncall-handoff.md)  
- app/knowledge/corpus/deploy-rollback-procedure.md — runbook de rollback. (app/knowledge/corpus/deploy-rollback-procedure.md)  
- app/knowledge/corpus/local-dev-environment-setup.md — setup local para desenvolvedores. (app/knowledge/corpus/local-dev-environment-setup.md)

Checklist operacional (passos para rodar, conforme os scripts)
1. Configure os valores referenciados em settings / variáveis de ambiente exigidas pelo script de ingest (ex.: `AZURE_STORAGE_ACCOUNT`, `AZURE_STORAGE_RESOURCE_ID`, `AZURE_AI_OPENAI_ENDPOINT`, além dos nomes de deployment usados nas settings: `foundry_embedding_model`, `foundry_model`, etc.). (app/knowledge/ingest.py)  
2. Suba a infraestrutura conforme a instrução do módulo (o cabeçalho do script indica rodar *after* `azd up`). (app/knowledge/ingest.py)  
3. Execute o ingest: `uv run python -m app.knowledge.ingest`. (app/knowledge/ingest.py)  
4. Se usar Copilot deep-wiki, gere o bundle com `app.knowledge.adapt_deepwiki.adapt(...)` (o script `app/knowledge/adapt_deepwiki.py` tem um `main()` para CLI). (app/knowledge/adapt_deepwiki.py)  
5. Rode o script de ACL para povoar `groups` no índice: `uv run python -m app.knowledge.acl_setup`. (app/knowledge/acl_setup.py)

Riscos e modos de falha (e evidências no código)
- Chamadas SDK que demoram demais são protegidas por `_with_timeout`, que encerra o processo em caso de timeout. (app/knowledge/ingest.py)  
- Documentos sem grupos resolvíveis são contabilizados em `fail_closed` e recebem uma lista vazia de `groups` no lote; com a opção de filtragem habilitada, ficam invisíveis para consultas sujeitas ao filtro. (app/knowledge/acl_setup.py)  
- `_resolve()` depende de `settings.acl_group_map` para mapear nomes para IDs; nomes desconhecidos são descartados. (app/knowledge/acl_setup.py)  
- `_validate_storage_resource_id` valida o formato de `AZURE_STORAGE_RESOURCE_ID` e aborta com instrução se o valor não estiver no formato esperado. (app/knowledge/ingest.py)

Referências (arquivos citados)
- Upload / criação de KB e sources: (app/knowledge/ingest.py)  
- Timeout / logging helpers: (app/knowledge/ingest.py)  
- Adaptação deep-wiki → bundle: (app/knowledge/adapt_deepwiki.py)  
- Document-level ACL setup e `_component` / `_resolve` logic: (app/knowledge/acl_setup.py)  
- Exemplos de documentos no corpus: (app/knowledge/corpus/*.md)

Observação final
- Esta página foi ajustada para conter apenas afirmações diretamente suportadas pelos arquivos fornecidos: app/knowledge/ingest.py, app/knowledge/adapt_deepwiki.py, app/knowledge/acl_setup.py e os arquivos em app/knowledge/corpus/. (app/knowledge/ingest.py) (app/knowledge/adapt_deepwiki.py) (app/knowledge/acl_setup.py)