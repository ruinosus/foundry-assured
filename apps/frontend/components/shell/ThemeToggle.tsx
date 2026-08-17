"use client";

// Seletor de tema — claro · escuro · sistema.
//
// Três estados, não dois. "Sistema" não é o mesmo que "claro": ele acompanha o SO e muda
// sozinho ao anoitecer, que é exatamente o caso de uso deste produto (o mesmo console é
// operado num incidente de madrugada e apresentado numa sala clara à tarde — ver PRODUCT.md).
//
// A escolha explícita estampa `data-theme` na raiz; "sistema" REMOVE o atributo, deixando
// `prefers-color-scheme` decidir. Os tokens em tokens.css cobrem os três casos: `:root` define
// o claro completo, a media query redefine sob `:not([data-theme="light"])`, e
// `[data-theme="dark"]` redefine de novo para o botão vencer nos dois sentidos.

import { useEffect, useState } from "react";

type Theme = "light" | "dark" | "system";
const KEY = "fa-theme";

/** Aplica na raiz. `system` remove o atributo em vez de escrever um valor. */
function apply(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

const OPTIONS: { value: Theme; label: string; icon: string }[] = [
  { value: "light", label: "Claro", icon: "☀" },
  { value: "dark", label: "Escuro", icon: "☾" },
  { value: "system", label: "Sistema", icon: "◐" },
];

export function ThemeToggle() {
  // Começa em `system` no servidor e no primeiro render do cliente; o valor salvo entra no
  // efeito. Ler localStorage durante o render quebraria a hidratação (servidor e cliente
  // chegariam a marcações diferentes). O script inline em layout.tsx já pintou a tela certa
  // antes disto rodar, então não há piscada — este estado só sincroniza o controle.
  const [theme, setTheme] = useState<Theme>("system");

  useEffect(() => {
    const saved = localStorage.getItem(KEY) as Theme | null;
    if (saved === "light" || saved === "dark" || saved === "system") setTheme(saved);
  }, []);

  const choose = (next: Theme) => {
    setTheme(next);
    localStorage.setItem(KEY, next);
    apply(next);
  };

  return (
    <div className="theme-toggle" role="group" aria-label="Tema">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          className={`theme-opt${theme === opt.value ? " on" : ""}`}
          aria-pressed={theme === opt.value}
          title={opt.label}
          onClick={() => choose(opt.value)}
        >
          <span aria-hidden>{opt.icon}</span>
          <span className="sr-only">{opt.label}</span>
        </button>
      ))}
    </div>
  );
}
