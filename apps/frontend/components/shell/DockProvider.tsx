"use client";

// O provider do CopilotKit no nível do SHELL — e por que ele subiu para cá.
//
// O dock tinha provider próprio, dentro do próprio dock. Isso funcionava enquanto ele só
// respondia perguntas: o conteúdo da página era IRMÃO do provider, não descendente. Assim que o
// wizard precisou registrar uma tool que o agente do dock pudesse chamar (`propose_field`), o
// arranjo deixou de servir — uma tool registrada fora do provider é invisível para o agente
// dentro dele.
//
// NÃO ENVOLVE A ROTA DE DOMÍNIO. O `/d/[domain]` tem provider próprio (o console É o chat), e
// dois providers aninhados disputariam o mesmo runtime. A regra é simples e defensável: o dock é
// das telas de GESTÃO; numa rota de domínio o chat já é a tela.
//
// A troca de agente não remonta mais nada. Antes era `key={agentId}` no provider — remontar era o
// jeito de não vazar histórico de um agente para o outro. Remontar agora apagaria o rascunho do
// wizard junto, então cada agente ganha o SEU `threadId` e o histórico fica separado por
// identidade, não por destruição.

import { CopilotKitProvider } from "@copilotkit/react-core/v2";
import { useLocale } from "next-intl";
import { usePathname } from "next/navigation";
import { useMemo, type ReactNode } from "react";

export function DockProvider({
  authorization,
  children,
}: {
  authorization?: string;
  children: ReactNode;
}) {
  const locale = useLocale();
  const pathname = usePathname() || "/";
  const naRotaDeDominio = pathname.startsWith("/d/");

  const headers = useMemo(
    () => ({
      ...(authorization ? { Authorization: authorization } : {}),
      "Accept-Language": locale,
    }),
    [authorization, locale],
  );

  if (naRotaDeDominio) return <>{children}</>;

  return (
    <CopilotKitProvider runtimeUrl="/api/copilotkit" headers={headers}>
      {children}
    </CopilotKitProvider>
  );
}
