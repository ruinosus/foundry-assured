# ADR-029 — Uma API key pode dar acesso ao modelo; ela não pode dar o trim de ACL

- **Status:** Proposed
- **Date:** 2026-08-26
- **Context:** [ADR-003](./ADR-003-multitenant-identity-obo.md) (identidade e OBO),
  [ADR-005](./ADR-005-never-store-secrets.md), [ADR-026](./ADR-026-retrieval-stays-ours-mcptool-ignores-headers.md)
  (por que a recuperação com ACL é nossa), `CLAUDE.md` regra 2 e regra 6,
  [`docs/DEV-LOCAL.md`](../DEV-LOCAL.md)

## Contexto

O produto vai ser absorvido por uma organização onde nem toda equipe tem RBAC no Azure, mas muitas
têm **chave de API** do Azure OpenAI. A pergunta que motivou esta ADR foi prática: *dá para rodar
com a key que eu já tenho?*

Hoje não dá, e não por acidente. Medido: `grep` por `AzureKeyCredential`, `api_key=` e
`AZURE_OPENAI_API_KEY` em `apps/backend/app/` devolve **zero ocorrências**. Todo acesso é
`DefaultAzureCredential` ou On-Behalf-Of, que é a regra 2 do `CLAUDE.md`.

## O fato que decide, e ele não é sobre conveniência

A recuperação usa **duas credenciais diferentes**, e elas fazem coisas diferentes
(`app/modules/knowledge/internal/retrieval.py`):

```python
primary   = (await app_cred.get_token(_SEARCH_SCOPE)).token   # :69  identidade da APLICAÇÃO
user_token = await _user_search_token(user)                   # :82  OBO do CHAMADOR
...
headers["x-ms-query-source-authorization"] = user_token        # :212
```

- `primary` é a managed identity da aplicação — o usuário final **não tem** RBAC no Search, então
  quem chama o serviço é o app.
- `user_token` é o **que produz o trim de ACL por documento**. Ele viaja num header e o corte
  acontece **dentro do Azure AI Search**, contra os grupos carimbados em cada documento.

Uma API key é uma identidade **de aplicação**. Ela pode substituir `primary` — o Azure AI Search
aceita chave de consulta. Ela **não tem como** substituir `user_token`, porque não existe usuário
dentro dela.

Isto não é limitação de implementação. É o que uma chave é.

## Decisão

**Um caminho por API key é aceitável para acesso ao MODELO, e proibido como caminho de
RECUPERAÇÃO com ACL.**

Concretamente:

1. **Modelo:** um seam na fábrica de chat client pode aceitar chave, para quem não tem RBAC rodar
   o produto e ver o fluxo. Isso não enfraquece garantia nenhuma — o modelo não decide acesso.
2. **Recuperação:** o caminho com `x-ms-query-source-authorization` continua exigindo OBO. Um modo
   por chave, se existir, **serve apenas domínios sem ACL** e precisa recusar, alto e no boot,
   qualquer domínio cujo `document_access` seja `"acl"`.
3. **A distinção é verificada, não confiada.** Um gate precisa provar que o modo por chave não
   alcança domínio com ACL — a regra 6 diz que acesso é dado, e um modo novo que a contorne é
   pior que a ausência do modo.

## Por quê

**O que se ganha.** Quem tem chave e não tem RBAC passa a rodar o produto — que é literalmente o
perfil de usuário que este projeto existe para atender ("preencher lacunas e trazer outros perfis
para consumir recursos Microsoft"). Para dev local, demonstração e avaliação, é a diferença entre
usar e não usar.

**O que não se pode perder.** O trim por documento é a garantia central. Um modo por chave que
servisse domínio com ACL entregaria, à identidade da aplicação, tudo o que o índice tem — sem
erro, sem log, e com a interface dizendo que respondeu com fontes. É o modo de falha que a
ADR-026 já documenta noutro contexto: funciona bem em tudo, menos em aplicar ACL.

**Por que `Proposed` e não `Accepted`.** A parte (1) é decisão de engenharia e cabe aqui. A parte
(2) toca o modelo de segurança do produto num ambiente corporativo, e quem decide isso é o dono
com a área de segurança — não uma ADR escrita por um agente.

## Consequências

- O `azure_openai_endpoint` que já existe em `settings.py` ganharia um par opcional de chave, lido
  de variável de ambiente e **nunca** commitado (ADR-005 continua valendo integralmente).
- `DEV-LOCAL.md` deixa de ter a linha "não tem caminho local hoje" para o modelo.
- A superfície de segredo cresce. Hoje o backend guarda um segredo (`ENTRA_API_CLIENT_SECRET`);
  passaria a guardar dois, e o segundo é de terceiro para quem for absorver o projeto.

## Alternativas consideradas

**Chave para tudo, inclusive recuperação.** Rejeitada pelo argumento acima: entrega o índice
inteiro sob a identidade da aplicação.

**Nada de chave, RBAC sempre.** É o estado atual. Correto do ponto de vista de segurança e
excludente do ponto de vista de adoção — obriga quem quer avaliar o produto a ter RBAC antes de
saber se o produto serve.

**Chave só no dev local, bloqueada por ambiente.** Meio-termo tentador e frágil: "só em dev" é uma
promessa que uma variável de ambiente não cumpre. Se o modo existir, precisa ser seguro por
construção — recusando domínio com ACL — e não seguro por convenção.

## Gatilho de reavaliação

Se o Azure AI Search passar a aceitar delegação de identidade por outro mecanismo que não OBO
(hoje o header é o caminho), a parte (2) muda de forma e esta ADR precisa ser reescrita, não
emendada.
