"use client";

// Conversa com um agente do Foundry — o que faltava para o ciclo fechar.
//
// Até aqui o produto tinha duas listas de "agente" que não se falavam: os ASSISTENTES (domínios de
// código, conversáveis) e os AGENTES do Foundry (recursos, criáveis pelo wizard e inúteis depois
// de criados). Quem criasse um agente pela tela o via na lista e não tinha o que fazer com ele.
//
// Esta tela usa o MESMO CopilotChat dos domínios. A diferença está no runtime: o agente não vem do
// registry de código, e sim registrado sob demanda pelo id que o cliente pede
// (app/api/copilotkit/…/route.ts), que por sua vez fala com o backend em /foundry-agent/{nome}.

import { CopilotChat, CopilotKitProvider } from "@copilotkit/react-core/v2";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useIsAuthenticated, useMsal } from "@azure/msal-react";
import { apiScopes, authConfigured } from "@/lib/auth/msal";

export function FoundryAgentChat({ name }: { name: string }) {
  const t = useTranslations("agentChat");
  const ta = useTranslations("agents");
  const locale = useLocale();
  const { instance, accounts } = useMsal();
  const isAuthenticated = useIsAuthenticated();
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
    // Mesmo intervalo do console: o token expira em ~1h e o chat 401 no meio da conversa sem isso.
    const id = setInterval(acquire, 4 * 60 * 1000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [instance, accounts]);

  if (authConfigured && !isAuthenticated) {
    return <p className="muted">{t("signInFirst")}</p>;
  }

  return (
    <section className="console">
      <div className="console-main">
        <header className="console-head">
          <div className="console-head-meta">
            <p className="t-xs muted-line">
              <Link href="/agents">{ta("title")}</Link>
            </p>
            <h2>{name}</h2>
            {/* Diz DE ONDE o agente vem. Sem isso, esta tela e a de um domínio do showcase
                pareceriam a mesma coisa — e não são: aqui o agente é um recurso do seu projeto. */}
            <p className="console-blurb">{t("subtitle")}</p>
          </div>
        </header>

        <div className="copilotkit-chat-host">
          <CopilotKitProvider
            runtimeUrl="/api/copilotkit"
            headers={{
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
              "Accept-Language": locale,
            }}
          >
            <CopilotChat agentId={name} />
          </CopilotKitProvider>
        </div>
      </div>
    </section>
  );
}
