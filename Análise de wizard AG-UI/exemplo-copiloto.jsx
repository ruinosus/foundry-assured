// Exemplo prático, animado: Ana cria o copiloto de RH, ele é validado, publicado,
// usado dentro do caso de uso, medido e atualizado para v2.
//
// Uma árvore só, renderizada a partir de T. Os painéis persistem; o que muda é o
// conteúdo dentro deles (Shot) e os valores interpolados.

const { CompositionStage, useComposition, Captions, Shot, Easing, animate, clamp } = window;

const C = {
  bg: "oklch(0.977 0.003 258)",
  s: "#fff",
  line: "oklch(0.902 0.006 258)",
  ls: "oklch(0.836 0.008 258)",
  ink: "oklch(0.235 0.017 262)",
  mut: "oklch(0.487 0.018 260)",
  acc: "oklch(0.452 0.152 262)",
  accW: "oklch(0.955 0.024 262)",
  pass: "oklch(0.492 0.126 158)",
  passW: "oklch(0.958 0.028 158)",
  wait: "oklch(0.545 0.126 68)",
  waitW: "oklch(0.960 0.038 68)",
  block: "oklch(0.505 0.176 26)",
  blockW: "oklch(0.958 0.030 26)",
  sunk: "oklch(0.955 0.005 258)",
  dark: "oklch(0.235 0.017 262)",
  darkInk: "oklch(0.944 0.004 258)",
};
const MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

const MOTION = {
  fade: (start, len) => animate({ from: 0, to: 1, start, end: start + (len || 0.5), ease: Easing.easeOutCubic }),
  rise: (start, len) => animate({ from: 16, to: 0, start, end: start + (len || 0.6), ease: Easing.easeOutCubic }),
  count: (start, end, from, to) => animate({ from, to, start, end, ease: Easing.easeOutQuart }),
};

function typed(text, T, start, cps) {
  const n = Math.floor(clamp((T - start) * (cps || 26), 0, text.length));
  return text.slice(0, n);
}

function Label({ children, color }) {
  return (
    <div style={{ fontFamily: MONO, fontSize: 15, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: color || C.mut }}>
      {children}
    </div>
  );
}

function Card({ children, style }) {
  return (
    <div style={{ background: C.s, border: "1px solid " + C.line, borderRadius: 8, padding: 20, display: "flex", flexDirection: "column", gap: 12, ...style }}>
      {children}
    </div>
  );
}

function Chip({ children, tone }) {
  const t = tone || "n";
  const map = {
    n: { bg: C.s, bd: C.line, ink: C.ink },
    a: { bg: C.accW, bd: C.acc, ink: C.acc },
    p: { bg: C.passW, bd: C.pass, ink: C.pass },
    w: { bg: C.waitW, bd: C.wait, ink: C.wait },
    b: { bg: C.blockW, bd: C.block, ink: C.block },
  }[t];
  return (
    <span style={{ fontFamily: MONO, fontSize: 16, padding: "4px 12px", borderRadius: 999, background: map.bg, border: "1px solid " + map.bd, color: map.ink, whiteSpace: "nowrap" }}>
      {children}
    </span>
  );
}

function Field({ label, value, T, start, focused }) {
  const o = MOTION.fade(start)(T);
  const txt = typed(value, T, start + 0.15, 30);
  const caret = txt.length < value.length && T > start;
  return (
    <div style={{ opacity: o, display: "flex", flexDirection: "column", gap: 6 }}>
      <Label>{label}</Label>
      <div style={{
        border: "1px solid " + (focused ? C.acc : C.ls), background: focused ? C.accW : C.s,
        borderRadius: 4, padding: "12px 14px", fontSize: 20, color: C.ink, minHeight: 48,
      }}>
        {txt}{caret ? <span style={{ color: C.acc }}>▌</span> : null}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────── o painel esquerdo (a tela)

function SceneVazio({ T, CUES }) {
  const o = MOTION.fade(0.2)(T);
  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", gap: 18, opacity: o }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
        <div style={{ fontSize: 34, fontWeight: 640, letterSpacing: "-0.015em" }}>Copilotos</div>
        <div style={{ fontSize: 19, color: C.mut }}>projeto fa-prod-eastus2</div>
      </div>
      <div style={{
        border: "1px dashed " + C.ls, borderRadius: 10, padding: 44, display: "flex",
        flexDirection: "column", gap: 12, alignItems: "center", textAlign: "center",
      }}>
        <div style={{ fontSize: 24, fontWeight: 620 }}>Nenhum copiloto ainda</div>
        <div style={{ fontSize: 19, color: C.mut, maxWidth: "52ch", lineHeight: 1.5 }}>
          O RH pede ajuda para montar agentes e bases sem escrever JSON. Um copiloto é um documento — comece por ele.
        </div>
        <div style={{ marginTop: 8, display: "flex", gap: 10 }}>
          <span style={{ padding: "12px 18px", border: "1px solid " + C.acc, background: C.acc, color: "#fff", borderRadius: 8, fontSize: 19, fontWeight: 600 }}>Novo copiloto</span>
          <span style={{ padding: "12px 18px", border: "1px solid " + C.ls, borderRadius: 8, fontSize: 19, fontWeight: 600 }}>Importar bundle</span>
        </div>
      </div>
    </div>
  );
}

function SceneBuilder({ T, CUES }) {
  const s = CUES.Builder;
  const targets = [
    { id: "flows/agent", fields: ["description", "instructions"], at: s + 4.4 },
    { id: "flows/knowledge", fields: ["description"], at: s + 5.2 },
  ];
  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 14, opacity: MOTION.fade(s)(T) }}>
        <div style={{ fontSize: 30, fontWeight: 640, letterSpacing: "-0.015em" }}>Novo copiloto</div>
        <Chip tone="a">okf · type: copilot</Chip>
      </div>
      <Card style={{ gap: 14 }}>
        <Field label="identificador" value="atendimento-rh" T={T} start={s + 0.4} focused={T < s + 2.2} />
        <Field label="título" value="Copiloto de RH" T={T} start={s + 1.8} focused={T >= s + 1.8 && T < s + 3.2} />
        <div style={{ opacity: MOTION.fade(s + 3.0)(T), display: "flex", flexDirection: "column", gap: 8 }}>
          <Label>superfície</Label>
          <div style={{ display: "flex", gap: 8 }}>
            <Chip tone={T > s + 3.4 ? "a" : "n"}>dock lateral</Chip>
            <Chip>console</Chip>
            <Chip>ancorado no campo</Chip>
          </div>
        </div>
        <div style={{ opacity: MOTION.fade(s + 4.0)(T), display: "flex", flexDirection: "column", gap: 8 }}>
          <Label color={C.acc}>alvos — em quais campos ele escreve</Label>
          {targets.map((t) => (
            <div key={t.id} style={{
              opacity: MOTION.fade(t.at)(T), transform: "translateY(" + MOTION.rise(t.at)(T) + "px)",
              border: "1px solid " + C.acc, background: C.accW, borderRadius: 6, padding: 12,
              display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
            }}>
              <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 600 }}>{t.id}</span>
              <span style={{ fontSize: 16, color: C.mut }}>escreve</span>
              {t.fields.map((f) => <Chip key={f} tone="n">{f}</Chip>)}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function SceneValidar({ T, CUES }) {
  const s = CUES.Validar;
  const checks = [
    { t: "Schema OKF · 3 documentos com type", tone: "p", at: s + 0.4 },
    { t: "Citações resolvem · 12 de 12 · 100%", tone: "p", at: s + 1.0 },
    { t: "Alvos existem neste projeto", tone: "p", at: s + 1.6 },
    { t: "Escrita atrás de gate · require_approval: always", tone: "p", at: s + 2.2 },
  ];
  const appear = MOTION.fade(s + 3.0)(T);
  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ fontSize: 30, fontWeight: 640, letterSpacing: "-0.015em", opacity: MOTION.fade(s)(T) }}>Validação</div>
      <Card>
        {checks.map((c) => (
          <div key={c.t} style={{ opacity: MOTION.fade(c.at)(T), display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ width: 26, height: 26, borderRadius: 999, background: C.pass, color: "#fff", display: "grid", placeItems: "center", fontSize: 16, fontWeight: 700 }}>✓</span>
            <span style={{ fontSize: 20 }}>{c.t}</span>
          </div>
        ))}
      </Card>
      <div style={{
        opacity: appear, transform: "translateY(" + MOTION.rise(s + 3.0)(T) + "px)",
        background: C.waitW, border: "1px solid " + C.wait, borderRadius: 8, padding: 18,
        display: "flex", flexDirection: "column", gap: 12,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Label color={C.wait}>aguardando aprovação</Label>
          <span style={{ marginLeft: "auto" }}><Chip tone="p">seu papel: Admin ✓</Chip></span>
        </div>
        <div style={{ fontSize: 22, fontWeight: 640 }}>Publicar copilots/atendimento-rh?</div>
        <div style={{ fontFamily: MONO, fontSize: 16, lineHeight: 1.5, background: C.s, border: "1px solid " + C.ls, borderRadius: 4, padding: 12 }}>
          POST /api/foundry/datasets/copilot-atendimento-rh{"\n"}{"{ \"version\": \"1\", \"files\": [\"index.md\", \"hitl.md\", \"log.md\"] }"}
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <span style={{
            padding: "12px 18px", borderRadius: 8, fontSize: 19, fontWeight: 600,
            border: "1px solid " + C.pass, background: T > s + 4.2 ? C.pass : C.s, color: T > s + 4.2 ? "#fff" : C.pass,
          }}>Aprovar</span>
          <span style={{ padding: "12px 18px", borderRadius: 8, fontSize: 19, fontWeight: 600, border: "1px solid " + C.ls, background: C.s }}>Corrigir</span>
          <span style={{ padding: "12px 18px", borderRadius: 8, fontSize: 19, fontWeight: 600, border: "1px solid " + C.block, background: C.s, color: C.block }}>Recusar com motivo</span>
        </div>
      </div>
    </div>
  );
}

function SceneUso({ T, CUES }) {
  const s = CUES.EmUso;
  const steps = [
    { k: "agente", l: "Triagem — intenção e urgência", at: s + 0.3, tone: "n" },
    { k: "agente", l: "Buscar na base rh-politicas", at: s + 0.9, tone: "n" },
    { k: "agente", l: "Redigir a resposta", at: s + 1.5, tone: "a" },
    { k: "humano", l: "Aprovar a abertura do chamado", at: s + 2.1, tone: "w" },
  ];
  const dec = s + 5.4;
  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 14, opacity: MOTION.fade(s)(T) }}>
        <div style={{ fontSize: 30, fontWeight: 640, letterSpacing: "-0.015em" }}>Atendimento de RH</div>
        <Chip>type: usecase</Chip>
      </div>
      <Card style={{ gap: 8 }}>
        {steps.map((st) => {
          const on = T > st.at;
          const col = st.tone === "w" ? C.wait : st.tone === "a" ? C.acc : C.line;
          return (
            <div key={st.l} style={{
              opacity: MOTION.fade(st.at)(T), display: "flex", alignItems: "baseline", gap: 14,
              padding: "10px 14px", background: C.sunk, borderRadius: 4, borderLeft: "4px solid " + (on ? col : C.line),
            }}>
              <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: st.tone === "w" ? C.wait : C.mut, minWidth: 96 }}>{st.k}</span>
              <span style={{ fontSize: 20 }}>{st.l}</span>
            </div>
          );
        })}
      </Card>

      <div style={{
        opacity: MOTION.fade(s + 3.0)(T), transform: "translateY(" + MOTION.rise(s + 3.0)(T) + "px)",
        border: "1px solid " + (T > dec ? C.pass : C.wait), borderLeft: "4px solid " + (T > dec ? C.pass : C.wait),
        background: C.s, borderRadius: 6, padding: 16, display: "flex", flexDirection: "column", gap: 10,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Label color={T > dec ? C.pass : C.wait}>{T > dec ? "usada — valor no campo" : "proposta · instructions"}</Label>
          <span style={{ marginLeft: "auto", fontSize: 16, color: C.mut }}>{T > dec ? "fonte registrada em metadata.provenance" : "aguardando sua decisão"}</span>
        </div>
        <div style={{ borderRadius: 4, overflow: "hidden", border: "1px solid " + C.line, fontFamily: MONO, fontSize: 16, lineHeight: 1.5 }}>
          <div style={{ display: "flex", gap: 10, padding: "8px 12px", background: C.blockW }}>
            <span style={{ color: C.block, fontWeight: 700 }}>−</span>
            <span style={{ textDecoration: "line-through" }}>Você responde dúvidas de RH citando a política.</span>
          </div>
          <div style={{ display: "flex", gap: 10, padding: "8px 12px", background: C.passW }}>
            <span style={{ color: C.pass, fontWeight: 700 }}>+</span>
            <span>{typed("Você atende dúvidas de RH consultando rh-politicas e cita sempre o documento de origem. Sem fonte, diga que não sabe.", T, s + 3.4, 34)}</span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <Chip tone="n">1 rh-politicas/ferias.md ↗</Chip>
          <Chip tone="n">2 rh-politicas/conduta.md ↗</Chip>
          <span style={{ marginLeft: "auto", display: "flex", gap: 10 }}>
            <span style={{
              padding: "10px 16px", borderRadius: 8, fontSize: 18, fontWeight: 600, border: "1px solid " + C.pass,
              background: T > dec ? C.pass : C.s, color: T > dec ? "#fff" : C.pass,
            }}>Usar</span>
            <span style={{ padding: "10px 16px", borderRadius: 8, fontSize: 18, fontWeight: 600, border: "1px solid " + C.ls }}>Editar</span>
            <span style={{ padding: "10px 16px", borderRadius: 8, fontSize: 18, fontWeight: 600, border: "1px solid " + C.ls, color: C.mut }}>Descartar</span>
          </span>
        </div>
      </div>
    </div>
  );
}

function SceneMedicao({ T, CUES }) {
  const s = CUES.Medicao;
  const used = Math.round(MOTION.count(s + 0.3, s + 2.6, 0, 82)(T));
  const edited = Math.round(MOTION.count(s + 0.8, s + 3.0, 0, 34)(T));
  const rows = [
    { f: "instructions", o: "usada", at: s + 3.2, tone: C.pass },
    { f: "description", o: "usada com correção", at: s + 3.8, tone: C.pass },
    { f: "name", o: "descartada — “não segue o padrão do time”", at: s + 4.4, tone: C.block },
  ];
  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ fontSize: 30, fontWeight: 640, letterSpacing: "-0.015em", opacity: MOTION.fade(s)(T) }}>Depois de 1.284 conversas</div>
      <div style={{ display: "flex", gap: 14 }}>
        <Card style={{ flex: 1, gap: 6 }}>
          <div style={{ fontSize: 56, fontWeight: 620, fontVariantNumeric: "tabular-nums", letterSpacing: "-0.02em", color: C.pass }}>{used}%</div>
          <div style={{ fontSize: 19, color: C.mut }}>propostas aproveitadas</div>
          <div style={{ height: 6, borderRadius: 999, background: C.line, overflow: "hidden" }}>
            <div style={{ height: "100%", width: used + "%", background: C.pass }} />
          </div>
        </Card>
        <Card style={{ flex: 1, gap: 6 }}>
          <div style={{ fontSize: 56, fontWeight: 620, fontVariantNumeric: "tabular-nums", letterSpacing: "-0.02em" }}>{edited}%</div>
          <div style={{ fontSize: 19, color: C.mut }}>precisaram de correção</div>
          <div style={{ fontSize: 16, color: C.mut, lineHeight: 1.45 }}>as duas juntas, sempre: muito usado e muito editado é tolerância, não uso</div>
        </Card>
      </div>
      <Card style={{ gap: 10 }}>
        <Label>decisões — o que entrou na trilha</Label>
        {rows.map((r) => (
          <div key={r.f} style={{ opacity: MOTION.fade(r.at)(T), display: "flex", alignItems: "baseline", gap: 12, fontSize: 19 }}>
            <span style={{ width: 10, height: 10, borderRadius: 999, background: r.tone }} />
            <span style={{ fontFamily: MONO, fontSize: 17 }}>{r.f}</span>
            <span style={{ color: C.mut }}>{r.o}</span>
          </div>
        ))}
        <div style={{ fontSize: 16, color: C.mut, lineHeight: 1.45 }}>o texto não entra na trilha — só o desfecho, o campo, as fontes e o tamanho</div>
      </Card>
    </div>
  );
}

function SceneUpdate({ T, CUES }) {
  const s = CUES.Atualizacao;
  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 14, opacity: MOTION.fade(s)(T) }}>
        <div style={{ fontSize: 30, fontWeight: 640, letterSpacing: "-0.015em" }}>Uma mudança, seis semanas depois</div>
      </div>
      <Card style={{ gap: 12 }}>
        <div style={{ fontSize: 20, lineHeight: 1.5, color: C.ink }}>
          O RH passou a manter também as bases de benefícios. O copiloto precisa escrever <span style={{ fontFamily: MONO, fontSize: 18 }}>instructions</span> na base — um campo novo, no mesmo alvo.
        </div>
        <div style={{ opacity: MOTION.fade(s + 1.2)(T), display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", border: "1px solid " + C.acc, background: C.accW, borderRadius: 6, padding: 12 }}>
          <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 600 }}>flows/knowledge</span>
          <span style={{ fontSize: 16, color: C.mut }}>escreve</span>
          <Chip tone="n">description</Chip>
          <span style={{ opacity: MOTION.fade(s + 1.8)(T) }}><Chip tone="a">+ instructions</Chip></span>
        </div>
        <div style={{ opacity: MOTION.fade(s + 2.6)(T), display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          <span style={{ padding: "10px 16px", borderRadius: 8, border: "1px solid " + C.acc, background: C.acc, color: "#fff", fontSize: 18, fontWeight: 600 }}>Abrir PR</span>
          <span style={{ fontFamily: MONO, fontSize: 17, color: C.mut }}>okf-to-git · index.md +1 −1</span>
          <span style={{ opacity: MOTION.fade(s + 3.6)(T) }}><Chip tone="p">merge · okf-to-dataset → v2</Chip></span>
        </div>
      </Card>
      <div style={{ opacity: MOTION.fade(s + 4.4)(T), display: "flex", gap: 14, alignItems: "stretch" }}>
        <Card style={{ flex: 1, gap: 8 }}>
          <Label>catálogo</Label>
          <div style={{ display: "flex", alignItems: "baseline", gap: 12, fontSize: 20 }}>
            <b style={{ fontWeight: 650 }}>Copiloto de RH</b>
            <Chip tone="p">publicado</Chip>
            <span style={{ marginLeft: "auto", fontFamily: MONO, fontSize: 18, color: C.mut, textDecoration: "line-through" }}>v1</span>
            <span style={{ fontFamily: MONO, fontSize: 20, fontWeight: 700, color: C.acc }}>v2</span>
          </div>
          <div style={{ fontSize: 17, color: C.mut }}>escreve 3 campos · dock lateral · aproveitamento 82%</div>
        </Card>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────── o painel direito (o bundle)

function BundlePanel({ T, CUES }) {
  const s = CUES.Bundle;
  const base = [
    "---",
    "type: copilot",
    "title: Copiloto de RH",
    "resource: atendimento-rh",
    'okf_version: "0.2"',
    "provenance: metadata.provenance",
    "lifecycle: active",
    "---",
    "",
    "## Surface",
    "",
    "surface:",
    "  mount: dock lateral",
    "  screens: [/agents, /knowledge]",
    "",
    "## Targets",
    "",
    "targets:",
    "  - flow: flows/agent",
    "    writes: [description, instructions]",
    "  - flow: flows/knowledge",
    "    writes: [description]",
    "",
    "## Policy",
    "",
    "Herda hitl.md.",
  ];
  const upd = CUES.Atualizacao;
  const panelIn = MOTION.fade(s - 0.4, 0.8)(T);
  const v2 = T > upd + 1.8;
  return (
    <div style={{
      position: "absolute", top: 0, right: 0, bottom: 0, width: 560,
      background: C.dark, color: C.darkInk, borderRadius: 8, overflow: "hidden",
      display: "flex", flexDirection: "column", opacity: panelIn,
    }}>
      <div style={{ padding: "14px 18px", borderBottom: "1px solid oklch(0.302 0.012 262)", display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "oklch(0.726 0.014 258)" }}>bundle okf</span>
        <span style={{ marginLeft: "auto", fontFamily: MONO, fontSize: 15, color: "oklch(0.612 0.014 258)" }}>
          copilots/atendimento-rh/index.md{v2 ? " · v2" : ""}
        </span>
      </div>
      <div style={{ flex: 1, minHeight: 0, padding: 18, fontFamily: MONO, fontSize: 16, lineHeight: 1.62, whiteSpace: "pre" }}>
        {base.map((l, i) => {
          const at = s + 0.25 + i * 0.16;
          const isTarget = l.indexOf("writes: [description]") > -1;
          const shown = isTarget && v2 ? "    writes: [description, instructions]" : l;
          const hl = isTarget && v2;
          return (
            <div key={i} style={{
              opacity: MOTION.fade(at, 0.3)(T),
              background: hl ? "oklch(0.302 0.052 262)" : "transparent",
              color: hl ? "#fff" : undefined,
            }}>{shown || " "}</div>
          );
        })}
        <div style={{ opacity: MOTION.fade(upd + 4.0, 0.4)(T), marginTop: 14, color: "oklch(0.726 0.014 258)" }}>
          {"log.md · append-only\n"}
          {"2026-08-29T14:26Z · publicado v1.\n"}
          {"2026-10-14T09:12Z · targets — + instructions em flows/knowledge (v2)."}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────── a peça

function Piece() {
  const { T, CUES, authoredTotal } = useComposition();
  const sceneNames = ["Vazio", "Builder", "Bundle", "Validar", "EmUso", "Medicao", "Atualizacao", "Fecho"];
  const labels = ["problema", "criar", "bundle", "validar", "usar", "medir", "atualizar", "fecho"];

  return (
    <div style={{ position: "absolute", inset: 0, padding: 40, display: "flex", flexDirection: "column", gap: 22 }}>
      {/* barra de topo — persiste em toda a peça */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, flex: "none" }}>
        <span style={{ width: 34, height: 34, borderRadius: 7, background: C.acc, color: "#fff", display: "grid", placeItems: "center", fontFamily: MONO, fontSize: 16, fontWeight: 700 }}>c</span>
        <div style={{ fontSize: 21, fontWeight: 650 }}>Exemplo prático — um copiloto, do zero ao v2</div>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
          {sceneNames.map((n, i) => {
            const start = CUES[n];
            const next = i + 1 < sceneNames.length ? CUES[sceneNames[i + 1]] : authoredTotal;
            const on = T >= start && T < next;
            const done = T >= next;
            return (
              <div key={n} style={{ display: "flex", alignItems: "center", gap: 7 }}>
                <span style={{ width: 9, height: 9, borderRadius: 999, background: on ? C.acc : done ? C.pass : C.ls }} />
                <span style={{ fontFamily: MONO, fontSize: 14, letterSpacing: "0.04em", textTransform: "uppercase", color: on ? C.ink : C.mut, fontWeight: on ? 700 : 400 }}>{labels[i]}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* palco */}
      <div style={{ flex: 1, minHeight: 0, position: "relative" }}>
        <div style={{ position: "absolute", top: 0, left: 0, bottom: 0, right: 600 }}>
          <Shot from={0} to={CUES.Builder}><SceneVazio T={T} CUES={CUES} /></Shot>
          <Shot from={CUES.Builder} to={CUES.Validar}><SceneBuilder T={T} CUES={CUES} /></Shot>
          <Shot from={CUES.Validar} to={CUES.EmUso}><SceneValidar T={T} CUES={CUES} /></Shot>
          <Shot from={CUES.EmUso} to={CUES.Medicao}><SceneUso T={T} CUES={CUES} /></Shot>
          <Shot from={CUES.Medicao} to={CUES.Atualizacao}><SceneMedicao T={T} CUES={CUES} /></Shot>
          <Shot from={CUES.Atualizacao} to={CUES.Fecho}><SceneUpdate T={T} CUES={CUES} /></Shot>
          <Shot from={CUES.Fecho} to={authoredTotal}>
            <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", justifyContent: "center", gap: 18 }}>
              <div style={{ fontSize: 40, fontWeight: 640, letterSpacing: "-0.02em", lineHeight: 1.15, maxWidth: "34ch" }}>
                O copiloto é um documento. A tela é um parser.
              </div>
              <div style={{ fontSize: 21, lineHeight: 1.5, color: C.mut, maxWidth: "48ch" }}>
                Criar, validar, publicar, medir e atualizar aconteceram sem um componente novo — e nada foi escrito sem gesto humano.
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 6 }}>
                <Chip tone="a">type: copilot</Chip>
                <Chip>type: usecase</Chip>
                <Chip>type: formflow</Chip>
                <Chip tone="w">type: policy</Chip>
                <Chip>type: log</Chip>
              </div>
            </div>
          </Shot>
        </div>

        <Shot from={CUES.Bundle - 0.6} to={authoredTotal}>
          <BundlePanel T={T} CUES={CUES} />
        </Shot>
      </div>

      <Captions items={[
        { at: 0, text: "O RH pede ajuda. Não há copiloto nenhum — e nenhum componente será escrito." },
        { at: CUES.Builder, text: "No builder, os campos do copiloto: quem ele é, onde monta e — o que importa — em quais campos ele escreve." },
        { at: CUES.Bundle, text: "Cada resposta vira uma linha do bundle: markdown com frontmatter, no formato OKF." },
        { at: CUES.Validar, text: "Antes de existir, ele é validado. Publicar é uma operação com gate: papel exigido e payload à vista." },
        { at: CUES.EmUso, text: "Em uso, dentro do caso de uso: ele propõe com diff e fonte; no passo humano, prepara e não atravessa." },
        { at: CUES.Medicao, text: "O desfecho de cada proposta é medido — aproveitamento e correção juntos, lidos da trilha." },
        { at: CUES.Atualizacao, text: "Seis semanas depois, um campo novo: PR, merge, v2. O log.md registra, sem reescrever nada." },
        { at: CUES.Fecho, text: "Copiloto novo, ou copiloto diferente, é documento — não release." },
      ]} />
    </div>
  );
}

function ExemploCopiloto() {
  return (
    <CompositionStage width={1600} height={900} scenes={window.OM_SCENES} playback={window.OM_PLAYBACK} bg={C.bg}>
      <Piece />
    </CompositionStage>
  );
}

window.ExemploCopiloto = ExemploCopiloto;
