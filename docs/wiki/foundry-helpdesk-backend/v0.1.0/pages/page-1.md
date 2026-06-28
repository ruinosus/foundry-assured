# Fatos suportados pelos arquivos-fonte

- Imagem base do container: python:3.12-slim. (Dockerfile)  
- WORKDIR no container: /app. (Dockerfile)  
- O Dockerfile instala o utilitário `uv` e o usa para sincronizar dependências a partir de `pyproject.toml` e `uv.lock`. (Dockerfile)  
- O código da aplicação é copiado para `/app` e o PATH é ajustado para `/app/.venv/bin`. (Dockerfile)  
- O container expõe a porta 8000 e o comando de execução padrão é `uvicorn app.main:app --host 0.0.0.0 --port 8000`. (Dockerfile)

- O projeto se chama "foundry-helpdesk-backend" e a versão declarada é "0.1.0". (pyproject.toml)  
- Dependências declaradas incluem, entre outras, `agent-framework>=1.9.0`, `agent-framework-ag-ui>=1.0.0rc5`, `azure-identity>=1.25.3`, `fastapi>=0.115.0`, e `uvicorn[standard]>=0.32.0`. (pyproject.toml)

- O README do backend descreve a aplicação como "FastAPI + Microsoft Agent Framework, expondo o helpdesk agent over AG-UI" e afirma que "Auth is always `DefaultAzureCredential`". (README.md)

- O entrypoint FastAPI declara a app com title "Foundry Helpdesk" e version "0.1.0", define um lifespan assíncrono que, se `azure_scheme` não for None, pré-carrega a configuração OpenID, e chama `hosted_aclose()` ao encerrar. (app/main.py)  
- A aplicação adiciona CORSMiddleware com `allow_origins=[settings.frontend_origin]`. (app/main.py)  
- O router `api_router` é incluído na app. (app/main.py)  
- O endpoint do AG-UI é registrado em `/helpdesk`. Se a função `_knowledge_configured()` retorna True, o endpoint usa `OrderedAgentFrameworkWorkflow(workflow_factory=build_helpdesk_workflow)` com dependências `auth_dependencies()`; caso contrário, registra `build_concierge_agent()` em `/helpdesk`. (app/main.py)  
- Um endpoint adicional em `/cockpit` é registrado somente se `cockpit_configured()` retorna True, usando `build_cockpit_agent()` e `auth_dependencies()`. (app/main.py)  
- Um endpoint adicional em `/selfwiki` é registrado somente se `selfwiki_configured()` retorna True, usando `build_selfwiki_agent()` e `auth_dependencies()`. (app/main.py)  
- Quando executado como script, o módulo chama `uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)`. (app/main.py)

- A pasta `eval/` contém documentação e scripts para avaliação e gates de garantia, incluindo políticas determinísticas (`assertions.py`), rubricas (`rubrics/helpdesk_quality.md`), um runner (`run_eval.py`) e um arquivo de thresholds (`assurance.yaml`). O README de `eval/` descreve comandos de execução locais como `uv run python -m eval.run_eval` e variantes (`--cloud`, `--safety`, `--self-test`). (eval/README.md)