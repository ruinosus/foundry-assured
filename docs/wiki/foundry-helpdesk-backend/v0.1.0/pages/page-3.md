Resumo ancorado no código-fonte:

- O entrypoint cria uma FastAPI app com title "Foundry Helpdesk" e version "0.1.0", e define um lifespan que carrega a config OpenID se azure_scheme não for None e chama hosted_aclose() ao terminar. (app/main.py)

- A aplicação adiciona CORSMiddleware com allow_origins = [settings.frontend_origin], allow_methods = ["*"], allow_headers = ["*"]. (app/main.py)

- O router principal é incluído via app.include_router(api_router). (app/main.py)

- Endpoints AG-UI registrados via add_agent_framework_fastapi_endpoint:
  - "/helpdesk": registrado com OrderedAgentFrameworkWorkflow(workflow_factory=build_helpdesk_workflow) se _knowledge_configured() for True; caso contrário registrado com build_concierge_agent(). (app/main.py)
  - "/cockpit": registrado com build_cockpit_agent() se cockpit_configured() for True, com dependências de autenticação. (app/main.py)
  - "/selfwiki": registrado com build_selfwiki_agent() se selfwiki_configured() for True, com dependências de autenticação. (app/main.py)

- Há um endpoint POST "/helpdesk-hosted" que recebe o corpo da requisição, chama stream_agui(body) e retorna um StreamingResponse com media_type "text/event-stream". (app/api/chat.py)

- Há um endpoint GET "/eval/runs" que, se o arquivo eval/runs.jsonl não existe, retorna {"runs": []}; caso exista, lê o arquivo linha a linha, decodifica JSON suprimindo erros, reverte a ordem e retorna {"runs": runs[:limit]}. (app/api/evals.py)

- Há um endpoint GET "/eval/foundry" que retorna {"runs": list_eval_runs(limit)}. (app/api/evals.py)

- Há um endpoint GET "/healthz" que retorna {"status": "ok"}. (app/api/health.py)

- Há um endpoint GET "/tickets" que retorna {"tickets": list_tickets(limit)} e declara que se refere a "Real tickets opened by the HITL approval flow (create_ticket tool)" e que são persistidos em data/tickets.jsonl (comentário/docstring). (app/api/tickets.py)

- O script executa uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) quando executado como __main__. (app/main.py)