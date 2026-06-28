# Execução, Deploy e Automação

Abaixo estão apenas fatos presentes nos arquivos-fonte fornecidos, com indicação do arquivo de origem.

## Arquivos relevantes
- DEPLOYMENT.md — guia de Deployment & provisioning (passo a passo, scripts, comandos) (DEPLOYMENT.md)  
- RELEASE-AUTOMATION.md — guia de Release & deploy automation (GitHub App token vs PAT, fluxo, setup do App) (RELEASE-AUTOMATION.md)

## Quickstart / comandos principais
- Fluxo curto (do root do repositório), após `azd auth login && az login`:

```bash
azd up
./scripts/setup-entra.sh
./scripts/bootstrap.sh

cd apps/backend  && uv run uvicorn app.main:app --port 8000 --reload
cd apps/frontend && npm install && npm run dev
```

(DEPLOYMENT.md)

- Instrução explícita: pular `setup-entra.sh` roda sem sign-in (usa `DefaultAzureCredential`). (DEPLOYMENT.md)

## O que é provisionado (resumo)
- Infra via Bicep executado por `azd up` (Foundry account + project + models, Azure AI Search, Storage, ACR, Container Apps env, RBAC). (DEPLOYMENT.md)
- Knowledge base e memory store via scripts Python (`apps/backend/{app/knowledge/ingest.py, cli/}`) ou `scripts/bootstrap.sh`. (DEPLOYMENT.md)
- Entra app registrations (SPA + API) via `scripts/setup-entra.sh` (ou manual). (DEPLOYMENT.md)
- Hosted agent (Foundry Agent Service) via `azd deploy helpdesk-concierge` + post-deploy RBAC; código sob `apps/hosted-agent/`. (DEPLOYMENT.md)
- Backend e frontend em Container Apps; comandos de deploy/infra documentados (DEPLOYMENT.md)

(DEPLOYMENT.md)

## Pré-requisitos citados
- Azure subscription com direitos para criar recursos e atribuir roles; Hosted agents requerem Foundry Project Manager no escopo do projeto. (DEPLOYMENT.md)  
- Ferramentas: `azd` ≥ 1.26, `az` CLI ≥ 2.80, `uv`, Node 20+, Docker (opcional). (DEPLOYMENT.md)  
- `az bicep` está mencionado como ferramenta para compilação/verificação de infra (DEPLOYMENT.md)

## Passos documentados (resumo)
- Step 1: `azd up` provisiona recursos descritos e fornece variáveis de saída a ler via `azd env get-values`. (DEPLOYMENT.md)  
- Step 2: copiar `apps/backend/.env.example` → `.env` e preencher variáveis (`FOUNDRY_PROJECT_ENDPOINT`, `AZURE_SEARCH_ENDPOINT`, `AZURE_STORAGE_*`, etc.) a partir de `azd env get-values`. (DEPLOYMENT.md)  
- Step 3: opcional — criar duas app registrations (API e SPA) para sign-in + OBO; há um script `./scripts/setup-entra.sh` que realiza essa etapa idempotentemente e escreve env files; as instruções manuais detalhadas estão no arquivo. (DEPLOYMENT.md)  
- Step 4: ingestão de KB e provisionamento de memory store via scripts Python (`uv run python -m app.knowledge.ingest` e `uv run python -m cli.provision_memory`) ou `./scripts/bootstrap.sh`. (DEPLOYMENT.md)  
- Step 5: comandos para rodar localmente backend e frontend (`uvicorn` e `npm run dev`) e observações sobre endpoints locais. (DEPLOYMENT.md)  
- Step 6: deploy do agente hospedado com `azd deploy helpdesk-concierge` e comandos de verificação/invocação; há nota sobre post-deploy RBAC para a identidade gerada no deploy. (DEPLOYMENT.md)

(DEPLOYMENT.md)

## Release & deploy automation — pontos essenciais
- O fluxo documentado usa release-please para gerar PRs de release, uma workflow que cria a Release, e um deploy acionado por evento de release; o diagrama e a descrição do fluxo estão no arquivo. (RELEASE-AUTOMATION.md)  
- Observação chave: `GITHUB_TOKEN` não pode acionar outros workflows; por isso recomenda-se usar um GitHub App installation token (curta duração) em vez de um PAT. (RELEASE-AUTOMATION.md)  
- Comparativo de opções listado: PAT (pessoa) vs GitHub App installation token (~1 hora, recomendado). (RELEASE-AUTOMATION.md)  
- Instruções passo a passo para criar o GitHub App: criar App, gerar private key, instalar no repositório e armazenar App ID e private key como variables/secrets (exemplos de comandos `gh variable set` / `gh secret set` estão no arquivo). (RELEASE-AUTOMATION.md)  
- O workflow do repositório já contém passos que mintam o token do App e invocam release-please, com fallback para `GITHUB_TOKEN` enquanto a variável/secret do App não existirem. (RELEASE-AUTOMATION.md)  
- Há uma descrição de um safety-net que corta a release automaticamente se `release-please` abortar por PRs mesclados não taggeados; a rotina usa o mesmo App token. (RELEASE-AUTOMATION.md)  
- Lista de controles de segurança e postura (OIDC para cloud auth, proteção de environment para produção, branch protection, least-privilege permissions, sem segredos no repo exceto variáveis de ambiente) conforme o arquivo. (RELEASE-AUTOMATION.md)

(RELEASE-AUTOMATION.md)

---

Notas: este documento apresenta apenas afirmações literais contidas nos arquivos fornecidos, com referência aos respectivos arquivos.