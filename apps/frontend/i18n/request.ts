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
// POR QUE O CATÁLOGO É LIDO DO DISCO EM DESENVOLVIMENTO. Com `import()` dinâmico, o Next cacheia
// o módulo: editar `messages/*.json` com o servidor no ar não recarrega, e a tela quebra com
// `MISSING_MESSAGE: Could not resolve <chave>` apontando para uma chave que ESTÁ no arquivo.
// Isso aconteceu três vezes nesta base. Documentar não resolveu — quem tropeça na quarta vez vai
// depurar a chave, não o cache, porque o erro acusa a chave.
//
// Em produção o `import()` continua, e deve continuar: ele embute o catálogo no bundle, que é
// mais rápido e não depende do sistema de arquivos (o container pode nem ter os JSON soltos).
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

/** O catálogo do idioma. Em dev vem do disco (sem cache); em produção, do bundle. */
async function loadMessages(locale: Locale) {
  if (process.env.NODE_ENV === "development") {
    // `readFile` a cada requisição é irrelevante em desenvolvimento e elimina a classe inteira
    // de "editei o JSON e a tela não viu".
    const { readFile } = await import("node:fs/promises");
    const { join } = await import("node:path");
    const raw = await readFile(join(process.cwd(), "messages", `${locale}.json`), "utf8");
    return JSON.parse(raw);
  }
  return (await import(`../messages/${locale}.json`)).default;
}

export default getRequestConfig(async () => {
  const [cookieStore, headerList] = await Promise.all([cookies(), headers()]);
  const locale = pickLocale(
    cookieStore.get(LOCALE_COOKIE)?.value,
    headerList.get("accept-language"),
  );
  return { locale, messages: await loadMessages(locale) };
});
