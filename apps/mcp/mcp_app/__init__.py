"""O servidor MCP do Foundry Assured, como unidade de deploy própria (ADR-027).

POR QUE O PACOTE NÃO SE CHAMA `app`. O backend se instala como o pacote `app`
(`apps/backend/pyproject.toml`, `packages = ["app"]`) e este app o importa. Um diretório
`app/` aqui dentro venceria o `app` instalado em `sys.path` na primeira posição (o diretório
de trabalho) e `import app.modules.knowledge.public` passaria a procurar `modules/` DENTRO
deste pacote — `ModuleNotFoundError` no import, com a mensagem apontando para o lugar errado.
`mcp_app` também evita o outro nome óbvio, `mcp`, que é o SDK do protocolo.
"""
