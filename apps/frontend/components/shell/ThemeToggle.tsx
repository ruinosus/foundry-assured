"use client";

// Seletor de tema — claro · escuro · sistema.
//
// Três estados, não dois. "Sistema" não é o mesmo que "claro": ele acompanha o SO e muda
// sozinho ao anoitecer, que é exatamente o caso deste produto (o mesmo console é operado num
// incidente de madrugada e apresentado numa sala clara à tarde — ver PRODUCT.md).
//
// A aplicação em si mora em lib/theme.ts, porque precisa estampar DOIS sistemas: o nosso
// (`data-theme`) e o do CopilotKit (a classe `.dark`).

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { applyTheme, readTheme, THEME_KEY, type Theme } from "@/lib/theme";

// Só o que NÃO é texto fica aqui; o rótulo vem do dicionário.
const OPTIONS: { value: Theme; icon: string }[] = [
  { value: "light", icon: "☀" },
  { value: "dark", icon: "☾" },
  { value: "system", icon: "◐" },
];

export function ThemeToggle() {
  const t = useTranslations("theme");
  // Começa em `system` no servidor e no primeiro render; o valor salvo entra no efeito. Ler
  // localStorage durante o render quebraria a hidratação. O script inline em layout.tsx já
  // pintou a tela certa antes disto, então não há piscada — este estado só sincroniza o
  // controle com o que já está aplicado.
  const [theme, setTheme] = useState<Theme>("system");

  useEffect(() => setTheme(readTheme()), []);

  // Em "sistema", o tema efetivo muda sem ninguém clicar em nada. A classe `.dark` é DOM, não
  // CSS, então nenhum seletor a coloca sozinho: sem este listener o chat continuaria claro
  // depois que o SO virasse escuro às 18h.
  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = () => applyTheme("system");
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, [theme]);

  const choose = (next: Theme) => {
    setTheme(next);
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      /* modo privado / storage bloqueado: o tema vale para esta sessão e pronto */
    }
    applyTheme(next);
  };

  return (
    <div className="theme-toggle" role="group" aria-label={t("label")}>
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          className={`theme-opt${theme === opt.value ? " on" : ""}`}
          aria-pressed={theme === opt.value}
          title={t(opt.value)}
          onClick={() => choose(opt.value)}
        >
          <span aria-hidden>{opt.icon}</span>
          <span className="sr-only">{t(opt.value)}</span>
        </button>
      ))}
    </div>
  );
}
