import type { Metadata } from "next";
import "@copilotkit/react-core/v2/styles.css";
import "@/styles/globals.css";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import { Providers } from "@/components/shell/Providers";
import { branding } from "@/lib/branding";

export const metadata: Metadata = {
  title: branding.product,
  description: branding.description,
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // O locale é resolvido no servidor (cookie → Accept-Language → padrão) e vira o `lang` do
  // documento. Deixar "pt-BR" fixo aqui diria ao leitor de tela e ao corretor do browser a
  // língua errada quando o conteúdo estivesse em inglês.
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale} suppressHydrationWarning>
      <head>
        {/*
          Aplica o tema salvo ANTES da primeira pintura. Sem isto a página pinta no tema padrão
          e corrige depois que o React hidrata — a piscada branca que denuncia tema mal feito,
          e que é pior justamente no caso que mais importa aqui (alguém abrindo o console às 23h
          e levando um flash branco na cara).

          Precisa ser síncrono e inline: qualquer script adiado já chega tarde. `system` é a
          ausência do atributo, então o caminho normal não escreve nada e deixa
          `prefers-color-scheme` resolver.
        */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var r=document.documentElement,t=localStorage.getItem('fa-theme');if(t==='light'||t==='dark'){r.setAttribute('data-theme',t)}var d=t==='dark'||((!t||t==='system')&&matchMedia('(prefers-color-scheme: dark)').matches);r.classList.toggle('dark',d)}catch(e){}})()`,
          }}
        />
      </head>
      <body>
        <NextIntlClientProvider locale={locale} messages={messages}>
          <Providers>{children}</Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
