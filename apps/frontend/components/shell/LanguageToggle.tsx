"use client";

// Seletor de idioma — português · English · automático.
//
// Mesma mecânica de três estados do seletor de tema, e pelo mesmo motivo: "automático" segue o
// navegador e muda sozinho se a pessoa trocar o idioma do sistema, o que não é o mesmo que
// escolher um.
//
// A escolha vai para um COOKIE, não localStorage. O locale é resolvido no servidor (i18n/
// request.ts), e o servidor não enxerga localStorage — com ele, a primeira renderização viria
// no idioma errado e corrigiria depois de hidratar.
//
// O mesmo valor é enviado ao backend como `Accept-Language` (lib/auth/api.ts), que é o que faz
// o AGENTE responder na língua certa. Interface e agente em línguas diferentes seria pior que
// a inconsistência que isto veio corrigir.

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { LOCALE_COOKIE, type Locale } from "@/lib/locale";

const OPTIONS: { value: Locale | "system"; short: string }[] = [
  { value: "pt-BR", short: "PT" },
  { value: "en", short: "EN" },
  { value: "system", short: "◐" },
];

export function LanguageToggle() {
  const t = useTranslations("language");
  const active = useLocale();
  const router = useRouter();
  const [pending, setPending] = useState(false);

  const choose = (value: Locale | "system") => {
    // `system` apaga o cookie: a ausência é o que devolve a decisão ao Accept-Language.
    document.cookie =
      value === "system"
        ? `${LOCALE_COOKIE}=; path=/; max-age=0; samesite=lax`
        : `${LOCALE_COOKIE}=${value}; path=/; max-age=31536000; samesite=lax`;
    setPending(true);
    // O locale é decidido no servidor, então trocá-lo exige buscar a árvore de novo — não
    // basta um setState. `refresh` preserva o estado do cliente (o chat aberto, por exemplo).
    router.refresh();
    setTimeout(() => setPending(false), 400);
  };

  return (
    <div className="theme-toggle" role="group" aria-label={t("label")}>
      {OPTIONS.map((opt) => {
        const on = opt.value === "system" ? false : opt.value === active;
        return (
          <button
            key={opt.value}
            type="button"
            className={`theme-opt${on ? " on" : ""}`}
            aria-pressed={on}
            disabled={pending}
            title={opt.value === "system" ? t("system") : t(opt.value)}
            onClick={() => choose(opt.value)}
          >
            <span aria-hidden>{opt.short}</span>
            <span className="sr-only">
              {opt.value === "system" ? t("system") : t(opt.value)}
            </span>
          </button>
        );
      })}
    </div>
  );
}
