import type { Metadata } from "next";
import "@copilotkit/react-core/v2/styles.css";
import "@/styles/globals.css";
import { Providers } from "@/components/shell/Providers";
import { branding } from "@/lib/branding";

export const metadata: Metadata = {
  title: branding.product,
  description: branding.description,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
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
            __html: `(function(){try{var t=localStorage.getItem('fa-theme');if(t==='light'||t==='dark'){document.documentElement.setAttribute('data-theme',t)}}catch(e){}})()`,
          }}
        />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
