// Aplicação de tema — um lugar só, porque são DOIS sistemas que precisam concordar.
//
// O nosso lê `data-theme` na raiz (com "sistema" = ausência do atributo, deixando
// `prefers-color-scheme` decidir). O CopilotKit lê a **classe `.dark`** — não data-theme, não
// media query. Enquanto só estampávamos o atributo, o chat ficava permanentemente claro dentro
// de uma interface escura, que foi exatamente o bug reportado.
//
// Como a classe é DOM e não CSS, o modo "sistema" precisa de JavaScript ouvindo a media query:
// não há como um seletor sozinho pôr uma classe quando o SO muda de tema.

export type Theme = "light" | "dark" | "system";
export const THEME_KEY = "fa-theme";

/** O tema que efetivamente vale agora — resolve "system" contra a preferência do SO. */
export function resolved(theme: Theme): "light" | "dark" {
  if (theme !== "system") return theme;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Estampa o tema nos dois sistemas: `data-theme` (nosso) e `.dark` (CopilotKit). */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
  root.classList.toggle("dark", resolved(theme) === "dark");
}

export function readTheme(): Theme {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === "light" || v === "dark" || v === "system" ? v : "system";
  } catch {
    return "system";
  }
}
