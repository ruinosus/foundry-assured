const AREA_STORAGE_KEY = "foundry-assured.area-id";

export function selectedAreaId(): string | null {
  if (typeof localStorage === "undefined") return null;
  return localStorage.getItem(AREA_STORAGE_KEY);
}

export function selectArea(areaId: string | null): void {
  if (typeof localStorage === "undefined") return;
  if (areaId) localStorage.setItem(AREA_STORAGE_KEY, areaId);
  else localStorage.removeItem(AREA_STORAGE_KEY);
}
