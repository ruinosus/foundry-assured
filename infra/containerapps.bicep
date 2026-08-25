// Phase 7 (publish): backend + web + mcp on Azure Container Apps. azd builds each image,
// pushes to the ACR, and deploys it to the container app tagged with its
// azd-service-name. All three run as the shared user-assigned identity (created in
// resources.bicep) for ACR pull; the backend and the MCP server also call Foundry + the
// search KB as that identity. The apps reference each other by FQDN derived from the
// environment's defaultDomain, so there's no circular dependency between them.
//
// O `mcp` é uma unidade de deploy PRÓPRIA desde a Fase 0c (ADR-027) — o `/mcp` deixou de ser
// servido pelo backend. Sobre FastMCP 4, num venv que não cabe no do backend: o teto `mcp<2`
// vem do extra `agents` do backend, e o FastMCP 4 exige `mcp>=2,<3`.

@description('Location for all resources.')
param location string

@description('Tags applied to every resource.')
param tags object = {}

@description('Short unique token for resource names.')
param resourceToken string

@description('ACR name (login server is <name>.azurecr.io).')
param registryName string

@description('Resource id of the shared user-assigned identity.')
param appIdentityId string

@description('Client id of the shared user-assigned identity (for DefaultAzureCredential).')
param appIdentityClientId string

// Backend runtime config (mirrors backend/.env).
param foundryProjectEndpoint string
param foundryModel string
param azureSearchEndpoint string
param azureSearchKnowledgeBase string
param entraTenantId string = ''
param entraApiClientId string = ''
@secure()
param entraApiClientSecret string = ''

@description('Entra group of app users — the private read audience of the selfwiki KB. When set, retrieval sends the per-user OBO ACL header for /selfwiki; empty leaves selfwiki fail-closed.')
param appUsersGroupId string = ''

@secure()
@description('Chave (>= 32 bytes) que assina o `requestState` da decisão humana do MCP (SEP-2322). Vinda do cofre para o ambiente do azd — NUNCA um valor no repositório (ADR-005). Vazia é modo suportado: o servidor sobe e só a tool de escrita `open_ticket` se declara indisponível. Ver apps/mcp/mcp_app/request_state.py.')
param mcpRequestStateKey string = ''

@secure()
@description('Chave que cifra o SNAPSHOT DE CONTEXTO das tasks em repouso no Redis (FASTMCP_TASKS_ENCRYPTION_KEY). O snapshot carrega o ACCESS TOKEN do chamador — sem a chave, o pacote grava JSON em claro, o que NORDOR-122 proíbe. Vazia é modo suportado: as tasks não sobem e a busca continua síncrona. Gere com: python -c "import secrets; print(secrets.token_hex(32))"')
param mcpTasksEncryptionKey string = ''

@description('Provisiona o Azure Cache for Redis (Basic C0, ~US$16/mês SEMPRE LIGADO) que sustenta as background tasks (SEP-2663) e o estado de sessão por usuário do servidor MCP. FALSE mantém o custo ocioso em zero e degrada as duas coisas de forma declarada: a busca só roda síncrona e a sessão vira memória de processo, que o `minReplicas: 0` apaga. Nada mais no produto depende dele.')
param deployRedis bool = true

@description('Storage account backing the Azure Files share for persisted app data.')
param storageAccountName string
@description('Blob container do corpus (azd: AZURE_STORAGE_CONTAINER). O backend monta a URL do documento com ele.')
param corpusContainerName string = ''
@description('Resource id da conta de storage (azd: AZURE_STORAGE_RESOURCE_ID).')
param storageResourceId string = ''
@description('Endpoint Azure OpenAI do recurso Foundry (azd: AZURE_AI_OPENAI_ENDPOINT).')
param azureAiOpenAiEndpoint string = ''
@description('Deployment de embedding (azd: FOUNDRY_EMBEDDING_MODEL).')
param embeddingModelName string = ''

@description('Azure Files share mounted into the backend at /app/data (tickets.jsonl).')
param fileShareName string

@description('Azure Files share holding the runtime agent definitions, mounted read-only into the backend at /mnt/agents (ADR-014). Empty share = backend falls back to the definitions baked into the image.')
param promptsShareName string

// O ÚNICO ARMAZENAMENTO DURÁVEL QUE O SERVIDOR MCP TEM PARA CHAMAR DE SEU, e ele existe por uma
// razão só: `minReplicas: 0`. Este app não é um servidor ocioso — é um servidor que DESLIGA. Toda
// peça de escala do FastMCP 4 assume, por padrão, memória de processo (`DocketSettings.url =
// memory://`, descrito na própria fonte como "single process only"; `MemoryStore()` para sessão),
// e memória de processo aqui é memória que some entre uma chamada e a seguinte, por design.
//
// MEDIDO ANTES DE PROVISIONAR: uma task submetida num processo e consultada de outro responde
// `Task <id> not found` — DEPOIS de o servidor ter prometido `ttl_ms=900000` e
// `poll_interval_ms=5000` ao cliente. Não é degradação; é uma promessa que o servidor não tem
// como cumprir. Duas peças da Fase 5 (tasks e sessão por usuário) dependem disto e nenhuma outra
// parte do produto depende: por isso um recurso só, e por isso ele é opcional.
//
// POR QUE AQUI E NÃO EM `resources.bicep`, onde moram storage e search. A URL de conexão do Redis
// contém a chave de acesso, e passá-la de um módulo para outro exigiria um `output` com
// `listKeys()` dentro — exatamente o que o linter do Bicep sinaliza
// (`outputs-should-not-contain-secrets`), e com razão: output de módulo fica registrado no
// histórico de deployment. Montada aqui, a URL nasce e morre dentro do mesmo arquivo que a
// consome, e chega ao container como Container App secret, como os outros dois.
//
// POR QUE CHAVE DE ACESSO E NÃO ENTRA ID, que seria o caminho sem segredo. `pydocket` recebe uma
// URL string (`Docket(url=...)`, lido na fonte instalada) e a repassa ao `redis-py`; a auth do
// Entra para Redis exige um `CredentialProvider` que renove o token, porque o token expira em
// ~1h. Não há como expressar isso numa URL estática. A ADR-005 continua de pé pelo mesmo motivo
// que vale para `ENTRA_API_CLIENT_SECRET`: é credencial da NOSSA infraestrutura, entregue pelo
// pipeline, nunca segredo de cliente e nunca um valor no repositório.
//
// `Basic C0` é o menor SKU e não tem réplica — perder o cache perde tasks em voo e preferências
// de sessão, e nada além disso. Nenhum dado do produto mora aqui: chamado, trilha e documento
// continuam no storage. TLS obrigatório (`enableNonSslPort: false`), que é o que torna o esquema
// `rediss://` abaixo o único possível.
resource redis 'Microsoft.Cache/redis@2024-11-01' = if (deployRedis) {
  name: 'redis-mcp-${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'Basic', family: 'C', capacity: 0 }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled' // o Container Apps environment sai pela internet; sem VNet aqui
    redisConfiguration: {
      // Sem persistência (o SKU Basic não a oferece) e, quando a memória enche, o que sai é a
      // chave menos usada COM TTL. `allkeys-lru` despejaria também o que o docket usa para
      // rastrear execução, o que corromperia uma task em voo em vez de expirá-la.
      'maxmemory-policy': 'volatile-lru'
    }
  }
}

// A URL que o `pydocket` e o store de sessão recebem. `uriComponent()` NÃO É DECORAÇÃO: a chave
// de acesso do Redis é base64 e pode conter `/` e `+`, e um `/` na senha parte a URL em dois —
// o cliente tentaria conectar num host que não existe, com um erro que não fala de senha.
var redisUrl = deployRedis
  ? 'rediss://:${uriComponent(redis.listKeys().primaryKey)}@${redis.properties.hostName}:${redis.properties.sslPort}/0'
  : ''

var placeholderImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
var backendAppName = 'ca-backend-${resourceToken}'
var webAppName = 'ca-web-${resourceToken}'
var mcpAppName = 'ca-mcp-${resourceToken}'

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-assured-${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-assured-${resourceToken}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// Azure Files persistence for app data (tickets). Files access is account-key only
// (no managed identity for the share key), so we pull it via listKeys.
resource storageAcct 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource envDataStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: env
  name: 'data'
  properties: {
    azureFile: {
      accountName: storageAccountName
      accountKey: storageAcct.listKeys().keys[0].value
      shareName: fileShareName
      accessMode: 'ReadWrite'
    }
  }
}

// Runtime agent definitions (ADR-014, production leg). Read-only: the runtime
// only READS prompts; publishing goes through scripts/push-prompts.sh (upload
// to the share + revision restart), never through the app.
resource envPromptsStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: env
  name: 'prompts'
  properties: {
    azureFile: {
      accountName: storageAccountName
      accountKey: storageAcct.listKeys().keys[0].value
      shareName: promptsShareName
      accessMode: 'ReadOnly'
    }
  }
}

// Predictable external FQDNs from the env's default domain — breaks the
// backend⇄web circular reference (both derive from `env`, created first).
var backendFqdn = '${backendAppName}.${env.properties.defaultDomain}'
var webFqdn = '${webAppName}.${env.properties.defaultDomain}'
var mcpFqdn = '${mcpAppName}.${env.properties.defaultDomain}'

resource backendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: backendAppName
  location: location
  tags: union(tags, { 'azd-service-name': 'backend' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${appIdentityId}': {} }
  }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        { server: '${registryName}.azurecr.io', identity: appIdentityId }
      ]
      // SÓ declara o segredo quando ELE EXISTE. A Azure recusa um secret sem valor
      // (`ContainerAppSecretInvalid: value or keyVaultUrl and identity should be provided`) e
      // derruba o container app INTEIRO — o backend simplesmente não é criado, enquanto o `web`,
      // que não declara segredo nenhum, sobe normal. O resultado é um resource group com tudo
      // no lugar e um buraco em forma de backend, que não se parece com uma falha de deploy.
      //
      // O caminho PADRÃO do repositório cai exatamente aqui: `up-all.sh` sem `--with-auth` não
      // cria as app registrations, então `entraApiClientSecret` fica `''` — e um clone novo não
      // conseguia subir. Vazio agora significa "sem sign-in", que é um modo suportado.
      secrets: empty(entraApiClientSecret) ? [] : [
        { name: 'entra-api-secret', value: entraApiClientSecret }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: placeholderImage
          resources: { cpu: json('0.5'), memory: '1.0Gi' }
          env: concat([
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
            { name: 'FOUNDRY_MODEL', value: foundryModel }
            { name: 'AZURE_SEARCH_ENDPOINT', value: azureSearchEndpoint }
            { name: 'AZURE_SEARCH_KNOWLEDGE_BASE', value: azureSearchKnowledgeBase }
            // selfwiki domain (grounded on this repo's deep-wiki). Setting this mounts /selfwiki;
            // ingest selfwiki-kb so retrieval has data (build_selfwiki_agent tolerates a missing KB at boot).
            { name: 'SELFWIKI_SEARCH_KNOWLEDGE_BASE', value: 'selfwiki-kb' }
            // platform domain (tool-driven, MCP). mcp_enabled defaults false in code, so /platform only
            // mounts when this is true. The first-party MS MCP servers (Learn, etc.) need no extra infra.
            { name: 'MCP_ENABLED', value: 'true' }
            { name: 'FRONTEND_ORIGIN', value: 'https://${webFqdn}' }
            { name: 'AZURE_CLIENT_ID', value: appIdentityClientId }
            { name: 'ENTRA_TENANT_ID', value: entraTenantId }
            { name: 'ENTRA_API_CLIENT_ID', value: entraApiClientId }
            // `MCP_PUBLIC_BASE_URL` NÃO ENTRA AQUI. Desde a Fase 0c (ADR-027) o backend não serve
            // `/mcp`: quem serve é o container app `mcp` (mais abaixo), e é lá que a variável
            // precisa apontar para o ingress DELE. Deixá-la aqui faria o backend anunciar um
            // recurso OAuth que ele não hospeda.
            // selfwiki audience: the app-users group is the self-wiki's private read audience;
            // retrieval sends the OBO ACL header only when this is set (else /selfwiki fails closed).
            { name: 'APP_USERS_GROUP_ID', value: appUsersGroupId }
            // Runtime agent-definition override (ADR-014, production leg): the
            // backend composes prompts from $AGENTS_DIR/assured when that
            // scope exists on the mounted share, else falls back (loudly) to
            // the copy baked into the image. Prompt update = push-prompts.sh.
            // ── Storage. SEM estes o backend monta `https://.blob.core.windows.net/...`:
            // `/source` filtra o índice por `blob_url eq` e não casa com nada (403 numa citação
            // que o agente acabou de emitir), e o store de conversas não acha container nenhum
            // (lista vazia + 404 em /conversations/by-id). O parâmetro storageAccountName já
            // chegava aqui desde sempre — era usado só para o file share, nunca exposto ao app.
            { name: 'AZURE_STORAGE_ACCOUNT', value: storageAccountName }
            { name: 'AZURE_STORAGE_CONTAINER', value: corpusContainerName }
            { name: 'AZURE_STORAGE_RESOURCE_ID', value: storageResourceId }
            // Usados pela escrita de conhecimento e pela ingestão a partir do app.
            { name: 'AZURE_AI_OPENAI_ENDPOINT', value: azureAiOpenAiEndpoint }
            { name: 'FOUNDRY_EMBEDDING_MODEL', value: embeddingModelName }
            { name: 'AGENTS_DIR', value: '/mnt/agents' }
          ], empty(entraApiClientSecret) ? [] : [
            // Pareado com o `secrets` acima: um `secretRef` apontando para um segredo que não
            // foi declarado é o MESMO erro de deployment. Os dois aparecem ou somem juntos.
            { name: 'ENTRA_API_CLIENT_SECRET', secretRef: 'entra-api-secret' }
          ])
          volumeMounts: [
            { volumeName: 'data', mountPath: '/app/data' } // tickets.jsonl persists here
            { volumeName: 'prompts', mountPath: '/mnt/agents' } // agent definitions (read-only share)
          ]
        }
      ]
      volumes: [
        { name: 'data', storageType: 'AzureFile', storageName: envDataStorage.name }
        { name: 'prompts', storageType: 'AzureFile', storageName: envPromptsStorage.name }
      ]
      // Single replica: the persisted jsonl is append-based, so >1 writer could
      // interleave/corrupt it. Scale-to-zero still applies (idle = $0).
      scale: { minReplicas: 0, maxReplicas: 1 }
    }
  }
}

resource webApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: webAppName
  location: location
  tags: union(tags, { 'azd-service-name': 'web' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${appIdentityId}': {} }
  }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 3000
        transport: 'auto'
      }
      registries: [
        { server: '${registryName}.azurecr.io', identity: appIdentityId }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: placeholderImage
          resources: { cpu: json('0.5'), memory: '1.0Gi' }
          env: [
            // Server-side (Next route handlers) — runtime env is fine here. The
            // browser-side NEXT_PUBLIC_* are baked at image build (see azure.yaml).
            { name: 'BACKEND_URL', value: 'https://${backendFqdn}' }
            { name: 'AGUI_URL', value: 'https://${backendFqdn}/helpdesk' }
            { name: 'HOSTED_AGUI_URL', value: 'https://${backendFqdn}/helpdesk-hosted' }
            // Second domain (TechDocs expert). Without this the /techdocs route proxies
            // to the localhost default and fails (405/fetch) in the container.
            { name: 'TECHDOCS_AGUI_URL', value: 'https://${backendFqdn}/techdocs' }
          ]
        }
      ]
      scale: { minReplicas: 0, maxReplicas: 3 }  // scale-to-zero: idle = $0 (cold start on first request)
    }
  }
}

// O servidor MCP (ADR-027). ELE TEM DOIS SEGREDOS, e o comentário que dizia "SEM SEGREDO" foi
// reescrito porque envelheceu duas vezes.
//
// A frase original era verdadeira para a Fase 0c: como Resource Server, ele valida o token do
// Entra com `AzureJWTVerifier`, que não pede `client_secret` nenhum. A Fase 3 (T3) já a
// contradisse ao trazer `MCP_REQUEST_STATE_KEY` — e ela também não cobria o que ele SEMPRE fez:
// `search_docs` chama o `knowledge.retrieve` do backend, que troca o token do chamador por um
// token de busca via **OBO**, e OBO é fluxo de cliente confidencial. Sem credencial de cliente,
// `OnBehalfOfCredential(..., client_secret='')` levanta, medido:
//
//     TypeError: Either "client_certificate", "client_secret", or "client_assertion_func"
//     must be provided
//
// Enquanto o `/mcp` morava no monolito isso nunca apareceu: o backend tem o segredo. Separado o
// app e copiadas só `ENTRA_TENANT_ID`/`ENTRA_API_CLIENT_ID`, a tool principal nasceria morta no
// primeiro deploy autenticado — e `mask_error_details=True` a devolveria como erro interno
// genérico.
//
// A ADR-005 CONTINUA DE PÉ, e é bom dizer por quê em vez de deixar a dúvida. Ela proíbe guardar
// **segredo do cliente** no control plane; `ENTRA_API_CLIENT_SECRET` é a credencial da NOSSA app
// registration, entregue como Container App secret pelo mesmo pipeline que já a entrega ao
// backend — nenhum segredo de cliente é armazenado, e nenhum valor mora no repositório.
//
// A ALTERNATIVA SEM SEGREDO FOI AVALIADA E RECUSADA POR ORA: `client_assertion_func` sobre a
// managed identity (federated identity credential) é aceito por esta versão do `azure-identity`
// (assinatura lida na fonte instalada, 1.26.0b2). O que falta não é código — é a federação no
// Entra: uma FIC na app registration da API confiando na identidade gerenciada, que só existe
// depois do `azd provision`, enquanto `scripts/setup-entra.sh` roda ANTES dele (`up-all.sh`).
// Sem essa configuração, o app trocaria "nasce morto por falta de segredo" por "nasce morto por
// falta de federação" — com o agravante de o segundo virar um 401 do Entra no meio da primeira
// busca, em vez de um erro de construção. Fica registrado como o próximo passo, não como este.
//
// O que ele precisa é ler: o endpoint do Foundry e do Search (a tool `search_docs` chama o
// MESMO `knowledge.retrieve` do backend, com o trim de ACL sob a identidade de quem perguntou),
// o storage (trilha de auditoria da ADR-023 + a URL do documento) e o Entra (para saber quem é
// o chamador). NÃO precisa do share de prompts: a tool não usa as instruções dos agentes, e sem
// `AGENTS_DIR` o pacote usa a cópia embutida na imagem (ADR-014).
//
// DESDE A FASE 3 ELE TAMBÉM ESCREVE, e isso trouxe DUAS coisas que ele não tinha:
//
//   1. MAIS UM SEGREDO — `MCP_REQUEST_STATE_KEY`, a chave que assina o `requestState` entre a
//      pergunta ao aprovador e a resposta dele. Declarado exatamente como o `entra-api-secret`
//      do backend (só quando existe, senão a Azure recusa o container app INTEIRO com
//      `ContainerAppSecretInvalid`), e vazio continua sendo modo suportado: o servidor sobe e a
//      escrita se declara indisponível. Nunca há valor no repositório (ADR-005).
//   2. O MOUNT `/srv/backend/data` — o MESMO share Azure Files do backend, em OUTRO caminho.
//      `create_ticket` grava em `<raiz do backend>/data/tickets.jsonl`, e a raiz do backend é
//      diferente em cada imagem: no `apps/backend/Dockerfile` ela é `/app` (daí `/app/data` no
//      container do backend), e no `apps/mcp/Dockerfile` ela é `/srv/backend`. Medido na
//      imagem: `docker run … python -c "import app; print(app.__file__)"` →
//      `/srv/backend/app/__init__.py`, e `/app` NEM EXISTE ali.
//
//      A primeira versão deste mount copiou o `/app/data` do backend, e o efeito foi
//      exatamente o que ele existia para evitar: o chamado aberto por MCP caía no disco
//      efêmero da réplica — a escrita "funcionava", o cliente recebia o id, e a página
//      `/tickets` do produto nunca o via. Pior, `data/decisoes/` (a reserva de nonce da
//      Fase 3) morria no scale-to-zero junto com a réplica, e o mesmo `requestState` selado
//      escrevia de novo dentro do TTL — o invariante "um `requestState`, uma escrita"
//      evaporava no cenário que ele existe para cobrir.
//
//      POR QUE O BICEP MUDA, E NÃO O DOCKERFILE. `apps/mcp/pyproject.toml` declara o backend
//      por path (`{ path = "../backend" }`), o que obriga os dois a serem IRMÃOS na imagem —
//      não há layout de diretórios que ponha a raiz do backend em `/app` e o app do MCP em
//      `/srv/mcp` ao mesmo tempo. E o `mountPath` é declaração POR CONTAINER: cada imagem tem
//      a sua raiz, e é o bicep que diz onde o share aparece em cada uma. Quem impede as duas
//      de divergirem de novo é `apps/mcp/tests/image_data_path_test.py`, que roda DENTRO da
//      imagem e compara o caminho que o código resolve com o `mountPath` daqui.
resource mcpApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: mcpAppName
  location: location
  tags: union(tags, { 'azd-service-name': 'mcp' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${appIdentityId}': {} }
  }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8001 // o mesmo do Dockerfile de apps/mcp
        transport: 'auto'
      }
      registries: [
        { server: '${registryName}.azurecr.io', identity: appIdentityId }
      ]
      // Mesma regra do backend: segredo sem valor derruba o container app inteiro, então cada um
      // só é declarado quando existe — e o `secretRef` correspondente aparece e some junto com
      // ele. São DOIS, e independentes: `entra-api-secret` é o que permite o OBO da leitura,
      // `mcp-request-state-key` é o que sela a decisão humana da escrita. Um deployment sem
      // sign-in não tem o primeiro; um sem escrita não tem o segundo; os dois modos sobem.
      secrets: concat(
        empty(mcpRequestStateKey) ? [] : [
          { name: 'mcp-request-state-key', value: mcpRequestStateKey }
        ],
        empty(entraApiClientSecret) ? [] : [
          { name: 'entra-api-secret', value: entraApiClientSecret }
        ],
        // OS DOIS DA FASE 5 (T7), E ELES ANDAM JUNTOS DE PROPÓSITO. O código exige AMBOS para
        // ligar as tasks (`mcp_app/tasks_backend.py`): a URL sem a chave gravaria o snapshot de
        // contexto — que carrega o access token do chamador — em JSON claro dentro do Redis, e
        // um token de usuário em claro num cache é o achado que NORDOR-122 descreve por extenso.
        // Falta um, as tasks não sobem; a busca continua síncrona e nada mais muda.
        empty(redisUrl) ? [] : [
          { name: 'mcp-redis-url', value: redisUrl }
        ],
        empty(mcpTasksEncryptionKey) ? [] : [
          { name: 'mcp-tasks-encryption-key', value: mcpTasksEncryptionKey }
        ]
      )
    }
    template: {
      containers: [
        {
          name: 'mcp'
          image: placeholderImage
          resources: { cpu: json('0.5'), memory: '1.0Gi' }
          env: concat([
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
            { name: 'AZURE_SEARCH_ENDPOINT', value: azureSearchEndpoint }
            { name: 'AZURE_SEARCH_KNOWLEDGE_BASE', value: azureSearchKnowledgeBase }
            { name: 'SELFWIKI_SEARCH_KNOWLEDGE_BASE', value: 'selfwiki-kb' }
            { name: 'APP_USERS_GROUP_ID', value: appUsersGroupId }
            { name: 'AZURE_CLIENT_ID', value: appIdentityClientId }
            { name: 'ENTRA_TENANT_ID', value: entraTenantId }
            { name: 'ENTRA_API_CLIENT_ID', value: entraApiClientId }
            // `resource` da metadata OAuth (RFC 9728) — o ingress DESTE app, não o do backend.
            // Sem isto o servidor anuncia o default `http://localhost:8001` e nenhum cliente MCP
            // externo descobre onde se autenticar. Era a variável que apontava para o backend
            // enquanto o `/mcp` morava lá; apontá-la para o vizinho errado é a mesma família de
            // falha do commit 007f399, só que mais silenciosa — o 401 traz uma placa que leva a
            // um host que não hospeda este recurso.
            { name: 'MCP_PUBLIC_BASE_URL', value: 'https://${mcpFqdn}' }
            // `FRONTEND_ORIGIN` SAIU DAQUI junto com o `CORSMiddleware` deste app: era a
            // única coisa que o lia. Uma variável de ambiente que ninguém consome parece
            // configuração feita e não é. O backend continua com a dele (linha ~185), que
            // tem consumidor de verdade.
            { name: 'AZURE_STORAGE_ACCOUNT', value: storageAccountName }
            { name: 'AZURE_STORAGE_CONTAINER', value: corpusContainerName }
            { name: 'AZURE_STORAGE_RESOURCE_ID', value: storageResourceId }
          ], empty(mcpRequestStateKey) ? [] : [
            { name: 'MCP_REQUEST_STATE_KEY', secretRef: 'mcp-request-state-key' }
          ], empty(redisUrl) ? [] : [
            // O BACKEND DURÁVEL DAS TASKS E DA SESSÃO POR USUÁRIO. Uma variável para as duas
            // peças, porque é UM recurso: `mcp_app/tasks_backend.py` a entrega ao `TasksExtension`
            // e `mcp_app/sessions.py` ao store do `session_state_store`. Ausente, as duas
            // degradam de forma declarada e provada por gate.
            { name: 'MCP_REDIS_URL', secretRef: 'mcp-redis-url' }
          ], empty(mcpTasksEncryptionKey) ? [] : [
            // O NOME É DO PACOTE, não nosso: `fastmcp_tasks.settings.TasksSettings` lê o prefixo
            // `FASTMCP_TASKS_`. Repassar de uma variável nossa seria inventar um segundo nome
            // para o mesmo valor — o pacote continuaria lendo o dele, e a configuração
            // "aplicada" não teria efeito nenhum, em silêncio.
            { name: 'FASTMCP_TASKS_ENCRYPTION_KEY', secretRef: 'mcp-tasks-encryption-key' }
          ], empty(entraApiClientSecret) ? [] : [
            // A CREDENCIAL DO OBO. `ENTRA_TENANT_ID` e `ENTRA_API_CLIENT_ID` já estavam aqui;
            // sem esta terceira, `knowledge.retrieve` levanta ao construir a credencial e
            // `search_docs`, `document://` e a completion de nome morrem no primeiro uso
            // autenticado. Ver o comentário grande acima do recurso.
            { name: 'ENTRA_API_CLIENT_SECRET', secretRef: 'entra-api-secret' }
          ])
          volumeMounts: [
            // O MESMO share do backend, em CAMINHO DIFERENTE — porque a raiz do backend nesta
            // imagem é `/srv/backend`, não `/app` (medido; ver o comentário grande acima do
            // recurso). Os dois apps escrevem o mesmo `tickets.jsonl` e as mesmas reservas de
            // decisão; a página `/tickets` lê pelo backend.
            { volumeName: 'data', mountPath: '/srv/backend/data' }
          ]
        }
      ]
      volumes: [
        { name: 'data', storageType: 'AzureFile', storageName: envDataStorage.name }
      ]
      // UMA RÉPLICA, e não por causa de arquivo: o transporte HTTP do MCP mantém sessão no
      // processo, então duas réplicas sem afinidade fariam a segunda requisição de uma sessão
      // cair num processo que não a conhece. Scale-to-zero continua valendo (ocioso = $0).
      //
      // A CHAVE DO `requestState` CONTINUA SENDO NECESSÁRIA MESMO COM UMA RÉPLICA SÓ, e é o
      // `minReplicas: 0` que explica: a réplica MORRE por ociosidade entre a pergunta ao
      // aprovador e a resposta dele. Com a chave efêmera do processo (o default do FastMCP), o
      // estado emitido antes do desligamento não seria aceito depois — a aprovação viraria
      // `Invalid or expired requestState` de forma intermitente.
      scale: { minReplicas: 0, maxReplicas: 1 }
    }
  }
}

output BACKEND_URL string = 'https://${backendApp.properties.configuration.ingress.fqdn}'
output WEB_URL string = 'https://${webApp.properties.configuration.ingress.fqdn}'
output MCP_URL string = 'https://${mcpApp.properties.configuration.ingress.fqdn}'
