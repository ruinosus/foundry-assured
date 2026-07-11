// Demo mode (no Azure). When NEXT_PUBLIC_DEMO_MODE=1, the app talks to an aimock
// AG-UI server replaying a recorded fixture instead of the real backend — so the
// whole flow (steps, grounded answer, HITL) runs with zero Azure and no sign-in.
// Set by scripts/demo.sh. See README › "Demo mode — see it with no Azure".
export const demoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "1";
