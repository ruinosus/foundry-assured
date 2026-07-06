"use client";

// Artifacts Studio — a CopilotKit + AG-UI conversational canvas: chat on the left, a live
// sandboxed HTML preview on the right. Mirrors this repo's REAL v2 pattern (NOT the v1
// useCoAgent/useCopilotAction hooks, which aren't exported from `/v2`):
//   - components/chat/HelpdeskApp.tsx      -> <CopilotKitProvider> + acquireTokenSilent token
//   - components/chat/WorkflowSteps.tsx    -> useAgent({agentId}) from /v2 + agent.subscribe
//   - components/chat/TicketApproval.tsx   -> interrupt tap (onEvent) + agent.runAgent({resume})
//
// LIVE HTML (backend state is a FLAT STRING field `html` — see
// app/agents/artifacts_studio.py: state_schema={"html": {"type":"string"}},
// predict_state_config maps it to update_artifact's `html` tool argument):
//   - STATE_SNAPSHOT: event.snapshot.html is the full document.
//   - STATE_DELTA: event.delta is a JSON-Patch array; since the tool argument is a flat
//     string (never nested), the only op that appears targets "/html" with a string value —
//     we take that value as the new full string. No generic JSON-Patch engine needed.
// setHtml is throttled with requestAnimationFrame to avoid a re-render per streamed token.
//
// EDIT APPROVAL (require_confirmation=True) — HIGHEST-RISK WIRING, best-effort now, verified
// live in Canvas Chunk 3: per the installed agent_framework_ag_ui rc5 (_run_common.py:431-444),
// this emits a CUSTOM event named "function_approval_request" with
// value={ id, function_call: { call_id, name, arguments } }, and the registered interrupt id is
// func_call_id or content.id (i.e. v.id, falling back to the call's call_id). We resolve it via
// the SAME runAgent({resume}) mechanism TicketApproval.tsx uses, but the payload is NOT a bare
// boolean: the backend continuation parses a `confirm_changes` tool-result body shaped
// { accepted: bool, steps: [...] } (_agent_run.py:309-336, _is_confirm_changes_response). See the
// TODO(verify-live) at the call site below.
//
// TITLE/TYPE/SKILL AUTO-FILL (Skills Chunk 4, "option c") — VERIFIED LIVE against the installed
// agent_framework_ag_ui rc5 (see app/agents/artifacts_studio.py, commit "studio state — verified-
// live title/type/skill via approval args"): a state_schema key with NO predict_state_config
// entry stays an empty {} — it is NEVER auto-populated. So title/type/skill are NOT read from
// agent state (only `html` is, via STATE_SNAPSHOT/STATE_DELTA above). Their values instead arrive
// fully parsed in the SAME function_approval_request event this file already taps for the
// approval card, under value.function_call.arguments = { html, title, type, skill }. The onEvent
// handler below reads them from there.

import { CopilotChat, CopilotKitProvider, useAgent } from "@copilotkit/react-core/v2";
import { useIsAuthenticated, useMsal } from "@azure/msal-react";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { apiScopes, authConfigured } from "@/lib/auth/msal";
import { authedFetch } from "@/lib/auth/api";
import { LivePreview } from "./LivePreview";

const MAX_TITLE = 200;
// Kept as the allowed-set for displaying/normalizing the agent-filled `type` — the manual
// Type <select> is gone (Skills Chunk 4): the agent now produces type as part of update_artifact.
const ARTIFACT_TYPES = ["report", "presentation", "walkthrough", "dashboard"] as const;
const SKILLS = ["auto", "slides", "report", "dashboard", "walkthrough"] as const;

type PendingApproval = {
  id: string;
  toolName?: string;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function htmlFromSnapshot(event: any): string | undefined {
  const snap = event?.snapshot;
  return snap && typeof snap.html === "string" ? snap.html : undefined;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function htmlFromDelta(event: any, fallback: string): string {
  const delta = event?.delta;
  if (!Array.isArray(delta)) return fallback;
  let next = fallback;
  for (const op of delta) {
    if (op && typeof op === "object" && op.path === "/html" && typeof op.value === "string") {
      next = op.value;
    }
  }
  return next;
}

const card: React.CSSProperties = {
  border: "1px solid #2563eb33",
  borderLeft: "3px solid #2563eb",
  borderRadius: 8,
  padding: 12,
  margin: "0 0 8px",
  background: "#eff6ff",
  fontFamily: "system-ui",
};
const btn = (bg: string): React.CSSProperties => ({
  padding: "6px 14px",
  borderRadius: 6,
  border: "none",
  background: bg,
  color: "white",
  cursor: "pointer",
  fontSize: 13,
  fontWeight: 600,
});

function StudioCanvas() {
  const { agent } = useAgent({ agentId: "artifacts-studio" });
  const [html, setHtml] = useState("");
  const [pending, setPending] = useState<PendingApproval | null>(null);
  const [approving, setApproving] = useState(false);
  const [title, setTitle] = useState("");
  const [type, setType] = useState<string>("");
  const [skill, setSkill] = useState<string>("auto");
  const [usedSkill, setUsedSkill] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const router = useRouter();

  // rAF-throttle setHtml so a burst of STATE_DELTA tokens doesn't trigger a re-render each.
  const rafRef = useRef<number | null>(null);
  const latestHtmlRef = useRef("");

  function scheduleSetHtml(next: string) {
    latestHtmlRef.current = next;
    if (rafRef.current !== null) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      setHtml(latestHtmlRef.current);
    });
  }

  useEffect(() => {
    if (!agent) return;
    const sub = agent.subscribe({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onStateSnapshotEvent: ({ event }: any) => {
        const snap = htmlFromSnapshot(event);
        if (snap !== undefined) scheduleSetHtml(snap);
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onStateDeltaEvent: ({ event }: any) => {
        scheduleSetHtml(htmlFromDelta(event, latestHtmlRef.current));
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onEvent: ({ event }: any) => {
        // Edit-confirmation interrupt. Handle the documented name plus, defensively, the
        // workflow-HITL name TicketApproval.tsx taps for the same CUSTOM-event channel.
        if (
          event?.type === "CUSTOM" &&
          (event?.name === "function_approval_request" || event?.name === "request_info")
        ) {
          const v = event.value ?? {};
          const fc = v.function_call ?? {};
          // Cover both shapes: function_approval_request -> { id, function_call: { call_id } };
          // request_info (the TicketApproval.tsx fallback) -> { request_id, data: {...} } (no id/
          // function_call). Without request_id the fallback would drop the event and hang the run.
          const id: string | undefined = v.id ?? v.request_id ?? fc.call_id;
          if (!id) return;
          setPending({ id, toolName: fc.name });

          // Auto-fill title/type/skill (option c — see the header comment). fc.arguments is the
          // parsed update_artifact call args in the normal shape, but defend against a raw JSON
          // string (some adapter versions/paths deliver tool args unparsed).
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          let args: any = fc.arguments ?? {};
          if (typeof args === "string") {
            try {
              args = JSON.parse(args);
            } catch {
              args = {};
            }
          }
          if (args.title) setTitle(args.title);
          if (args.type) setType(args.type);
          if (args.skill) setUsedSkill(args.skill);
          // The approval event carries the COMPLETE html too — take it as authoritative so the
          // preview reflects the final document even if a STATE_DELTA token was missed.
          if (typeof args.html === "string" && args.html) scheduleSetHtml(args.html);
        }
      },
    });
    return () => sub.unsubscribe();
  }, [agent]);

  useEffect(
    () => () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    },
    [],
  );

  async function respond(approved: boolean) {
    if (!agent || approving || !pending) return;
    setApproving(true);
    const id = pending.id;
    setPending(null);
    try {
      await agent.runAgent({
        resume: [
          {
            interruptId: id,
            status: approved ? "resolved" : "cancelled",
            // VERIFIED LIVE (Studio E2E): the backend's confirm_changes continuation
            // (agent_framework_ag_ui _agent_run.py _is_confirm_changes_response) accepts a
            // { accepted, steps } body. The resume bridge maps this to the backend's
            // { interrupts: [{ id, value }] } form; interruptId is the update_artifact call_id
            // (event.value.id). Confirmed end-to-end by e2e/artifacts-studio.spec.ts.
            payload: { accepted: approved, steps: [] },
          },
        ],
      });
    } finally {
      setApproving(false);
    }
  }

  async function save() {
    if (!title || title.length > MAX_TITLE || !type || !html || saving) return;
    setSaving(true);
    setSaveError(null);
    try {
      const r = await authedFetch("/api/artifacts/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          type,
          html,
          skill: usedSkill || (skill === "auto" ? undefined : skill),
        }),
      });
      if (!r.ok) {
        setSaveError(`save failed (${r.status})`);
        return;
      }
      const dto = await r.json();
      router.push(`/artifacts/${dto.id}`);
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  // Pin a skill + regenerate: send a chat turn telling the agent which skill to use, then run it
  // — the SAME addMessage+runAgent send mechanism this repo already uses to program-send a chat
  // message (see components/console/SuggestedPrompts.tsx: agent.addMessage(...) + agent.runAgent()),
  // not a guessed API. Disabled while a run/approval is in flight so it can't race the pending
  // approval card.
  async function regenerate() {
    if (!agent || approving || pending) return;
    const id =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.round(Math.random() * 1e6)}`;
    const content =
      skill === "auto"
        ? "Regenerate the artifact."
        : `Use the ${skill} skill and regenerate the artifact.`;
    agent.addMessage({ id, role: "user", content });
    await agent.runAgent();
  }

  const titleOk = title.length > 0 && title.length <= MAX_TITLE;
  const canSave = titleOk && Boolean(type) && Boolean(html) && !saving;
  const typeLabel =
    type && (ARTIFACT_TYPES as readonly string[]).includes(type)
      ? type[0].toUpperCase() + type.slice(1)
      : type || "—";

  return (
    <div style={{ display: "flex", gap: 16, minHeight: "70vh" }}>
      <div
        style={{
          flex: "1 1 40%",
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          border: "1px solid var(--border)",
          borderRadius: 12,
          overflow: "hidden",
        }}
      >
        <div style={{ flex: 1, minHeight: "70vh" }}>
          <CopilotChat agentId="artifacts-studio" />
        </div>
      </div>

      <div style={{ flex: "1 1 60%", minWidth: 0, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <label className="muted" style={{ fontSize: 12 }}>
            Title
          </label>
          <input
            className="acct-btn"
            style={{ cursor: "text" }}
            placeholder="Q3 status report"
            value={title}
            maxLength={MAX_TITLE}
            onChange={(e) => setTitle(e.target.value)}
          />
          {!titleOk && title.length > 0 && (
            <span className="muted" style={{ fontSize: 12 }}>
              Title must be 1–{MAX_TITLE} characters.
            </span>
          )}

          <label className="muted" style={{ fontSize: 12 }}>
            Type <span style={{ fontWeight: 400 }}>(set by the agent)</span>
          </label>
          <div className="acct-btn" style={{ cursor: "default" }}>
            {typeLabel}
          </div>

          <label className="muted" style={{ fontSize: 12 }}>
            Skill
          </label>
          <div style={{ display: "flex", gap: 8 }}>
            <select
              className="acct-btn"
              style={{ flex: 1 }}
              value={skill}
              onChange={(e) => setSkill(e.target.value)}
            >
              {SKILLS.map((s) => (
                <option key={s} value={s}>
                  {s === "auto" ? "Auto" : s[0].toUpperCase() + s.slice(1)}
                </option>
              ))}
            </select>
            <button
              className="acct-btn"
              disabled={!agent || approving || Boolean(pending)}
              onClick={regenerate}
            >
              Regenerate
            </button>
          </div>
          {usedSkill && (
            <span className="muted" style={{ fontSize: 12 }}>
              Generated with: {usedSkill}
            </span>
          )}
        </div>

        {pending && (
          <div style={card}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Apply this version of the artifact?</div>
            {pending.toolName && (
              <div style={{ fontSize: 13, marginBottom: 10 }}>
                <b>Tool:</b> <code>{pending.toolName}</code>
              </div>
            )}
            <div style={{ display: "flex", gap: 8 }}>
              <button style={btn("#16a34a")} onClick={() => respond(true)}>
                Approve
              </button>
              <button style={btn("#dc2626")} onClick={() => respond(false)}>
                Reject
              </button>
            </div>
          </div>
        )}

        <LivePreview html={html || "<!doctype html><html><body></body></html>"} />

        {saveError && (
          <p className="muted" style={{ margin: 0 }}>
            ⚠️ {saveError}
          </p>
        )}

        <div>
          <button className="btn btn-solid" disabled={!canSave} onClick={save}>
            {saving ? "Saving…" : "Save as draft"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Studio({ authorization }: { authorization?: string }) {
  return (
    <CopilotKitProvider
      runtimeUrl="/api/copilotkit"
      headers={authorization ? { Authorization: authorization } : undefined}
    >
      <StudioCanvas />
    </CopilotKitProvider>
  );
}

const center: React.CSSProperties = {
  display: "flex",
  height: "100%",
  minHeight: 360,
  alignItems: "center",
  justifyContent: "center",
  fontFamily: "system-ui",
  flexDirection: "column",
  gap: 16,
};

function AuthedStudio() {
  const { instance, accounts } = useMsal();
  const isAuthenticated = useIsAuthenticated();
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated || !accounts[0]) return;
    let active = true;
    const acquire = () =>
      instance
        .acquireTokenSilent({ scopes: apiScopes, account: accounts[0] })
        .then((r) => {
          if (active) setToken(r.accessToken);
        })
        .catch(() => instance.acquireTokenRedirect({ scopes: apiScopes }));
    acquire();
    // Refresh well before the ~1h access-token expiry (mirrors HelpdeskApp.tsx).
    const id = setInterval(acquire, 4 * 60 * 1000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [isAuthenticated, accounts, instance]);

  if (!isAuthenticated) {
    return (
      <div style={center}>
        <p>Sign in to use the Artifacts Studio.</p>
        <button
          onClick={() => instance.loginRedirect({ scopes: apiScopes })}
          style={{
            padding: "10px 16px",
            borderRadius: 8,
            border: "1px solid #2563eb",
            background: "#2563eb",
            color: "white",
            cursor: "pointer",
            fontSize: 14,
          }}
        >
          Sign in with Microsoft
        </button>
      </div>
    );
  }
  if (!token) return <div style={center}>Acquiring token…</div>;
  return <Studio authorization={`Bearer ${token}`} />;
}

export function ArtifactStudio() {
  // Module-constant branch (not a hook), same pattern as HelpdeskApp — safe early return.
  if (!authConfigured) return <Studio />;
  return <AuthedStudio />;
}
