"use client";

// O access token do usuário para a API, com renovação silenciosa.
//
// Extraído do `DockHost` quando o provider do CopilotKit subiu para o nível do shell (ver
// `DockProvider`): o token precisa ser adquirido ACIMA do provider, porque agora é ele que carrega
// o cabeçalho `Authorization`. Deixá-lo no componente de baixo faria o provider subir sem token e
// o chat responder 401 até alguém trocar de página.
//
// A renovação bem antes da expiração de ~1h é o que impede o sintoma clássico: o chat "para de
// responder" no meio da sessão porque o token venceu em silêncio.

import { useMsal } from "@azure/msal-react";
import { useEffect, useState } from "react";
import { apiScopes, authConfigured } from "@/lib/auth/msal";

export function useApiToken(): string | null {
  const { instance, accounts } = useMsal();
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    if (!authConfigured || !accounts[0]) return;
    let alive = true;
    const acquire = () =>
      instance
        .acquireTokenSilent({ scopes: apiScopes, account: accounts[0] })
        .then((r) => alive && setToken(r.accessToken))
        .catch(() => {});
    void acquire();
    const id = setInterval(acquire, 4 * 60 * 1000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [instance, accounts]);

  return token;
}
