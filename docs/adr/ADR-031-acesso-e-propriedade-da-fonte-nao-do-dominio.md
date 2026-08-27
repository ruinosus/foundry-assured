# ADR-031 — Acesso é propriedade da FONTE, não do domínio

- **Status:** Proposed
- **Date:** 2026-08-27
- **Context:** `CLAUDE.md` Regra #6 (controle de acesso é DADO) e MÁXIMA MAIOR,
  [ADR-029](./ADR-029-caminho-por-api-key.md) (o trim vem do OBO, não da chave),
  `app/modules/domains/internal/catalog.py` (`document_access`),
  `app/modules/knowledge/internal/{ingest,acl_setup,secure_search}.py`

## Contexto

Hoje o acesso é declarado **por domínio**. `DomainSpec.document_access` é um
`Literal["acl", "session"]` (`catalog.py:61`), declarado e não derivado, com validação: um
domínio `"acl"` sem `search_index` falha ao montar (`catalog.py:75-77`).

A distribuição atual: `techdocs` e `selfwiki` são `"acl"`; `helpdesk` e `platform` são
`"session"`.

O `helpdesk` ser `"session"` é uma decisão consciente, e o próprio catálogo escreve a condição
que a sustenta (`catalog.py:140-150`):

> "qualquer sessão autenticada pode ler qualquer blob da raiz deste container pelo nome…
> **Hoje isso não vaza nada porque o container só recebe os runbooks da ingestão** (conteúdo já
> público a quem usa o helpdesk)… Antes de gravar qualquer coisa sensível aqui, pergunte:
> *uma sessão qualquer pode ler isto pelo nome?*"

O comentário está certo e é honesto. Ele também é **condicional** — e o dono do projeto acaba de
responder a pergunta que ele deixa em aberto: as fontes não serão só código nem só runbooks
curados. Serão arquivos que alguém sobe (PDF, MD, PPTX, XLSX), e apontamentos para APIs que
devolvem JSON.

No instante em que um PDF restrito entra nesse container, `document_access="session"` deixa de
ser uma decisão de audiência e passa a ser um vazamento — **sem erro, sem gate vermelho**. A
condição que tornava a decisão segura some sem avisar.

## Decisão

**Acesso passa a ser declarado pela FONTE, não pelo domínio.** Um domínio deixa de ter uma
audiência; ele passa a hospedar fontes que têm audiências, possivelmente diferentes entre si.

Isto NÃO é reescrever o mecanismo. O mecanismo de aplicação já está correto e já é o nativo da
plataforma (ver abaixo). O que muda é **onde a resposta ao "quem pode ler" é declarada**: sai do
`DomainSpec`, vai para a fonte.

## O que a plataforma já resolve — medido, não suposto

Medido em `azure-search-documents 11.7.0b2` (o pacote instalado) e na doc oficial.

**Formatos (o "quê").** O *document cracking* do blob indexer / knowledge source já extrai texto
de: `PDF`, Office (`DOCX/DOC/DOCM`, `XLSX/XLS/XLSM`, `PPTX/PPT/PPTM`, `MSG`), OpenDocument
(`ODT/ODS/ODP`), `JSON`, `CSV`, `Markdown`, `HTML`, `XML`, `EML`, `EPUB`, `RTF`, `TXT`, `KML`,
`GZ`, `ZIP`. Sem custo de extração. Imagem exige AI enrichment à parte.

**Não há nada a construir do lado dos formatos.** A lista acima já cobre tudo que foi pedido.

**Tipos de fonte.** O SDK instalado expõe `AzureBlobKnowledgeSource`,
`IndexedOneLakeKnowledgeSource`, `IndexedSharePointKnowledgeSource`,
`RemoteSharePointKnowledgeSource`, `SearchIndexKnowledgeSource` e `WebKnowledgeSource`.

**Acesso por documento (o "porquê").** `KnowledgeSourceIngestionParameters` tem o campo
**`ingestion_permission_options`** — na mesma classe que `ingest.py:169` já constrói. Valores:
`GROUP_IDS`, `USER_IDS`, `RBAC_SCOPE`.

E o mecanismo de consulta que já usamos é o nativo, não a gambiarra: `acl_setup.py:93,121-125`
liga `permissionFilterOption` e cria o campo `groups` com `"permissionFilter": "groupIds"`,
consultado com `x-ms-query-source-authorization`. A doc separa os dois explicitamente — o
permission filter *"é reconhecido como autenticação do Microsoft Entra, enquanto o security
trimming é comparação simples de string"*. Estamos no de cima.

**Conclusão da MÁXIMA MAIOR:** a Regra #6 é o padrão de mercado escrito noutro idioma. Azure AI
Search, Graph/Copilot connectors, Kendra, Glean e Gemini Enterprise fazem todos a mesma coisa —
ACL por documento, herdada da fonte, aplicada na query. **Nada do mecanismo é para escrever.**

## Os limites, também medidos

1. **Blob comum não tem ACL por documento.** A doc é literal: *"para Azure blobs usando o blob
   indexer ou knowledge source, a preservação de escopo RBAC é no nível do **container**"*. Por
   documento, o caminho *pull* nativo exige **ADLS Gen2** com ACL POSIX nos arquivos.
   Nossa conta (`infra/resources.bicep:191`) é `StorageV2` **sem `isHnsEnabled`** — blob comum.
2. **Ligar HNS está bloqueado por decisão nossa anterior.** A migração exige versionamento
   desligado; `resources.bicep:218` tem `isVersioningEnabled: true`, pré-requisito da
   imutabilidade da trilha (ADR-023). São mutuamente exclusivos na mesma conta, a conta fica
   offline durante a migração, e ela é irreversível. Viável só com uma **segunda** storage
   account, HNS-ligada, dedicada a conhecimento.
3. **`ingestionPermissionOptions` não combina com `assetStore`** — sem image serving na mesma
   knowledge source.
4. **Fonte que não é blob** (uma API que devolve JSON) usa o **push model**: `Index Documents`
   com o campo de permissão no payload. É agnóstico de API e já é o que `acl_setup.py` faz.

## Consequências

**O que passa a valer.** Uma fonte declara seu acesso; o domínio herda a união do que suas fontes
declaram. `document_access` no `DomainSpec` deixa de ser a resposta e passa a ser, no máximo, o
default de uma fonte que não declarou — que por fail-closed é "ninguém", não "qualquer sessão".

**O que isto obriga a decidir e ainda não está decidido:**

- Onde a fonte declara. Para conteúdo que passa por adaptador, dentro do próprio documento
  (frontmatter, no formato do OKF — ver
  `docs/superpowers/specs/2026-08-27-docbundle-vs-okf-medicao.md`) é o único lugar que viaja com
  o conteúdo e é versionado junto. Para fonte com ACL nativa (SharePoint, ADLS Gen2, OneLake), o
  lugar certo é a própria fonte, e nós não declaramos nada — `ingestion_permission_options`
  resolve.
- Se o `helpdesk` ganha `search_index`. Hoje ele não tem, e a validação do `DomainSpec` recusa
  `document_access="acl"` sem ele. Enquanto isso não mudar, esse domínio não pode receber fonte
  restrita.
- Se conhecimento migra para uma segunda storage account com HNS.

**O que NÃO muda.** O mecanismo de aplicação (permission filter + OBO no header), a Regra #6, e
o princípio de que nenhuma classificação mora no código.

## Risco aceito enquanto isto não for implementado

`helpdesk` e `platform` seguem `document_access="session"`. **Enquanto forem, é proibido subir
conteúdo restrito nos containers deles** — a garantia é operacional, não verificada por gate.
Fechar essa lacuna com um gate é parte do trabalho que esta ADR autoriza, não um pré-requisito
dela.

## Gatilho de reavaliação

Esta ADR vira urgente — e o risco acima deixa de ser aceitável — no primeiro dos eventos:

1. Qualquer fonte não-código com público restrito apontada para um domínio `"session"`.
2. Suporte a ACL por documento em blob comum (hoje: só container).
3. Um segundo domínio precisar de fontes com audiências diferentes entre si.
