// A conversa vive na URL: `/d/<domínio>?c=<threadId>`.
//
// O nome do parâmetro é uma constante porque dois lugares precisam concordar com ele —
// AssuranceConsole (que lê e escreve `?c=`) e ShareButton (que monta o link a partir do mesmo
// nome) — e "c" batendo por coincidência em duas strings literais é o tipo de acoplamento
// silencioso que este repo já viu quebrar antes (ver idDaMensagem em lib/thread-history.ts).

export const PARAMETRO_CONVERSA = "c";

/** O link compartilhável de uma conversa — mesma origem, rota do domínio, id da conversa. */
export function sharedConversationUrl(domainId: string, threadId: string): string {
  const url = new URL(`/d/${encodeURIComponent(domainId)}`, window.location.origin);
  url.searchParams.set(PARAMETRO_CONVERSA, threadId);
  return url.toString();
}
