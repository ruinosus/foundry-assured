"use client";

import { useTranslations } from "next-intl";
import { AuditView } from "@/components/audit/AuditView";
import { AppShell } from "@/components/shell/AppShell";
import { canAdmin, useMyRoles } from "@/lib/auth/roles";

export default function Page() {
  const common = useTranslations("common");
  const t = useTranslations("audit");
  const roles = useMyRoles();

  return (
    <AppShell>
      {roles === null ? (
        <p className="muted">{common("loading")}</p>
      ) : canAdmin(roles) ? (
        <AuditView />
      ) : (
        <div className="card">{t("needAdmin")}</div>
      )}
    </AppShell>
  );
}
