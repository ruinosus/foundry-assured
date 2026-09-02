---
title: 'Design: agentes, bases e skills que o usuário final cria e mantém'
description: "Trazer um perfil de usuário que não tem acesso ao portal do Foundry para consumir os recursos do Foundry — criar, usar e manter agentes, bases de conhecimento e skills. Levantamento feito ANTES do desenho, pela MÁXIMA MAIOR do CLAUDE.md, e o resultado é que praticamente tudo já existe como API oficial: 23 operações de agente (incluindo versionamento e sessões), 11 de skill, 11 de knowledge. A única lacuna real é o GitHub."
type: design
audience: contributor
status: shipped
updated: 2026-08-17
---

# Agentes, bases e skills que o usuário final cria e mantém

Substitui e amplia `2026-08-17-user-managed-knowledge-bases-design.md`, que cobria só as bases.
Aquela spec continua correta no que diz; esta a engloba.

## O que estamos construindo, e por quê

> "Não é recriar nada da Microsoft, é preencher lacunas e trazer outros perfis de usuário para
> consumir recursos Microsoft."

O portal do Foundry atende quem tem conta e RBAC no Azure. Este produto atende quem **não tem
e não vai ter**: o usuário final que precisa criar, usar e manter agentes, bases e skills sem
nunca abrir o portal e sem saber o que é um resource group.

O teste que separa produto de violação da máxima: *estou expondo uma capacidade a um perfil
que não a alcança, ou reimplementando a capacidade?* Tudo abaixo é o primeiro.

## O levantamento (feito antes do desenho)

Do SDK **instalado** — `azure-ai-projects`, `azure-search-documents 11.7.0b2` — que é a fonte de
verdade sobre a versão em uso, não a documentação.

### Agentes: 23 operações, e agente é recurso versionado

```
list · get · delete · enable · disable
create_version · create_version_from_code · create_version_from_manifest
create_session · get_session · delete_session · list_sessions
get_session_log_stream · list_session_files · download_session_file · delete_session_file
download_code
```

Três coisas que isso revela e mudam o desenho:

1. **Agente tem versões.** `AgentVersionDetails`, `AgentVersionStatus`, `AgentObjectVersions`.
   Editar um agente não é sobrescrever — é publicar versão. A interface precisa refletir isso,
   ou vai mentir sobre o que acontece ao salvar.
2. **`create_version_from_manifest`** aceita um manifesto declarativo. É o mesmo modelo dos
   documentos AgentSchema que este repositório já usa (ADR-013), então "criar agente" pode ser
   "enviar um manifesto" em vez de um formulário que inventa campos.
3. **Sessões são recurso de primeira classe**, com log em streaming e arquivos. "Usar o agente"
   e "ver o que ele fez" já têm API — não precisamos guardar histórico por fora.

Há ainda `AgentCard` + `AgentCardSkill` (o formato A2A), `AgentBlueprintReference` e
`AgentIdentity` — o agente tem identidade própria, o que importa quando ele chama coisas.

### Skills: 11 operações

```
create · create_from_files · get · get_version · delete · delete_version
download · download_version
```

`create_from_files` é o caminho para "traga sua skill", sem formato nosso.

### Conhecimento: 11 operações (já mapeado)

`create/create_or_update/get/list/delete` para knowledge base e knowledge source, mais
`get_knowledge_source_status`. Seis tipos de fonte de primeira parte: Blob, SearchIndex,
SharePoint (indexado e remoto), OneLake, Web.

### E ainda existem, sem precisarmos escrever

`BetaMemoryStoresOperations` (13), `BetaEvaluatorsOperations` (13),
`BetaRedTeamsOperations`, `BetaSchedulesOperations`, `ConnectionsOperations`.

## A única lacuna real: GitHub

Não existe knowledge source de GitHub, e as três alternativas plausíveis falham:

- **Conector GitHub do Logic Apps** — oficial, mas as ações são *issues, pull requests,
  secrets*. Não lê a árvore de arquivos de um repositório.
- **`WebKnowledgeSource`** — é Bing público; não alcança repositório privado.
- **Data Sources Gallery** — Blob, Table, ADLS, Cosmos, SQL, MySQL, OneLake, SharePoint.

O código nosso é pequeno e cercado: ler os arquivos pela API do GitHub e escrevê-los no blob.
Do blob em diante tudo volta a ser oficial (`AzureBlobKnowledgeSource` faz chunking, embedding
e indexação). O token é do usuário, não da aplicação — o `dna-cloud` já tem a GitHub App com
token user-to-server cifrado por `oid`.

## Decisões que este levantamento resolve

As duas perguntas em aberto do `PRODUCT.md` deixam de ser opinião:

**"Criar agente vai até onde?"** Até publicar versão, porque é isso que a API faz. Um formulário
que "salva" sem versionar contradiz o recurso por baixo. E `create_version_from_manifest`
permite que a primeira versão seja **enviar um manifesto**, sem inventarmos um editor de
campos — o editor visual vem depois, se vier.

**"Os quatro domínios atuais viram gerenciáveis?"** Eles são configuração de código, não
recursos do Foundry — por isso não entram na mesma lista. Ficam como **exemplos**, marcados
como tal, ao lado dos agentes do usuário. Fundi-los exigiria transformar registry em recurso,
que é trabalho sem demanda.

## Desenho

### Superfície HTTP — repasse, com uma exceção

| Endpoint | Chama | Nosso |
|---|---|---|
| `GET /agents` | `AgentsOperations.list` | projeção |
| `GET /agents/{name}` | `get` + `get_version` | projeção |
| `POST /agents` | `create_version_from_manifest` | validação |
| `POST /agents/{name}/versions` | `create_version` | validação |
| `POST /agents/{name}/{enable,disable}` | `enable` / `disable` | repasse |
| `DELETE /agents/{name}` | `delete` | repasse |
| `GET /agents/{name}/sessions` | `list_sessions` | projeção |
| `GET /knowledge` | `list_knowledge_bases` + `_sources` | projeção |
| `POST /knowledge` | `create_or_update_knowledge_source` + `_base` | validação |
| `DELETE /knowledge/{name}` | `delete_knowledge_base` + `_source` | ordem |
| `POST /knowledge/{name}/files` | upload para blob | repasse |
| `GET /skills` · `POST /skills` | `BetaSkillsOperations.list` / `create_from_files` | repasse |
| `POST /knowledge/{name}/github` | **GitHub API → blob** | **a peça nossa** |

`DELETE` de conhecimento remove base antes de fonte: a base referencia a fonte, e apagar a
fonte primeiro deixaria a base apontando para nada.

### Arquitetura de informação

A navegação deixa de ser "as features que o time embutiu" e passa a ser "o que é meu":

```
Agentes      lista · detalhe (versões, sessões) · criar
Conhecimento lista · detalhe (status de sincronização) · criar (arquivos | GitHub)
Skills       lista · criar (arquivos)
Exemplos     os quatro domínios de hoje, marcados como demonstração
```

### Autorização

Leitura exige autenticação. Escrita (`POST`, `DELETE`) exige **Admin** — reusa `require_role`,
nada novo. Criar agente e apagar base mudam o que outras pessoas veem.

## Riscos

**Versionamento visível.** Se a interface esconder que salvar publica versão, o usuário vai
esperar edição in-place e perder a rastreabilidade que é o ponto do recurso.

**Custo por base.** Cada knowledge source vira indexer e índice. O serviço é o mesmo (~US$73/mês
para o Search ligado), mas armazenamento e execução crescem por base — teto por tenant é
necessário antes de abrir para vários clientes.

**Repositório privado no nosso índice.** Vira contrato: onde o dado vive, quem alcança, como se
apaga. O modo `dedicated` (stamp na subscription do cliente) é a resposta para quem não aceita
multi-tenant.

**Escala do GitHub.** `gather_source` lê o repositório inteiro em memória, com teto de 16k
caracteres por arquivo. Serve para 509 arquivos; um monorepo de cliente quebra.

**Nomes globais.** `name` de agente/base é recurso no serviço — precisa de prefixo por tenant e
validação de formato, ou dois clientes colidem.

## O que NÃO vamos escrever

- CRUD de agente, skill, base ou fonte — as 45 operações do SDK fazem
- versionamento, sessões, log em streaming — já são recurso
- chunking, embedding, pipeline de indexação — `KnowledgeSourceIngestionParameters` faz
- conectores de SharePoint, OneLake, Web — tipos de primeira parte
- extração de texto de PDF/Office — o blob source suporta

## Ordem sugerida, e onde estamos

1. ✅ **`GET /agents` + `GET /knowledge`** — listar é o menor passo que já entrega valor e prova
   a ligação com o Foundry. As duas telas existem (`/agents`, `/knowledge`), com projeção
   testada offline em `tests/foundry/`.
2. Detalhe do agente (versões, sessões) — `GET /agents/{name}` já responde; falta a tela
3. Criar base por upload
4. Criar agente por manifesto
5. GitHub (a peça nossa)

### O que o passo 1 ensinou, contra o serviço real

**Fonte órfã é um problema de verdade, e apareceu no primeiro uso.** O ambiente tem
`selfwiki-docbundles-ks` (azureBlob) que nenhuma base referencia — resquício da migração para
`selfwiki-docbundles-si-ks` (searchIndex). Cada fonte mantém um indexador rodando, então isso é
custo sem resposta. O catálogo marca (`orphan`) e a tela avisa ANTES das tabelas. Não estava na
spec; é lacuna que o portal também não mostra bem, e virou parte do produto.

**`get_knowledge_source_status` é uma chamada POR FONTE.** O status não vem no objeto da base, e
é ele que responde "esta base está atualizada?". Falha de status não derruba a página: a fonte
aparece com status ausente e a base continua legível.

**O objeto de estado não sobrevive a `str()` — e o gate não bastou na primeira tentativa.**
`current_synchronization_state` e `last_synchronization_state` são o MESMO tipo. Corrigi o `last_`
e plantei a forma real só nele, então o `current_` continuou com `str()` e o gate passou verde. O
defeito só apareceu ao subir um arquivo de verdade, quando o campo finalmente veio preenchido.
**Um campo opcional só mostra o defeito no dia em que vem cheio** — o gate agora cobre os dois.

### O que os passos 3 a 5 ensinaram, contra o serviço real

**O container tem de existir ANTES da knowledge source.** A fonte é validada no momento em que é
criada, e o Search responde `Unable to retrieve blob container for account '<conta>' using your
managed identity` — mensagem que soa como falta de permissão e manda procurar no lugar errado. Meu
desenho criava o container só no primeiro upload. Corrigido com `ensure_container`.

**Ciclo completo verificado no Azure:** criar → aparecer no catálogo → subir arquivo → status de
sincronização em curso → apagar base, fonte e container. Nenhum resíduo ficou.

## Referências

- SDK instalado: `azure.ai.projects.operations` — `AgentsOperations` (23), `BetaSkillsOperations`
  (11), `BetaMemoryStoresOperations` (13), `BetaEvaluatorsOperations` (13);
  `azure.ai.projects.models` — 42 tipos de Agent
- `azure.search.documents.indexes` — 11 operações de knowledge, 6 tipos de fonte
- [Conector GitHub (Logic Apps)](https://learn.microsoft.com/en-us/connectors/github/) — issues/PRs, não conteúdo
- `dna-cloud`: `apps/web/lib/connections/github.ts` — conexão delegada por usuário
- MÁXIMA MAIOR em `CLAUDE.md`
