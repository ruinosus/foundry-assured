// Locale por requisição — sem roteamento por prefixo.
//
// A spec decidiu não usar `/pt-BR/...`: mudaria todas as URLs e o produto não tem SEO (é
// autenticado). A preferência vive num cookie, do mesmo jeito que o tema vive no
// localStorage — e o padrão, sem escolha explícita, é o `Accept-Language` do navegador.
//
// O MESMO valor é enviado ao backend no header `Accept-Language`, que é o que faz o agente
// responder na língua certa. Interface e agente falando línguas diferentes seria pior que o
// inglês inconsistente que isto veio corrigir.

//
// GOTCHA DO DEV SERVER: os catálogos entram por `import()` dinâmico, e o Next cacheia o módulo em
// desenvolvimento. Editar `messages/*.json` com o servidor no ar NÃO recarrega — a tela quebra com
// `MISSING_MESSAGE: Could not resolve <chave>` para uma chave que está no arquivo. Aconteceu duas
// vezes nesta base antes de alguém escrever isto aqui. Se a chave existe no JSON e o erro insiste,
// reinicie `npm run dev` em vez de procurar defeito na chave.
import { getRequestConfig } from "next-intl/server";
import { cookies, headers } from "next/headers";

import { DEFAULT_LOCALE, LOCALES, LOCALE_COOKIE, type Locale } from "@/lib/locale";

export { DEFAULT_LOCALE, LOCALES, LOCALE_COOKIE, type Locale };

/** A escolha explícita vence; sem ela, o navegador decide; sem isso, o padrão. */
export function pickLocale(cookieValue: string | undefined, acceptLanguage: string | null): Locale {
  if (cookieValue && (LOCALES as readonly string[]).includes(cookieValue)) {
    return cookieValue as Locale;
  }
  // Primeira preferência do navegador que temos tradução para. Comparação por prefixo: "pt",
  // "pt-PT" e "pt-BR" recebem português; "en-GB" recebe inglês.
  for (const part of (acceptLanguage ?? "").split(",")) {
    const tag = part.split(";")[0].trim().toLowerCase();
    if (!tag) continue;
    const hit = LOCALES.find((l) => l.toLowerCase() === tag || tag.startsWith(l.split("-")[0].toLowerCase()));
    if (hit) return hit;
  }
  return DEFAULT_LOCALE;
}

export default getRequestConfig(async () => {
  const [cookieStore, headerList] = await Promise.all([cookies(), headers()]);
  const locale = pickLocale(
    cookieStore.get(LOCALE_COOKIE)?.value,
    headerList.get("accept-language"),
  );
  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  };
});
