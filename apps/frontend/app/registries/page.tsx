"use client";

import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { AppShell } from "@/components/shell/AppShell";
import { canAdmin, useMyRoles } from "@/lib/auth/roles";

const RegistriesView = dynamic(
  () => import("@/components/registries/RegistriesView").then((module) => module.RegistriesView),
  { ssr: false },
);

export default function RegistriesPage() {
  const common = useTranslations("common");
  const t = useTranslations("registries");
  const roles = useMyRoles();
  return (
    <AppShell>
      {roles === null ? <p className="muted">{common("loading")}</p> : canAdmin(roles) ? <RegistriesView /> : <div className="card">{t("needAdmin")}</div>}
    </AppShell>
  );
}