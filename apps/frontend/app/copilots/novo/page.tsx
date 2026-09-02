"use client";

import { useTranslations } from "next-intl";
import { AppShell } from "@/components/shell/AppShell";
import { CopilotNew } from "@/components/copilots/CopilotNew";
import { canAuthor, useMyRoles } from "@/lib/auth/roles";

export default function Page() {
  const common = useTranslations("common");
  const t = useTranslations("copilots");
  const roles = useMyRoles();

  return (
    <AppShell>
      {roles === null ? (
        <p className="muted">{common("loading")}</p>
      ) : canAuthor(roles) ? (
        <CopilotNew />
      ) : (
        <div className="card">{t("needAuthor")}</div>
      )}
    </AppShell>
  );
}
