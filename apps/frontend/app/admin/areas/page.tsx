"use client";

import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { AppShell } from "@/components/shell/AppShell";
import { isAdmin, useMyRoles } from "@/lib/auth/roles";

const Areas = dynamic(() => import("@/components/admin/Areas").then((module) => module.Areas), {
  ssr: false,
});

export default function AdminAreasPage() {
  const t = useTranslations("common");
  const ta = useTranslations("areas");
  const roles = useMyRoles();

  return (
    <AppShell>
      {roles === null ? (
        <p className="muted">{t("loading")}</p>
      ) : isAdmin(roles) ? (
        <Areas />
      ) : (
        <div className="card">{ta.rich("needAdmin", { b: (children) => <b>{children}</b> })}</div>
      )}
    </AppShell>
  );
}
