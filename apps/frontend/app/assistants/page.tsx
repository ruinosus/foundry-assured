"use client";

import { useTranslations } from "next-intl";
import { AssistantsView } from "@/components/assistants/AssistantsView";
import { AppShell } from "@/components/shell/AppShell";
import { canAdmin, useMyRoles } from "@/lib/auth/roles";

export default function Page() {
  const common = useTranslations("common");
  const t = useTranslations("assistants");
  const roles = useMyRoles();

  return (
    <AppShell>
      {roles === null ? (
        <p className="muted">{common("loading")}</p>
      ) : canAdmin(roles) ? (
        <AssistantsView />
      ) : (
        <div className="card">{t("needAdmin")}</div>
      )}
    </AppShell>
  );
}
