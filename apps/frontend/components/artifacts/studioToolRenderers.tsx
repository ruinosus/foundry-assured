// The Studio's chat rail must stay a pure conversation: the internal HITL/skill tools
// (confirm_changes = the framework's approval pseudo-tool; update_artifact = approval-gated,
// so it never gets a terminal event and the default card sticks on "Running"; the SkillsProvider
// tools) are surfaced in the StudioSteps strip instead, never as chat cards. Rendering nothing here
// removes the stuck/duplicated cards. Hiding the transcript render does NOT suppress the approval
// CUSTOM event — that is captured in StudioCanvas.onEvent and drives the review bar.
const HIDDEN_IN_TRANSCRIPT = [
  "confirm_changes",
  "update_artifact",
  "load_skill",
  "read_skill_resource",
  "run_skill_script",
];

export const studioToolRenderers = HIDDEN_IN_TRANSCRIPT.map((name) => ({
  name,
  render: () => <></>,
}));
