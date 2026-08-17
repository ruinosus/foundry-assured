---
title: 'Design: produto bilíngue — interface, agente e conteúdo'
description: Tornar o produto utilizável em português e inglês de verdade, não só na interface. O levantamento mostra que o Foundry NÃO tem campo de idioma para agentes de texto (é instrução de prompt), que o gerador da wiki aceita locale, e que o corpus é o único conteúdo sem caminho de tradução. Três camadas, custos muito diferentes.
type: design
audience: contributor
status: draft
updated: 2026-08-17
---

# Produto bilíngue

## Por que a interface sozinha não resolve

Traduzir rótulos é a parte fácil e, feita isolada, **piora** o que já existe. Hoje o produto
mistura idiomas assim:

| Camada | Estado |
|---|---|
| Navegação | inglês (`Overview`, `Tickets`, `Evaluations`) |
| Telas novas | português |
| Resposta do agente | português, por instrução explícita no prompt |
| Corpus do helpdesk | **inglês** ("Runbook: VPN drops on new laptops") |
| Wiki / selfwiki | **inglês** |
| Citações | mostram nome de arquivo e trecho do documento original |

Com a interface em inglês e o resto como está, o usuário veria rótulos em inglês, resposta em
português e citação em inglês — **três idiomas na mesma tela**, pior que a inconsistência
atual. Por isso esta spec trata as três camadas, e não só a primeira.

## O levantamento

Feito antes do desenho, pela MÁXIMA MAIOR.

### O Foundry não tem campo de idioma para agentes de texto

Procurado e não encontrado. O que a plataforma oferece em torno de idioma é:

- **Azure Translator** (API 2026-06-06 GA) — traduzir texto
- **Language Detection** (Azure Language) — descobrir o idioma de uma entrada
- **Voice Live** — multilíngue para voz, com até 10 idiomas declarados

Nenhum é "responda neste idioma". Para agente de texto, **idioma de resposta é instrução de
prompt** — não há API para delegar. Isso é o raro caso em que a lacuna é da plataforma, e a
cola é legítima.

**Mas `Language Detection` é aproveitável**: detectar o idioma da pergunta é melhor que confiar
na preferência salva, porque a pessoa pode escrever em inglês num navegador em português.

### O gerador da wiki aceita locale

`openwiki --language <locale>` — "Generate wiki documentation in the requested language". O
conteúdo do selfwiki pode ser gerado por idioma, sem tradutor no meio.

### O idioma está duplicado dentro dos prompts

`"Responda SEMPRE em português (pt-BR)"` aparece cravado em `selfwiki.yaml` e `techdocs.yaml`.
É regra transversal escrita em cada arquivo — e o repositório já tem o lugar certo para isso:
`agents/helpdesk/guardrails/`, hoje com `grounded-citation.md` e `no-write-claims.md`.

### A composição é estática

`definitions.compose()` monta persona → instructions → additionalInstructions → guardrails **no
import**. Idioma por usuário é dinâmico, então não pode sair dali — entra no momento da
requisição, junto com o que já é per-request (identidade, OBO, ACL).

## Desenho

### Camada 1 — Interface

`next-intl`, como no `aap-kb` (precedente do próprio time, 1.095 chaves lá; aqui são ~111
strings). Seletor de idioma ao lado do de tema, com a mesma mecânica de três estados:
**português · inglês · sistema** (`Accept-Language`).

Sem roteamento por locale (`/pt-BR/...`): mudaria todas as URLs e o produto não tem SEO — é
autenticado. A preferência vive no mesmo lugar do tema.

### Camada 2 — Agente

Duas mudanças, e a primeira vale por si:

1. **O idioma vira guardrail** (`guardrails/response-language.md`), removendo a duplicação. É o
   que o repositório já faz com citação obrigatória e com proibição de alegar escrita.
2. **O idioma efetivo entra por requisição.** A preferência do usuário viaja com a chamada e é
   anexada às instruções na hora da síntese — onde já vivem identidade e ACL. A composição
   estática continua estática; o que muda é o sufixo dinâmico.

Opcional, quando houver demanda: `Language Detection` sobre a pergunta, para responder no
idioma em que a pessoa **escreveu**, ignorando a preferência. Mais caro (uma chamada a mais) e
melhor.

### Camada 3 — Conteúdo

Aqui as três fontes têm respostas diferentes, e uma não tem:

| Conteúdo | Caminho |
|---|---|
| **Wiki (selfwiki)** | `openwiki --language` gera por idioma; um bundle por locale |
| **TechDocs** | bundles externos — idioma é de quem produz, fora do nosso alcance |
| **Corpus (helpdesk)** | **sem caminho** — ver abaixo |

O corpus é o problema honesto. Ele está congelado de propósito, porque três gates de eval casam
pergunta ↔ runbook por título exato (`golden.jsonl`). Traduzi-lo exigiria traduzir também o
conjunto dourado e reancorar os gates — e aí o eval passaria a medir a tradução, não o produto.

**Recomendação:** deixar o corpus em inglês e assumir. Ele é cenário fictício de demonstração;
um usuário que pergunta em português e recebe resposta em português citando um runbook em
inglês está vendo exatamente o que aconteceria numa empresa real com documentação em inglês.
Fingir o contrário custaria os gates.

## Ordem

1. **Guardrail de idioma** — tira a duplicação; vale mesmo que o resto não venha
2. **Idioma por requisição** — o agente passa a responder na preferência do usuário
3. **`next-intl` + seletor** — a interface
4. **Wiki por locale** — regenerar com `--language`
5. *(se houver demanda)* **Language Detection** — responder no idioma da pergunta

Os passos 1 e 2 entregam o ganho maior: **é o agente falando a língua da pessoa** que torna o
produto bilíngue. A interface traduzida sem isso é maquiagem.

## Riscos

**Prompt cresce.** Cada instrução dinâmica anexada consome contexto e pode competir com as
regras existentes. O guardrail precisa ser curto e imperativo.

**Gates de prompt.** `eval/prompt_contract_test` valida as invariantes dos prompts compostos;
mudar a composição exige atualizar os casos no mesmo PR, que é a regra do CLAUDE.md.

**Citações em outro idioma.** A resposta em português citando trecho em inglês é o
comportamento correto (a citação é literal, e alterá-la quebraria a procedência) — mas a
interface deve deixar claro que o trecho é do documento original, não uma tradução.

**Duas versões da wiki.** Um bundle por locale dobra a prateleira, e o gate de acervo exige uma
versão por componente. Precisaria de componente por idioma (`foundry-assured-pt`,
`foundry-assured-en`) ou de uma regra nova — decisão a tomar antes de gerar a segunda.

## Referências

- Pesquisa 2026-08-17: Azure Translator, Azure Language (Detection), Voice Live — nenhum é
  "responda neste idioma" para agente de texto
- `openwiki --language <locale>`
- `aap-kb`: `next-intl@^4.13.0`, `messages/pt-BR.json`
- `app/modules/agentdefs/internal/definitions.py` — a composição estática
- MÁXIMA MAIOR em `CLAUDE.md`
