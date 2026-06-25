import type { Metadata } from "next";
import "@copilotkit/react-core/v2/styles.css";
import "@/styles/globals.css";
import { Providers } from "@/components/shell/Providers";

export const metadata: Metadata = {
  title: "Foundry Helpdesk",
  description: "Internal engineering support concierge",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body style={{ margin: 0 }}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
