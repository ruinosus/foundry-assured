---
name: sdk-verify
description: Use ANTES de escrever ou corrigir qualquer chamada a azure-ai-projects, agent-framework, agent-framework-ag-ui, agent-framework-declarative, azure-identity ou a um MCP server da Microsoft — e sempre que a tarefa parecer pedir código novo que talvez o Azure/Foundry já resolva. Aplica a MÁXIMA MAIOR e a regra 1 do CLAUDE.md.
---

# Verificar antes de escrever cola

Duas regras deste repo se encontram aqui:

- **MÁXIMA MAIOR** — se existe capacidade equivalente no Azure / Foundry / AI Search / Agent
  Framework / MCP oficial, ela ganha do nosso código **por definição**. O teto do que se escreve
  aqui é a cola.
- **Regra 1** — nunca invente assinatura de SDK. A superfície muda rápido, em especial o
  namespace `.beta` de `azure-ai-projects`.

O ônus da prova é **invertido**: escrever código nosso exige demonstrar que se procurou e não
existe. "Não achei" só vale depois de procurar nos quatro lugares.

## Os quatro lugares, nesta ordem

1. **O código do pacote instalado** — é a fonte de verdade sobre a versão em uso, e é local:
   ```bash
   cd apps/backend && uv run python -c "import azure.ai.projects as m; print(m.__file__, m.__version__)"
   ```
   Depois leia a classe/método de verdade. Um `dir()` no objeto responde mais rápido que
   qualquer busca.
2. `learn.microsoft.com/azure/foundry`
3. `github.com/microsoft-foundry/foundry-samples` (pasta `python/hosted-agents/agent-framework`)
   e `github.com/microsoft/agent-framework`
4. Release notes / CHANGELOG do pacote.

## O que responder depois de procurar

Uma destas três, explicitamente — nunca silêncio:

- **"Existe X, é isto"** → escreva a cola usando X e diga qual peça oficial cada parte usa.
- **"Existe X, cobre ~80%, faltam estes 20% e custam N linhas"** → é decisão do desenvolvedor,
  não sua. Apresente e pare.
- **"Procurei nos quatro e não existe"** → diga onde procurou. Só então escreva código próprio.

Se não conseguir confirmar uma assinatura, deixe `# TODO: verificar assinatura` explícito no
lugar. Chutar é pior que admitir.

## A fronteira que a máxima NÃO proíbe

> "Não é recriar nada da Microsoft, é preencher lacunas e trazer outros perfis de usuário para
> consumir recursos Microsoft."

O portal do Foundry atende quem tem conta e RBAC no Azure. Este produto atende quem não tem.
Construir essa camada de acesso é **preencher lacuna**; reescrever o que o portal faz por baixo
dela é **violar a máxima**.

O teste, na dúvida: *estou expondo uma capacidade a um perfil que não a alcança, ou
reimplementando a capacidade?* O primeiro é o produto. O segundo é proibido.

**A única exceção calibrada:** a camada de assurance é nossa — `eval/`, `tests/architecture/`, a
resolubilidade de citações, o contrato de decisão HITL. Foi pesquisada, não há equivalente de
primeira parte, e por isso sobrevive à máxima. Tudo que for produto segue sem exceção.
