# Detalhamento técnico — Binding MCP, Toolbox e snapshot de descoberta

> Base: `01-entendimento.md`, `02-prd.md`, ADR-032 e ADR-033.
> Workflow: `critico`.
> Estado: contratos confirmados pelo desenvolvedor; validação estrutural de tech lead/arquiteto
> permanece obrigatória antes da implementação.

## 1. Fronteira e capacidades oficiais

| Responsabilidade | Dono | Uso na F03 |
|---|---|---|
| Catálogo e versões de Toolbox | Foundry `AIProjectClient.toolboxes` 2.4.0 | `list`, `get`, `list_versions`; sem catálogo local |
| Credenciais e identidade | Foundry connections, Entra/OBO, `DefaultAzureCredential` | referência e resolução em memória; nunca segredo no OKF |
| Protocolo MCP | Agent Framework 1.14.0 + MCP 1.28.0 | `MCPStreamableHTTPTool` e `MCPTool.load_tools()` |
| Allowlist e aprovação runtime | `allowed_tools`, `approval_mode`/`require_approval` | configuração derivada da conformidade |
| Classificação administrativa | `platform_ops` | lacuna local tenant-scoped, fail-closed |
| Snapshot e drift | `platform_ops` + `audit` | lacuna de assurance permitida pela máxima |
| Imutabilidade e criptografia | Azure Blob WORM + Storage SSE | primitiva Azure, sem criptografia própria |

Verificações concluídas nos quatro lugares exigidos pela MÁXIMA MAIOR: pacote instalado,
Microsoft Learn, repositórios/samples oficiais e release metadata. `load_tools()` pagina por
`session.list_tools()` e não chama `call_tool`. A auditoria `maxima-auditor` retornou `PASS`.

## 2. Organização modular

- `okf`: schema estrito e validação estrutural de `mcp-binding`; não acessa rede nem stores.
- `foundry`: projeção oficial de Toolboxes/versões e resolução das referências Foundry.
- `platform_ops`: endpoint proposal, discovery, saneamento, classificação, drift, projeção,
  conformidade e construção runtime.
- `tenancy`: tenant/projeto/connection derivados do request; nenhuma rota aceita esses escopos.
- `audit`: grava evento e payload de evidência sanitizado sob WORM/SSE por superfície pública.
- composition root: inclui routers pelos `public.py`; imports cross-module nunca entram em
  `internal/` de outro módulo.

ADR-032 continua governando bindings e publicação. ADR-033 é complementar e fixa as decisões
operacionais da F03. Nenhum módulo novo é necessário.

## 3. Schema `mcp-binding`

`spec` é estrito e contém:

```yaml
# origem Toolbox fixa
toolbox:
  name: platform-tools
  version: "3"
tools: [search_resources, update_resource]
reviewedSnapshot:
  id: msnap_...
  hash: <sha256-hex>
```

```yaml
# origem Toolbox default, resolvida para versão fixa pela F06
toolbox:
  name: platform-tools
  useDefault: true
tools: [search_resources]
reviewedSnapshot:
  id: msnap_...
  hash: <sha256-hex>
```

```yaml
# endpoint direto previamente aprovado
endpoint:
  id: mep_...
tools: [search]
reviewedSnapshot:
  id: msnap_...
  hash: <sha256-hex>
```

Regras:

- exatamente uma origem: `toolbox` ou `endpoint`;
- Toolbox contém exatamente `name` e um de `version`/`useDefault:true`;
- `tools` é lista não vazia, única e limitada aos nomes do snapshot revisado;
- `reviewedSnapshot` contém id tenant-local e hash SHA-256;
- `classification`, `server.url`, connection, auth, header, token e segredo não existem no schema;
- detecção recursiva de chave com semântica de segredo continua obrigatória;
- a conformidade valida que source, snapshot e tools se referem ao mesmo tenant e contrato.

## 4. Recursos persistidos

### 4.1 `McpEndpoint`

Registro tenant-scoped imutável após criação:

```text
id, tenant_key, origin, auth_mode(public|connection|obo), connection_ref?,
status(pending|approved|rejected), created_at, created_by,
decision_at?, decision_by?, decision_reason?, revision
```

`origin` é somente `https://host` ou `https://host/path`, porta implícita 443. Não contém userinfo,
fragmento, query secreta nem IP literal. Alterar URL/auth cria outro endpoint. Criar não acessa rede.

### 4.2 `McpDiscoverySnapshot`

Blob JSON imutável e sanitizado:

```text
snapshot_id, source(kind,id,resolved_version?), observed_at, protocol_version,
tools[{name,description,input_schema,output_schema,annotations,contract_hash}], snapshot_hash
```

Campos MCP permitidos: nome, descrição, `inputSchema`, `outputSchema` e annotations
`title`, `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`. `_meta`, ícones,
resultados, recursos, prompts e campos desconhecidos são descartados antes da persistência.

Uma projeção Azure Table guarda apenas source, `latest_snapshot_id`, `current|stale`,
`last_success_at`, `last_attempt_at` e resumo de drift. O Blob é a fonte do conteúdo.

### 4.3 `McpToolClassification`

Fonte de policy em Azure Table, com fake em memória:

```text
tenant_key, source_id, tool_name, tool_contract_hash, effect(read|write), reason,
revision/etag, decided_at, decided_by
```

Chave inclui o hash do contrato: schema ou descrição alterada não herda autorização. Toda mutação
usa `expectedRevision` e também grava evento na evidence layer. A trilha não é lida no hot path.

## 5. Contratos HTTP

Todas as rotas usam autenticação existente. `tenant`, project endpoint, storage scope e identidade
do ator vêm exclusivamente do contexto autenticado.

### 5.1 Toolbox projection

`GET /authoring/toolboxes?cursor=&limit=50`

- Papéis: Builder, Author, Admin.
- `limit`: 1..100.
- `200`: `items[{name,description,defaultVersion,versions[{version,createdAt}],mcpUrl}],nextCursor`.
- Consulta Foundry a cada leitura; não persiste catálogo.

### 5.2 Direct endpoint

- `POST /authoring/mcp-endpoints`: cria `{url,auth:{mode,connectionRef?}}` como `pending`, sem rede.
- `GET /authoring/mcp-endpoints`: lista somente o tenant atual.
- `POST /authoring/mcp-endpoints/{id}/approval`: Admin envia
  `{decision: approved|rejected,reason}`; decisão é auditada e não autoriza discovery/tool call por si.

### 5.3 Discovery and review

`POST /authoring/mcp-discoveries`, somente Admin:

```json
{"toolbox":{"name":"platform-tools","version":"3"}}
```

ou Toolbox com `useDefault:true`, ou `{"endpointId":"mep_..."}`. A resposta `201` contém
`snapshotId`, source, `resolvedVersion`, `observedAt`, `protocolVersion`, `status`, `hash`, projeção
de tools e drift. É síncrona; cada retry cria uma observação.

`POST /authoring/mcp-snapshots/{id}/review`, somente Admin, confirma um snapshot depois de todas as
tools estarem classificadas. Mudança de default/resolved version bloqueia promoção até essa revisão.

### 5.4 Classification

`PUT /authoring/mcp-snapshots/{snapshotId}/tools/{toolName}/classification`, somente Admin:

```json
{"effect":"read","reason":"consulta sem efeito colateral verificada","expectedRevision":2}
```

Retorna a decisão, nova revisão e estado efetivo. Conflito otimista retorna `409`.

### 5.5 Projection and conformity

- `GET /authoring/mcp-sources/{sourceId}`: latest snapshot, `current|stale`, tentativas e drift.
- `GET /authoring/mcp-snapshots/{id}`: projeção sanitizada e estados por tool; nunca o payload
  protegido ou protocolo bruto.
- `POST /authoring/mcp-bindings/conformity`: recebe um `mcp-binding.spec`, não persiste e devolve
  `pass|block`, razões, source/snapshot resolvidos e estado das tools.

Leitura/conformidade: Builder, Author e Admin. Recurso cross-tenant responde `404` igual a ausente.

## 6. Discovery, egress e saneamento

Ordem obrigatória:

1. autenticar e exigir Admin;
2. resolver tenant e source sem aceitar escopo do body;
3. exigir endpoint direto `approved` ou resolver Toolbox/version pelo SDK oficial;
4. adquirir lease tenant+source com TTL de 30 s;
5. validar URL e resolver todos os A/AAAA imediatamente antes da conexão;
6. conectar com HTTP client restrito e redirects desabilitados;
7. chamar `MCPTool.load_tools()` e consumir apenas metadata gerada por `tools/list`;
8. aplicar limites durante paginação e parse, não após materializar payload ilimitado;
9. descartar campos não permitidos, redigir, canonicalizar e calcular hashes em memória;
10. persistir Blob create-once, evento de audit e projeção; liberar lease.

Política de URL:

- somente HTTPS, porta 443, hostname DNS e origem exata aprovada;
- sem IP literal, userinfo, fragmento ou redirect;
- recusar se qualquer resposta DNS for loopback, private, link-local, multicast, unspecified,
  reserved ou metadata; nomes internos conhecidos também são recusados;
- egress de infraestrutura bloqueia os mesmos destinos e é o controle final contra rebinding/TOCTOU;
- header de autenticação só existe em memória; modo public envia nenhum header.

Limites:

| Limite | Valor |
|---|---:|
| Connect timeout | 5 s |
| Request/read timeout | 10 s |
| Operação total | 15 s |
| Tools por snapshot | 200 |
| Snapshot sanitizado | 256 KiB |
| Schema por tool | 32 KiB |
| Profundidade de schema | 12 |
| Propriedades por schema | 200 |
| Nome de tool | 128 caracteres |
| Descrição de tool | 2.048 caracteres |
| Concorrência | 1 discovery por tenant+source; excedente `429` |

Qualquer excesso invalida a descoberta inteira. Não existe snapshot parcial. Cursor repetido,
paginação sem progresso, JSON/schema inválido e nomes duplicados são erro de protocolo.

## 7. Classificação efetiva e runtime

Precedência fail-closed:

1. sem classificação Admin para o hash atual: `quarantined`;
2. decisão Admin `write`, `destructiveHint=true` ou `readOnlyHint=false`: `write_requires_approval`;
3. decisão Admin `read` sem sinal de elevação: `read`;
4. policy ou RBAC pode converter qualquer estado em `forbidden`;
5. estado stale, drift ou ausência de revisão converte a tool afetada em `quarantined`.

Annotations remotas nunca concedem read. Tool `write_requires_approval` entra no runtime somente
para papel permitido e sempre em `always_require_approval`; read usa `never_require_approval` onde
a policy permitir. `allowed_tools` contém somente tools conformes. Execução verifica conformidade
antes da chamada remota; F03 não implementa a publicação da configuração.

## 8. Hash e drift

- Canonicalização: RFC 8785 JCS sobre UTF-8; digest SHA-256 hexadecimal minúsculo.
- Tool hash: `name`, descrição sanitizada completa, input/output schemas normalizados e annotations
  permitidas.
- Snapshot hash: source identity, resolved version, protocol version e tools ordenadas por nome.
- Ordem de tools e de chaves de objeto não altera hash; ordem de arrays continua semântica.

Matriz:

| Mudança | Resultado |
|---|---|
| Tool adicionada | nova tool quarantined; promoção bloqueada |
| Tool removida | referência/call bloqueada; demais inalteradas continuam |
| Descrição, schema ou annotation permitida | tool quarantined |
| Classificação efetiva | tool quarantined até revisão |
| Apenas ordem/chaves equivalentes | sem drift |
| Default/resolved Toolbox version | promoção bloqueada; runtime anterior segue versão fixa |
| Falha de discovery/auth/timeout | último contexto fica `stale`; promoção e execução bloqueadas |

## 9. Persistência e criptografia

- Snapshot: Blob create-once `mcp-snapshots/{snapshotId}.json` na evidence layer do tenant.
- Imutabilidade: política WORM com protected append/create conforme ADR-023.
- Criptografia: Azure Storage SSE AES-256, com Microsoft-managed key ou CMK configurada na conta.
- Auth: `DefaultAzureCredential`; nenhum account key/SAS em código ou documento.
- Retenção: herda a política da evidence layer do tenant.
- Redaction e limites acontecem antes da primeira escrita durável.
- Evento de audit contém identidade/hash/contagens, nunca descrição, schema, URL ou payload.

## 10. Erros e observabilidade

Envelope:

```json
{"error":{"code":"MCP_SNAPSHOT_STALE","message":"...","correlationId":"...","retryable":false}}
```

| HTTP | Codes |
|---:|---|
| 404 | `MCP_SOURCE_NOT_FOUND` (inclui cross-tenant) |
| 409 | `MCP_ENDPOINT_NOT_APPROVED`, `MCP_SNAPSHOT_STALE`, `MCP_DRIFT_BLOCKING` |
| 413 | `MCP_DISCOVERY_LIMIT_EXCEEDED` |
| 422 | `MCP_BINDING_INVALID`, `MCP_EGRESS_DENIED`, `MCP_PROTOCOL_INVALID` |
| 424 | `MCP_AUTH_FAILED` |
| 429 | `MCP_DISCOVERY_BUSY` |
| 502 | `MCP_SOURCE_UNAVAILABLE` |
| 504 | `MCP_DISCOVERY_TIMEOUT` |

Spans/logs contêm tenant pseudonimizado, source id/hash, snapshot id, outcome, duração, contagens,
drift e error code. Não contêm URL, token, header, tool description/schema ou payload remoto.
Stack trace fica apenas no backend protegido. Métricas agregam duração, outcome, code, quantidade
de tools e drift sem dimensão de alta cardinalidade sensível.

## 11. Estratégia de testes

- contratos estritos do novo `mcp-binding`, inclusive segredos recursivos e campos removidos;
- fake de `AIProjectClient.toolboxes` para projeto/versão/default e isolamento por tenant;
- fake MCP paginado que falha se `call_tool` for acessado;
- integração source → discovery → Blob/audit/projection → classification → drift → conformity;
- matriz de annotations/classification/policy/RBAC/native approval;
- adição, remoção, descrição, schema, annotation, classificação e version drift;
- SSRF IPv4/IPv6, DNS rebinding, metadata, malformed URL e qualquer redirect;
- timeout, auth, cursor repetido, payload, profundidade, propriedades e concorrência;
- canary de segredo em todos os campos remotos, erros, logs, traces, Table, Blob e audit;
- dois tenants com os mesmos nomes e dados diferentes;
- gate implantado para WORM/SSE/egress, além dos gates offline;
- import-linter e cobertura mínima de 80% para lógica crítica nova.

Os testes verificam comportamento nas superfícies públicas e não classes geradas dos SDKs.

## 12. Decisões confirmadas e gates

Confirmado explicitamente pelo desenvolvedor durante o detalhamento:

- arquitetura e fronteira Microsoft-native;
- contratos de Toolbox, endpoint, discovery, classificação, projeção e conformidade;
- schema `mcp-binding` sem classificação/credencial;
- limites e redirects recusados;
- RFC 8785 + SHA-256 e matriz de drift;
- Azure Table para policy/projeção e Blob WORM/SSE para snapshot;
- envelope de erros e telemetria sem conteúdo.

Gate ainda aberto: tech lead/arquiteto deve aceitar ADR-033 e a mudança estrutural antes da
implementação. O threat model obrigatório está em
`.smart-coding/_threat-models/2026-08-31-mcp-binding-discovery.md`.

## 13. Fora do escopo reafirmado

- escrita/publicação, journal, idempotência e compensação da F06;
- UI e gesto final da F08;
- criação de Foundry connection ou armazenamento de credencial;
- execução de tool em discovery/health;
- motor universal de policy ou analisador de compatibilidade semântica de JSON Schema;
- hierarquia e delegação cross-tenant da F12.
