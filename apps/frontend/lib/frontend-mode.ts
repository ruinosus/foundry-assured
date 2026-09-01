export const FRONTEND_MODES = ["legacy", "assured"] as const;
export type FrontendMode = (typeof FRONTEND_MODES)[number];

export const DATA_MODES = ["connected", "local"] as const;
export type DataMode = (typeof DATA_MODES)[number];

function configuredMode<T extends string>(value: string | undefined, allowed: readonly T[], fallback: T): T {
  return value && allowed.includes(value as T) ? (value as T) : fallback;
}

export const frontendMode = configuredMode(
  process.env.NEXT_PUBLIC_FRONTEND_MODE,
  FRONTEND_MODES,
  "legacy",
);

export const dataMode = configuredMode(
  process.env.NEXT_PUBLIC_DATA_MODE,
  DATA_MODES,
  "connected",
);

export const isLocalDataMode = dataMode === "local";
