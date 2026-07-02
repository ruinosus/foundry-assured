"use client";

// MermaidZoom — pan/zoom/fullscreen for the chat's Mermaid diagrams, for EVERY agent.
//
// Why this exists: CopilotKit v2 renders markdown via `streamdown`, whose mermaid viewer is
// styled entirely with Tailwind utilities the diagram needs (`min-h-[200px]`, flex layout,
// cursor-grab, …). This app has no Tailwind and CopilotKit's precompiled CSS is a partial
// build missing those, so the built-in viewer renders unstyled/broken and zoom never engages.
//
// We take over: observe the chat DOM, and for each mermaid block wrap its diagram <svg> in our
// own viewport with wheel-zoom (to cursor), drag-pan, a control bar (−/fit/+/fullscreen) and
// native fullscreen — all via explicit inline styles, robust to the missing utilities. We hide
// streamdown's own (broken) control bar and suppress its pan handlers (capture + stopPropagation).

import { useEffect, useRef } from "react";

const BLOCK = '[data-streamdown="mermaid-block"]';
const MIN = 0.2;
const MAX = 8;

type Ctl = { scale: number; x: number; y: number; svg: SVGSVGElement; apply: () => void };

// The diagram <svg> is the WIDEST svg in the block — the control-bar icons are tiny (~14px).
function diagramSvg(block: Element): SVGSVGElement | null {
  let best: SVGSVGElement | null = null;
  let bestW = 24; // ignore icon svgs
  block.querySelectorAll<SVGSVGElement>("svg").forEach((s) => {
    if (s.closest(".mz-ctrl")) return;
    const w = s.getBoundingClientRect().width || Number(s.getAttribute("width")) || 0;
    if (w >= bestW) {
      bestW = w;
      best = s;
    }
  });
  return best;
}

function hideNativeControls(block: HTMLElement) {
  // Streamdown renders two control groups (unstyled here): the top bar (download/copy/fullscreen,
  // class `justify-end`) and the pan/zoom panel (class `z-10`). Hide both — we provide our own.
  block
    .querySelectorAll<HTMLElement>(':scope [class*="justify-end"], :scope [class*="z-10"]')
    .forEach((el) => {
      if (el.closest(".mz-ctrl")) return;
      el.style.display = "none";
    });
}

export function MermaidZoom({ hostSelector = ".copilotkit-chat-host" }: { hostSelector?: string }) {
  const anchor = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const host =
      (anchor.current?.closest(hostSelector) as HTMLElement | null) ??
      (document.querySelector(hostSelector) as HTMLElement | null);
    if (!host) return;

    const styleSvg = (svg: SVGSVGElement) => {
      svg.style.transformOrigin = "0 0";
      svg.style.maxWidth = "none";
      svg.style.transition = "transform .08s ease-out";
    };

    const enhance = (block: HTMLElement) => {
      const svg = diagramSvg(block);
      if (!svg) return;

      const existing = (block as any).__mz as Ctl | undefined;
      if (existing) {
        if (existing.svg !== svg) {
          existing.svg = svg;
          styleSvg(svg);
          hideNativeControls(block);
          fit(existing, block);
        }
        return;
      }

      block.classList.add("mz-block");
      hideNativeControls(block);
      styleSvg(svg);

      const ctl: Ctl = {
        scale: 1,
        x: 0,
        y: 0,
        svg,
        apply() {
          this.svg.style.transform = `translate(${this.x}px, ${this.y}px) scale(${this.scale})`;
        },
      };
      (block as any).__mz = ctl;

      const zoomAt = (cx: number, cy: number, factor: number) => {
        const ns = Math.min(MAX, Math.max(MIN, ctl.scale * factor));
        ctl.x = cx - (cx - ctl.x) * (ns / ctl.scale);
        ctl.y = cy - (cy - ctl.y) * (ns / ctl.scale);
        ctl.scale = ns;
        ctl.apply();
      };

      const onWheel = (e: WheelEvent) => {
        e.preventDefault();
        e.stopPropagation();
        const r = block.getBoundingClientRect();
        zoomAt(e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.15 : 1 / 1.15);
      };

      let drag = false;
      let sx = 0;
      let sy = 0;
      let ox = 0;
      let oy = 0;
      const onDown = (e: PointerEvent) => {
        if ((e.target as HTMLElement).closest(".mz-ctrl")) return;
        e.stopPropagation();
        drag = true;
        sx = e.clientX;
        sy = e.clientY;
        ox = ctl.x;
        oy = ctl.y;
        block.setPointerCapture(e.pointerId);
        block.style.cursor = "grabbing";
        ctl.svg.style.transition = "none";
      };
      const onMove = (e: PointerEvent) => {
        if (!drag) return;
        ctl.x = ox + (e.clientX - sx);
        ctl.y = oy + (e.clientY - sy);
        ctl.apply();
      };
      const onUp = () => {
        drag = false;
        block.style.cursor = "grab";
        ctl.svg.style.transition = "transform .08s ease-out";
      };

      block.addEventListener("wheel", onWheel, { passive: false, capture: true });
      block.addEventListener("pointerdown", onDown, { capture: true });
      block.addEventListener("pointermove", onMove);
      block.addEventListener("pointerup", onUp);
      block.addEventListener("pointercancel", onUp);

      const bar = document.createElement("div");
      bar.className = "mz-ctrl";
      const mk = (glyph: string, title: string, fn: () => void) => {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = glyph;
        b.title = title;
        b.setAttribute("aria-label", title);
        b.addEventListener("click", (e) => {
          e.stopPropagation();
          fn();
        });
        return b;
      };
      const mid = () => {
        const r = block.getBoundingClientRect();
        return { cx: r.width / 2, cy: r.height / 2 };
      };
      bar.append(
        mk("−", "Diminuir", () => {
          const c = mid();
          zoomAt(c.cx, c.cy, 1 / 1.2);
        }),
        mk("⤢", "Ajustar", () => fit(ctl, block)),
        mk("+", "Aumentar", () => {
          const c = mid();
          zoomAt(c.cx, c.cy, 1.2);
        }),
        mk("⛶", "Tela cheia", () => {
          if (document.fullscreenElement) document.exitFullscreen();
          else block.requestFullscreen?.().then(() => fit(ctl, block)).catch(() => {});
        }),
      );
      block.appendChild(bar);

      fit(ctl, block);
      requestAnimationFrame(() => fit(ctl, block));
    };

    // Fit-to-WIDTH: show the diagram at full readable width, centered; tall diagrams then pan
    // vertically (fitting height too would shrink vertical flowcharts to nothing).
    const fit = (ctl: Ctl, block: HTMLElement) => {
      const vw = block.clientWidth || 1;
      const vh = block.clientHeight || 1;
      const r = ctl.svg.getBoundingClientRect();
      const w = (r.width || 1) / (ctl.scale || 1);
      const h = (r.height || 1) / (ctl.scale || 1);
      const s = Math.min(1, (vw - 24) / w) || 1;
      ctl.scale = s;
      ctl.x = Math.max(12, (vw - w * s) / 2);
      ctl.y = h * s < vh - 24 ? Math.max(12, (vh - h * s) / 2) : 12; // center if it fits, else top
      ctl.apply();
    };

    const scan = () => host.querySelectorAll<HTMLElement>(BLOCK).forEach(enhance);

    scan();
    const obs = new MutationObserver(scan);
    obs.observe(host, { childList: true, subtree: true });
    return () => obs.disconnect();
  }, [hostSelector]);

  return <span ref={anchor} style={{ display: "none" }} data-mz-anchor />;
}
