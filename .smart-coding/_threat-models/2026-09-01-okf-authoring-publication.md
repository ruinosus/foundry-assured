# Threat model — autoria OKF e publicação compensável

- **Data:** 2026-09-01
- **Escopo:** frontend CURA, autoria por tenant e área, SQLite/PostgreSQL, GitHub,
  Azure DevOps, Foundry, AI Search, aprovação e saga pós-merge
- **Método:** STRIDE, informado por NORDOR-122, NORDOR-107 e POLDOR-015
- **Status:** Proposto; revisão de segurança e arquitetura obrigatória antes da implementação

## Ativos e fronteiras de confiança

### Ativos protegidos

- identidade do usuário, `tid`, object ID, App Roles e grupos Entra;
- vínculo autorizado entre tenant, área e projeto Foundry;
- documentos OKF, AgentSchema, revisões, diffs e ChangeSets;
- aprovações, journal, chaves de idempotência e evidências de compensação;
- connections, consentimentos OAuth e tokens delegados, que nunca entram no armazenamento da aplicação;
- branches, commits, pull requests e recursos materializados no Foundry ou AI Search;
- snapshots MCP sanitizados, classificações administrativas e allowlists efetivas.

### Fronteiras de confiança

1. Navegador autenticado para APIs Next.js e backend.
2. Backend para validação Entra, resolução de tenant, área, papéis e grupos.
3. Backend para SQLite local ou PostgreSQL conectado.
4. Backend para Azure DevOps REST usando OBO.
5. Backend para Foundry Toolbox e GitHub MCP usando OAuth identity passthrough.
6. Provedores Git para a reconciliação pós-merge.
7. Backend para Foundry Agent Service e Azure AI Search.
8. Publicador para a trilha de auditoria e armazenamento WORM.

IDs, estados, descrições, schemas, annotations, mensagens de erro e respostas recebidas das
integrações são entrada não confiável. A autenticação no provedor não substitui autorização de
produto, isolamento por área, validação do ChangeSet nem aprovação da publicação.

## Fluxo de dados

1. O backend resolve tenant pelo token e deriva as áreas autorizadas dos grupos Entra.
2. Reader ou Author consulta um catálogo projetado das fontes donas dentro do tenant e área ativos.
3. Author cria ou revisa documentos; Builder e FormFlow produzem somente proposta e ChangeSet.
4. Checks determinísticos validam schema, referências, segredo, escopo, autorização e concorrência.
5. Approver revisa e confirma o ChangeSet normalizado; qualquer edição invalida a aprovação.
6. A saga usa a identidade delegada para criar branch, commit e pull request no provedor configurado.
7. O publicador consulta o provedor até confirmar que o pull request exato foi integrado.
8. O commit integrado é conferido contra os hashes aprovados e então materializado pelas APIs oficiais.
9. Cada operação registra estado, tentativa, resultado mínimo, compensação e correlação no journal.
10. Falha parcial é retomada, compensada ou encerrada como intervenção explícita, sem declarar sucesso.

## Análise STRIDE

| Categoria | Ameaça | Controle | Verificação |
|---|---|---|---|
| Spoofing | Cliente envia outro tenant ou área | Tenant vem somente do `tid`; área é derivada dos grupos autorizados; IDs enviados são revalidados no servidor | Testes negativos tenant A/área A, tenant A/área B e tenant B |
| Spoofing | Ator reutiliza aprovação de outro ChangeSet | Aprovação liga ator, revisão, hash canônico, tenant, área e finalidade; edição ou mudança de contexto invalida | Replay, troca de área e revisão concorrente |
| Spoofing | PR ou commit diferente é apresentado como o aprovado | Journal guarda provedor, repositório, PR, source/target refs e hash esperado; reconciliação consulta a fonte dona | PR adulterado, force-push e merge de commit diferente |
| Spoofing | Connection ou recurso homônimo cruza tenant | Toda resolução parte do projeto Foundry do tenant e do registro tenant-área autorizado | Mesmo nome em projetos e áreas diferentes |
| Tampering | Documento muda entre aprovação, commit e materialização | Canonicalização declarada, hashes por documento e do conjunto, comparação com o commit integrado | Alteração antes/depois do PR e diferença de normalização |
| Tampering | Duas publicações sobrescrevem revisão ou journal | Concorrência otimista, revisão esperada, chave de idempotência e transições condicionais | Corrida entre submissões, retries e workers |
| Tampering | Tool MCP muda após revisão | Snapshot sanitizado, hash, redescoberta e quarentena conforme ADR-033 | Drift de nome, schema, annotation e classificação |
| Repudiation | Autor ou Approver nega uma ação | Eventos append-only com ator, papéis, tenant, área, decisão, hashes, instante e correlação | Verificação da cadeia, recibo e exportação de auditoria |
| Repudiation | Retry cria efeitos sem vínculo | Toda tentativa referencia a mesma operação e chave de idempotência; recursos remotos são consultados antes de nova escrita | Timeout após sucesso remoto e retomada posterior |
| Information disclosure | Token, segredo ou consent URL chega ao banco, log ou documento | Schema recusa campos de segredo; credenciais são resolvidas em memória por OBO/Toolbox; respostas persistidas são allowlisted e redigidas antes da escrita | Canary de segredo em API, SQLite/PostgreSQL, logs, traces e auditoria |
| Information disclosure | Dados de autoria vazam entre áreas | Chaves, consultas, caches, snapshots, journal e auditoria incluem tenant e área; ausência e proibição são indistinguíveis externamente | Leitura, referência, aprovação e retomada entre áreas |
| Information disclosure | Erro externo expõe payload ou infraestrutura | Mapeamento para categoria de domínio; detalhe técnico somente no canal interno sanitizado | Erros 401/403/409/429/5xx com canaries |
| Denial of service | Upload, bundle, diff ou resposta externa esgota recursos | Limites de tamanho, quantidade e profundidade; paginação limitada; timeout e rate limit por tenant/área | Casos de borda e payload excessivo |
| Denial of service | Retry amplifica indisponibilidade do provedor | Máximo de três tentativas, backoff exponencial com jitter, `Retry-After` e retry apenas para 408/429/5xx ou transporte | Provedor falso, tempestade de 429 e falha prolongada |
| Denial of service | Saga fica presa indefinidamente | Lease de worker, transições persistidas, prazo por operação e estado terminal de intervenção | Queda entre etapas e expiração de lease |
| Elevation of privilege | Reader/Author publica ou Admin contorna Approver | Matriz fixa: Reader consulta, Author cria/submete, Approver aprova/publica e Admin configura; Admin só inicia remediação de agregado já em `compensation_required`; backend reaplica por endpoint e transição | Matriz completa de papéis e ausência de papel |
| Elevation of privilege | Grupo de outra área concede ação global | App Role autoriza a ação e grupo limita a área; o resultado efetivo é a interseção | Combinações de role sem grupo e grupo sem role |
| Elevation of privilege | Metadata MCP reduz risco de uma tool | Classificação administrativa e política usam o resultado mais restritivo; tool desconhecida é escrita de alto risco | Matriz de conflitos e aprovação nativa |
| Elevation of privilege | Builder ou FormFlow escreve externamente | Esses módulos só produzem proposta; somente o publicador aceita ChangeSet aprovado e transição válida | Gate arquitetural e teste de chamadas proibidas |
| Elevation of privilege | Recurso é criado antes do merge | Materialização exige consulta positiva do PR, commit integrado e igualdade de hash | Merge ausente, PR abandonado e commit divergente |

## Invariantes de segurança

1. Nenhuma requisição de autoria aceita tenant, projeto Foundry ou autoridade de área como verdade do cliente.
2. Nenhuma operação externa ocorre a partir de proposta, draft ou aprovação invalidada.
3. Nenhuma materialização ocorre antes da confirmação do merge e da comparação do commit integrado.
4. Nenhum token, segredo, header, URL de consentimento ou resposta externa bruta chega a armazenamento durável.
5. GitHub opera somente por OAuth identity passthrough oficial e falha fechado; não existe fallback para PAT persistido.
6. Azure DevOps usa OBO e o menor escopo que cobre branch, commit e pull request.
7. Retry nunca é automático para erro 4xx não transitório, conflito de ref, consentimento ou decisão humana.
8. Um check pendente nunca é convertido em aprovado por ausência do serviço.
9. A UI não é fronteira de autorização; cada leitura e transição é revalidada no backend.
10. Uma saga parcial nunca é apresentada como publicação concluída.

## Retenção e minimização

- Rascunho abandonado expira 90 dias após a última atividade.
- ChangeSet rejeitado ou cancelado e snapshots associados expiram 90 dias após o estado terminal.
- Publicação, journal e aprovação seguem a política de auditoria/WORM configurada pelo tenant.
- Produção não habilita publicação sem política explícita de retenção da auditoria.
- Documentos integrados seguem a retenção do repositório Git; telemetria permanece separada e retida por 30 dias.
- Legal hold suspende purge sem autorizar coleta adicional.

## Riscos residuais

- Um usuário legitimamente autorizado pode publicar conteúdo malicioso. Revisão, separação de papéis,
  proteção de branch e auditoria reduzem o risco, mas não substituem governança humana.
- OAuth, OBO, Foundry, AI Search e os provedores Git podem mudar contratos ou ficar indisponíveis.
  O sistema expõe bloqueio e reconciliação; não oferece fallback de credencial ou implementação própria.
- Redação determinística não reconhece todo dado sensível. A defesa principal é não coletar respostas
  externas brutas e proibir dado de paciente ou regulado neste produto.
- Compensação não equivale a transação distribuída. Alguns efeitos exigirão intervenção documentada.
- A segurança do PostgreSQL, WORM, egress e identidades depende da configuração implantada e precisa
  de smoke no ambiente; testes offline não provam esses controles de plataforma.

## Gates de segurança obrigatórios

- matriz de AuthN/AuthZ para papéis, tenant e área, incluindo cache e retomada;
- canary de segredo/PII em documentos, APIs, bancos, logs, traces, journal e auditoria;
- concorrência e idempotência com timeout depois de efeito remoto bem-sucedido;
- contratos GitHub e Azure DevOps para consentimento, escopo, conflito, rate limit e merge divergente;
- drift MCP e paridade de approval nativo conforme ADR-033;
- materialização impedida antes do merge e diante de hash divergente;
- rate limit e limites de payload nas rotas críticas;
- smoke implantado de PostgreSQL, OBO, OAuth passthrough, Foundry/Search e WORM;
- SAST, auditoria de dependências e triagem de findings novos antes do merge.
