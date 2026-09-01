const AREA_STORAGE_KEY = "foundry-assured.area-id";
export const AREA_SELECTION_EVENT = "foundry-assured:area-selection";

export function selectedAreaId(): string | null {
  if (typeof localStorage === "undefined") return null;
  return localStorage.getItem(AREA_STORAGE_KEY);
}

export function selectArea(areaId: string | null): void {
  if (typeof localStorage === "undefined") return;
  const previous = localStorage.getItem(AREA_STORAGE_KEY);
  if (areaId) localStorage.setItem(AREA_STORAGE_KEY, areaId);
  else localStorage.removeItem(AREA_STORAGE_KEY);
  if (previous !== areaId) {
    window.dispatchEvent(new CustomEvent(AREA_SELECTION_EVENT, { detail: areaId }));
  }
}
