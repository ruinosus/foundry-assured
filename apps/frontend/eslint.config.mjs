// Flat config (ESLint 9). Next 16 removed the `next lint` subcommand — the lint
// script now calls the ESLint CLI directly, so this file IS the configuration
// (there was none before: `next lint` used to set one up interactively, which in
// CI just failed silently behind continue-on-error).
import next from "eslint-config-next";

const config = [
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"],
  },
  ...next,
];

export default config;
