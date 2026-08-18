---
title: 'Design: bases de conhecimento gerenciáveis pelo usuário (GitHub + upload)'
description: Permitir que o usuário crie, liste e remova bases de conhecimento a partir de arquivos enviados e de repositórios GitHub, e transformar as bases atuais (helpdesk, selfwiki) em entradas da mesma lista. Levantamento do que a plataforma Microsoft já resolve, feito ANTES de desenhar — três dos quatro pedidos são cola pura sobre o SDK oficial; o quarto (GitHub) é a única peça sem equivalente de primeira parte.
type: design
audience: contributor
status: draft
updated: 2026-08-17
---

# Bases de conhecimento gerenciáveis pelo usuário

## O pedido

O usuário quer adicionar, remover e criar bases de conhecimento — a partir de **repositórios
GitHub** e de **arquivos enviados** — e quer que as bases que hoje existem em código
(`helpdesk`, `selfwiki`) apareçam na mesma lista.

## Como esta spec foi escrita

Pela MÁXIMA MAIOR do `CLAUDE.md`: pesquisar primeiro, escrever depois, e só a cola. O
levantamento abaixo veio do **SDK instalado** (`azure-search-documents 11.7.0b2`, fonte de
verdade sobre a versão em uso) e da documentação oficial — não de memória.

## O que a plataforma já resolve

### Gestão de bases: 100% coberta

`SearchIndexClient` já expõe o CRUD completo, para base e para fonte:

```
create_knowledge_base            create_knowledge_source
create_or_update_knowledge_base  create_or_update_knowledge_source
delete_knowledge_base            delete_knowledge_source
get_knowledge_base               get_knowledge_source
list_knowledge_bases             list_knowledge_sources
                                 get_knowledge_source_status
```

**Nenhuma lógica de gestão precisa ser escrita.** Criar, listar, remover e consultar status são
chamadas de método. O que escrevemos são endpoints HTTP que repassam — e nada mais.

### Tipos de fonte de primeira parte

Seis, todos prontos no SDK:

| Tipo | Cobre |
|---|---|
| `AzureBlobKnowledgeSource` | **arquivos enviados** ✓ |
| `SearchIndexKnowledgeSource` | envelopar um índice existente ✓ |
| `IndexedSharePointKnowledgeSource` | SharePoint indexado |
| `RemoteSharePointKnowledgeSource` | SharePoint via Copilot Retrieval API |
| `IndexedOneLakeKnowledgeSource` | Fabric / OneLake |
| `WebKnowledgeSource` | web pública (Bing) |

O blob source faz **chunking, embedding e indexação sozinho** (integrated vectorization,
`KnowledgeSourceIngestionParameters.embedding_model`). Não escrevemos nada disso hoje e não
passaremos a escrever.

### Upload: dois caminhos oficiais

1. **Blob + knowledge source** — o que o repositório já faz. Traz ACL por documento e retrieval
   agêntico; custa o serviço de Search (~US$73/mês por estar ligado).
2. **Vector store do Foundry** — via `AIProjectClient.get_openai_client()` → `files` +
   `vector_stores`. Dispensa o AI Search, cobra US$0,11/GB/dia com 1 GB grátis, mas **não tem
   ACL por documento** nem retrieval agêntico.

A escolha entre os dois é de produto, não técnica: quem precisa de controle de acesso por
documento fica no (1).

## Onde a plataforma NÃO resolve: GitHub

**Não existe knowledge source de GitHub.** Três alternativas plausíveis foram investigadas e
todas falham para este uso:

- **Conector GitHub do Logic Apps** — existe e é oficial, mas as ações são *issues, pull
  requests, secrets, dispatch events*. Não lê a árvore de arquivos de um repositório. Serve para
  automação de workflow, não para ingestão de conteúdo.
- **`WebKnowledgeSource`** — é Bing público. Não alcança repositório privado, e mesmo público
  chegaria por busca, não pelo conteúdo versionado.
- **Data Sources Gallery** — Blob, Table, ADLS Gen2, Cosmos (NoSQL/Gremlin/Mongo), SQL, MySQL,
  OneLake, SharePoint. Nenhum é GitHub.

**Esta é a única peça que exige código nosso**, e ela é pequena: ler os arquivos pela API do
GitHub e escrevê-los no blob. Do blob em diante tudo volta a ser oficial.

O token vem do usuário, não da aplicação: o `dna-cloud` já tem a GitHub App
("DNA Cloud Connect", token user-to-server ~8h com refresh ~6 meses, cifrado por `oid`). Isso
mantém a mesma filosofia do OBO usado aqui — o acesso é de quem pediu.

### A alternativa que elimina até essa cola

O cliente instala uma **GitHub Action** que empurra o conteúdo para o blob. Nada nosso toca o
repositório dele. Custa a mudança de produto de "conecte e pronto" para "instale e conecte", e
por isso não é o caminho padrão — mas é a resposta certa para quem não autoriza um app de
terceiro a ler seu código.

## Desenho

### Superfície HTTP

Seis endpoints. Cinco são repasse; um é a peça nossa.

| Endpoint | O que chama | Nosso código |
|---|---|---|
| `GET /knowledge` | `list_knowledge_bases` + `list_knowledge_sources` | projeção |
| `POST /knowledge` | `create_or_update_knowledge_source` + `_base` | validação |
| `DELETE /knowledge/{name}` | `delete_knowledge_base` + `_source` | ordem |
| `GET /knowledge/{name}/status` | `get_knowledge_source_status` | repasse |
| `POST /knowledge/{name}/files` | `BlobServiceClient.upload_blob` | repasse |
| `POST /knowledge/{name}/github` | **GitHub API → blob** | **a peça nossa** |

`DELETE` remove base antes de fonte: a base referencia a fonte
(`KnowledgeSourceReference`), e apagar a fonte primeiro deixaria a base apontando para nada.

### As bases atuais entram na mesma lista

`helpdesk` e `selfwiki` **já são** knowledge sources no serviço — `list_knowledge_sources` as
devolve hoje. O que falta não é migração, é o `GET /knowledge` não filtrá-las.

O que continua em código é o **registry de domínios** (`app/registry.py`), que amarra uma base a
um agente, prompts e ACL. Uma base criada pelo usuário é conteúdo consultável; um domínio é um
produto. Confundir os dois transformaria "adicionar uma base" em "adicionar um agente", que não
foi o pedido.

### Onde isso mora

Módulo `knowledge` já existe e é o dono do assunto (ADR-017). Entra como
`app/modules/knowledge/api_knowledge.py`, exposto pelo `public.py`. O conector GitHub fica em
`internal/github_source.py` — a única superfície nova, isolada por construção.

### Autorização

`POST` e `DELETE` mudam o que os agentes leem: exigem **Admin** (mesmo papel de
`/admin/users`). `GET` exige apenas autenticação. Reusa `require_role`; nada novo.

## Riscos e questões abertas

**Escala do GitHub.** Repositório grande não cabe em memória. O caminho é streamar por arquivo
para o blob, com teto de tamanho e de contagem — e dizer no log o que foi cortado, nunca truncar
em silêncio.

**Custo por base.** Cada knowledge source vira um indexer e um índice. O serviço é o mesmo
(~US$73/mês), mas armazenamento e execução crescem por base. Um teto por tenant é necessário
antes de abrir para vários clientes.

**ACL de conteúdo do usuário.** Uma base criada por alguém precisa de audiência declarada. O
mecanismo existe (carimbo de grupo + `permissionFilterOption`), e o default seguro é a
audiência de quem criou — nunca "todos", que é o default que vaza.

**Nomes.** `name` vira recurso no serviço de Search e é global por serviço. Precisa de prefixo
por tenant e de validação de formato, senão dois clientes colidem.

## O que NÃO vamos escrever

Registrado para que ninguém reintroduza por engano:

- chunking, embedding ou pipeline de indexação — `KnowledgeSourceIngestionParameters` faz
- CRUD de base/fonte — os onze métodos do SDK fazem
- conectores de SharePoint, OneLake, Web — tipos de primeira parte já existem
- extração de texto de PDF/Office — o blob source já suporta esses formatos

## Referências

- SDK instalado: `azure.search.documents.indexes` — 29 tipos de knowledge, 11 operações
- [Knowledge sources](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-overview) ·
  [Criar knowledge base](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-create-knowledge-base) ·
  [Data Sources Gallery](https://learn.microsoft.com/en-us/azure/search/search-data-sources-gallery)
- [Conector GitHub (Logic Apps)](https://learn.microsoft.com/en-us/connectors/github/) — issues/PRs, não conteúdo
- `dna-cloud`: `apps/web/lib/connections/github.ts` — a conexão delegada
- MÁXIMA MAIOR em `CLAUDE.md` — o princípio que ordenou esta pesquisa
