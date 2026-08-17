# Foundry Assured — contexto de produto

## O que é

Um **console de garantias** sobre agentes de IA, para quem **não tem acesso ao portal do
Foundry**. O usuário conversa com um agente que responde fundamentado em documentos, e a
interface mostra **por que aquela resposta é confiável**: de onde veio, quem podia ler aquilo,
o que exigiu aprovação humana, e o que os gates mediram.

Não é um chat com um painel ao lado. O chat é o meio; a **procedência** é o produto.

## Para quem, e por que existimos

> "Não é recriar nada da Microsoft, é preencher lacunas e trazer outros perfis de usuário para
> consumir recursos Microsoft."

O portal do Foundry serve quem tem conta e RBAC no Azure. Este produto serve o **usuário
final** — que precisa criar, usar e manter agentes, bases de conhecimento e skills **sem nunca
abrir o portal**, e sem saber o que é um resource group.

Isso é o que decide a arquitetura de informação: agentes, bases e skills são **entidades que o
usuário possui e mantém**, não configuração cravada em código. A navegação é "o que é meu",
não "as features que o time embutiu".

### Decisões ainda em aberto (afetam a navegação)

Registradas porque a interface muda conforme a resposta, e adivinhar sairia caro:

- **Criar agente** vai até onde? Criar de verdade no Foundry (nome, modelo, instruções,
  ferramentas, base vinculada) ou, na primeira versão, apenas listar e usar os existentes?
- Os quatro domínios atuais **viram agentes gerenciáveis** ou permanecem fixos, como exemplos
  ao lado dos que o usuário criar?

Enquanto não decidido, o design assume **listagem + detalhe + uso** como o núcleo, e trata
"criar" como um fluxo que entra depois sem reorganizar o resto.

## Register

`product` — design serve o produto. Console operado por engenheiros dentro de uma tarefa, não
uma página de marketing.

## Platform

`web` — Next.js 16 (App Router), React 19.

## Quem usa, onde

Duas situações reais, e elas puxam para lados diferentes:

1. **Engenheiro em tarefa** — quer uma resposta com fonte, ou precisa aprovar/corrigir uma ação
   (abrir chamado, escalar incidente). Está numa mesa, possivelmente durante um incidente,
   frequentemente à noite. Quer resolver e sair.
2. **Demonstração** — o mesmo app projetado numa sala clara, para alguém avaliando se as
   garantias são reais. Aqui a interface precisa **explicar-se** enquanto é usada.

Por isso os dois temas são requisito, não preferência: a situação 1 pede escuro, a 2 pede claro.
Hoje não existe nenhum dos dois — só um tema claro implícito.

## As telas

| Superfície | Função |
|---|---|
| `/d/[domain]` | o console: chat + passos do workflow + card de aprovação + painel de evidências |
| `/tickets` | chamados abertos por aprovação humana |
| `/evals` | resultados dos gates (groundedness, relevance, coherence, políticas) |
| `/admin/users` | papéis do Entra (Admin / Author / Approver / Reader) |
| `/admin/connections` | conexões do tenant (só no modo `shared`) |
| `/` | visão geral / entrada |

## Os quatro domínios de hoje

Ponto de partida, não destino: hoje são fixos no registry; a direção é que convivam com
agentes criados pelo usuário. Cada um demonstra uma capacidade diferente, e **a interface hoje
não diz qual** — a lacuna central de informação:

| Domínio | Demonstra |
|---|---|
| Helpdesk concierge | workflow multi-agente + memória + aprovação para abrir chamado |
| Project wiki | documentação gerada por IA, com gate de fidelidade e ACL por documento |
| On-call triage | segundo runtime (LangGraph) e aprovação com **edit** — corrigir antes de executar |
| Platform ops | ferramentas Microsoft via MCP, com aprovação em toda escrita |

## O vocabulário do domínio

As palavras que a interface precisa carregar bem, porque são o produto:

- **citação / fonte** — toda resposta aponta para o documento que a sustenta
- **fidelidade** — quantas citações resolvem para arquivo real
- **aprovação** — approve · **edit** · reject, com papel exigido
- **acesso** — quem podia ler aquele documento (grupo, por documento)
- **gate** — passou, avisou ou barrou

## Estados que importam mais que o normal

- **Vazio com causa**: "nenhum documento autorizado" ≠ "nenhum documento existe". A diferença é
  de segurança e precisa aparecer.
- **Aguardando humano**: o card de aprovação é o momento mais importante da interface. Bloqueia
  uma ação real.
- **Degradado**: domínio sem base configurada, modo que não oferece Connections, papel sem
  permissão de aprovar. Hoje isso aparece como 404, 500 ou silêncio.

## Restrições

- Sem Tailwind, sem biblioteca de componentes. CSS próprio em `styles/globals.css`.
- `@copilotkit/react-ui` traz CSS próprio para o chat — o tema precisa conviver com ele.
- Autenticação Entra (MSAL); papéis vêm do claim `roles`.
