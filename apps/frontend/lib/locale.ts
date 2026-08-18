// Constantes de locale compartilhadas entre servidor e cliente.
//
// Vivem aqui, e não em i18n/request.ts, porque aquele arquivo importa `next/headers` — que só
// existe no servidor. Um componente de cliente importando de lá quebraria o build.

export const LOCALES = ["pt-BR", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "pt-BR";
export const LOCALE_COOKIE = "fa-locale";
