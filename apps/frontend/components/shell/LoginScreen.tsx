"use client";

// Muro de entrada. Renderizado pelo <AuthGate> sempre que o Entra está configurado e o usuário
// não está autenticado — substitui o app INTEIRO (sem shell, sem nav, sem rota), então nada é
// alcançável sem entrar. Depois do sign-out o usuário volta para cá.
//
// Primeira tela do produto, e por isso a primeira a sair do estilo inline: antes tinha
// gradiente cravado, card branco imune ao tema, sombra de 60px de blur e `#2563eb`. Agora
// consome os tokens, respeita claro/escuro e traz o seletor de tema — quem abre isto às 23h
// escolhe o tema antes de entrar, não depois.

import { useMsal } from "@azure/msal-react";
import { useTranslations } from "next-intl";
import { apiScopes } from "@/lib/auth/msal";
import { branding } from "@/lib/branding";
import { ThemeToggle } from "@/components/shell/ThemeToggle";

export function LoginScreen() {
  const { instance } = useMsal();
  const t = useTranslations();

  return (
    <div className="login">
      <main className="login-card">
        <span className="login-mark" aria-hidden>
          ⚡
        </span>
        <h1 className="login-title">{branding.product}</h1>
        <p className="login-sub">{t("branding.description")}</p>

        <button
          type="button"
          className="btn btn-primary btn-block"
          onClick={() => instance.loginRedirect({ scopes: apiScopes })}
        >
          {t("common.signIn")}
        </button>

        {/* Diz o que exige a entrada, não que ela é exigida — o usuário já percebeu isso ao
            ver esta tela. A informação útil é POR QUE: as respostas carregam procedência, e
            procedência precisa de identidade. */}
        <p className="login-note">{t("login.note")}</p>
      </main>

      <footer className="login-foot">
        <ThemeToggle />
      </footer>
    </div>
  );
}
