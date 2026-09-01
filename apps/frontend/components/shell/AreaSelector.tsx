"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { MyArea } from "@/lib/auth/roles";
import { selectArea, selectedAreaId } from "@/lib/area-selection";

export function AreaSelector({ areas }: { areas: MyArea[] }) {
  const t = useTranslations("common");
  const [preference, setPreference] = useState<string | null>(() => selectedAreaId());
  const selected = areas.some((area) => area.id === preference)
    ? preference
    : (areas[0]?.id ?? null);

  useEffect(() => {
    selectArea(selected);
  }, [selected]);

  if (areas.length === 0 || selected === null) return null;

  return (
    <label className="area-selector">
      <span>{t("area")}</span>
      <select
        value={selected}
        aria-label={t("activeArea")}
        onChange={(event) => {
          const next = areas.some((area) => area.id === event.target.value)
            ? event.target.value
            : selected;
          setPreference(next);
          selectArea(next);
        }}
      >
        {areas.map((area) => (
          <option key={area.id} value={area.id}>
            {area.name}
          </option>
        ))}
      </select>
    </label>
  );
}
