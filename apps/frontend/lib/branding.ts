// Product identity — the single place to rebrand the showcase for your own domain.
//
// Sobrou o que é NOME PRÓPRIO: nome de produto e nome do assistente não se traduzem, do mesmo
// jeito que ninguém traduz "Azure" ou "Foundry". O que era FRASE (a tagline sob a marca e a
// descrição de uma linha) virou chave de dicionário — `branding.tagline` e
// `branding.description` em `messages/<locale>.json` — porque frase tem idioma, e aqui ela
// nascia em inglês e ficava em inglês mesmo para quem escolheu português.
//
// A cópia da visão geral (app/page.tsx) e as instruções dos agentes (backend, agents/assured/)
// são *conteúdo* de domínio, reescritos à parte — ver docs/CUSTOMIZE.md.
export const branding = {
  /** Product name — browser title, sidebar brand, login screen. */
  product: "Foundry Assured",
  /** The assistant's display name — nav item + sign-in prompt. */
  assistant: "Concierge",
};
