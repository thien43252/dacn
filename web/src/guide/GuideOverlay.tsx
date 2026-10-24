import gsap from "gsap";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import quill from "../assets/illustrations/derived/art-classroom-quill.webp";
import openBook from "../assets/illustrations/derived/prop-open-book.webp";
import "./guide.css";
import { findTarget, type GuideSession, isOtherSurfaceOpen } from "./useGuide";

const MOBILE_QUERY = "(max-width: 900px)";
const PAD = 4;
const GAP = 14;
const EDGE = 12;
const SPARKS = 8;
const MOTES = 10;
const BURST = 6;
const COMP_MOTES = 5;

/** Per-role companion: size (px), resting tilt, idle drift/tilt/period and flight character. */
const SPECS = {
  student: { w: 104, h: 78, rest: -4, drift: 8, tilt: 3, idle: 3.2, lean: 10, ease: "sine.inOut" },
  teacher: { w: 48, h: 111, rest: 28, drift: 6, tilt: 2.5, idle: 2.6, lean: 22, ease: "power3.inOut" },
  parent: { w: 104, h: 78, rest: -4, drift: 8, tilt: 3, idle: 3.2, lean: 10, ease: "sine.inOut" },
} as const;

interface Box { x: number; y: number; w: number; h: number }
interface Layout { halo: Box & { radius: number }; card: { x: number; y: number }; comp: { x: number; y: number }; top: boolean }

const inView = (b: Box, vw: number, vh: number) => b.x >= EDGE && b.y >= EDGE && b.x + b.w <= vw - EDGE && b.y + b.h <= vh - EDGE;
const overlaps = (a: Box, b: Box) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), Math.max(min, max));

interface GuideOverlayProps {
  session: GuideSession | null;
  pathname: string;
  onFinish: (status: "completed" | "dismissed", step: number) => void;
}

/**
 * The Book (student) / Wand (teacher) companion. Three independent decorative layers (target halo, sparkle trail,
 * companion) plus the explanation card. It only reads the page: it never clicks, navigates or submits for the user.
 */
export function GuideOverlay({ session, pathname, onFinish }: GuideOverlayProps) {
  if (!session || pathname !== session.guide.route) return null;
  // Keyed by guide so a different guide always starts from its own first step.
  return <GuideTour key={session.guide.id} session={session} onFinish={onFinish} />;
}

/** Where the card and companion go around the real target: side, then below/above, else a clamped fallback. */
function computeLayout(target: HTMLElement, card: HTMLElement, spec: { w: number; h: number }): Layout {
  const r = target.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const mobile = window.matchMedia(MOBILE_QUERY).matches;
  const T: Box = { x: r.left - PAD, y: r.top - PAD, w: r.width + PAD * 2, h: r.height + PAD * 2 };
  const radiusValue = parseFloat(getComputedStyle(target).borderTopLeftRadius) || 12;
  const radius = Math.min(radiusValue + PAD, Math.min(T.w, T.h) / 2);
  const top = mobile && T.y + T.h / 2 > vh / 2;
  const { w: cw, h: ch } = spec;
  const cy = T.y + T.h / 2;
  const halo = { ...T, radius };

  if (mobile) {
    // Bottom sheet or top sheet: use the one that covers less of the target (a tall target may leave no clear side).
    const measure = (atTop: boolean): { S: Box; area: number } => {
      card.classList.toggle("guide__card--top", atTop);
      const sheet = card.getBoundingClientRect();
      const S: Box = { x: sheet.left, y: sheet.top, w: sheet.width, h: sheet.height };
      const area = Math.max(0, Math.min(S.x + S.w, T.x + T.w) - Math.max(S.x, T.x)) * Math.max(0, Math.min(S.y + S.h, T.y + T.h) - Math.max(S.y, T.y));
      return { S, area };
    };
    const first = measure(top);
    const second = measure(!top);
    const atTop = second.area < first.area ? !top : top;
    const { S } = atTop === !top ? second : measure(top);
    card.classList.toggle("guide__card--top", atTop);
    const options: Box[] = [
      { x: T.x - GAP - cw, y: cy - ch / 2, w: cw, h: ch },
      { x: T.x + T.w + GAP, y: cy - ch / 2, w: cw, h: ch },
      { x: T.x + T.w / 2 - cw / 2, y: T.y - GAP - ch, w: cw, h: ch },
      { x: T.x + T.w / 2 - cw / 2, y: T.y + T.h + GAP, w: cw, h: ch },
    ];
    // Last resort (target fills the screen): park the companion on the free band next to the sheet, at the right edge.
    const band: Box = { x: vw - cw - EDGE, y: atTop ? S.y + S.h + GAP : S.y - GAP - ch, w: cw, h: ch };
    const pick = options.find((o) => inView(o, vw, vh) && !overlaps(o, T) && !overlaps(o, S)) ?? band;
    return { halo, card: { x: 0, y: 0 }, comp: { x: pick.x, y: clamp(pick.y, EDGE, vh - ch - EDGE) }, top: atTop };
  }

  const w = card.offsetWidth;
  const h = card.offsetHeight;
  const arrangements: { comp: Box; card: Box }[] = [];
  const rowY = (y: number) => clamp(y, EDGE, vh - h - EDGE);
  const rightComp: Box = { x: T.x + T.w + GAP, y: cy - ch / 2, w: cw, h: ch };
  arrangements.push({ comp: rightComp, card: { x: rightComp.x + cw + GAP, y: rowY(cy - h / 2), w, h } });
  const leftComp: Box = { x: T.x - GAP - cw, y: cy - ch / 2, w: cw, h: ch };
  arrangements.push({ comp: leftComp, card: { x: leftComp.x - GAP - w, y: rowY(cy - h / 2), w, h } });
  for (const [compX, cardX] of [[T.x, T.x + cw + GAP], [T.x + T.w - cw, T.x + T.w - cw - GAP - w]]) {
    arrangements.push({ comp: { x: compX, y: T.y + T.h + GAP, w: cw, h: ch }, card: { x: cardX, y: T.y + T.h + GAP, w, h } });
    arrangements.push({ comp: { x: compX, y: T.y - GAP - ch, w: cw, h: ch }, card: { x: cardX, y: T.y - GAP - h, w, h } });
  }
  const fit = arrangements.find(({ comp, card: c }) =>
    inView(comp, vw, vh) && inView(c, vw, vh) && !overlaps(comp, T) && !overlaps(c, T) && !overlaps(comp, c));
  if (fit) return { halo, card: { x: fit.card.x, y: fit.card.y }, comp: { x: fit.comp.x, y: fit.comp.y }, top };
  // A target too large to sit beside: dock the pair at the bottom edge, still clamped inside the viewport.
  const cardX = clamp(vw - EDGE - w, EDGE, vw - w - EDGE);
  const cardY = clamp(vh - EDGE - h, EDGE, vh - h - EDGE);
  return { halo, card: { x: cardX, y: cardY }, comp: { x: clamp(cardX - GAP - cw, EDGE, vw - cw - EDGE), y: clamp(cardY + h - ch, EDGE, vh - ch - EDGE) }, top };
}

/** Small light motes that rise from around a box and fade: random size, brightness and drift, restarted forever. */
function driftMotes(
  container: HTMLElement,
  box: () => { w: number; h: number },
  out: number,
  rise: number,
  guard: { alive: boolean },
  bag: Set<gsap.core.Timeline>,
) {
  Array.from(container.children).forEach((el) => {
    const launch = () => {
      if (!guard.alive) return;
      const { w, h } = box();
      let d = Math.random() * 2 * (w + h);
      const o = Math.random() * out;
      let x: number;
      let y: number;
      if (d < w) { x = d; y = -o; }
      else if ((d -= w) < h) { x = w + o; y = d; }
      else if ((d -= h) < w) { x = d; y = h + o; }
      else { d -= w; x = -o; y = d; }
      const size = 3 + Math.random() * 4;
      const dur = 2.6 + Math.random() * 2;
      const peak = 0.5 + Math.random() * 0.5;
      const t: gsap.core.Timeline = gsap.timeline({ delay: Math.random() * 0.9, onComplete: () => { bag.delete(t); launch(); } });
      bag.add(t);
      if (document.hidden) t.pause();
      t.set(el, { width: size, height: size, x, y, opacity: 0, scale: 0.5 })
        .to(el, { opacity: peak, scale: 1, duration: dur * 0.3, ease: "sine.out" }, 0)
        .to(el, { x: x + (Math.random() - 0.5) * 16, y: y - rise * (0.5 + Math.random() * 0.7), duration: dur, ease: "sine.inOut" }, 0)
        .to(el, { opacity: 0, scale: 0.3, duration: dur * 0.5, ease: "sine.in" }, dur * 0.5);
    };
    launch();
  });
}

/** preparing -> travelling -> revealing -> presenting -> dismissing; only `presenting` accepts navigation. */
type Phase = "preparing" | "travelling" | "revealing" | "presenting" | "dismissing";

function GuideTour({ session, onFinish }: { session: GuideSession; onFinish: GuideOverlayProps["onFinish"] }) {
  const { steps, role } = session;
  const spec = SPECS[role];
  const isWand = role === "teacher";
  // `shown` is the step whose content is in the card. It only changes while the card is hidden, so the card never
  // shows the old step's text with the new step's buttons (or the reverse).
  const [shown, setShown] = useState(0);
  const [paused, setPaused] = useState(false);
  const [phase, setPhaseState] = useState<Phase>("preparing");
  const phaseRef = useRef<Phase>("preparing");
  const direction = useRef<1 | -1>(1);
  const cardRef = useRef<HTMLDivElement>(null);
  const haloRef = useRef<HTMLDivElement>(null);
  const fxRef = useRef<HTMLDivElement>(null);
  const glowRef = useRef<HTMLDivElement>(null);
  const motesRef = useRef<HTMLDivElement>(null);
  const burstRef = useRef<HTMLDivElement>(null);
  const echoRef = useRef<HTMLImageElement>(null);
  const compMotesRef = useRef<HTMLDivElement>(null);
  const compRef = useRef<HTMLDivElement>(null);
  const artRef = useRef<HTMLDivElement>(null);
  const sparksRef = useRef<HTMLDivElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);
  const motion = useRef<{
    tl: gsap.core.Timeline | null;
    idle: gsap.core.Tween | null;
    extra: gsap.core.Animation[];
    motes: Set<gsap.core.Timeline>;
    guard: { alive: boolean } | null;
  }>({ tl: null, idle: null, extra: [], motes: new Set(), guard: null });
  const entered = useRef(false);
  const step = steps[shown];
  const last = shown === steps.length - 1;

  const setPhase = (next: Phase) => {
    phaseRef.current = next;
    setPhaseState(next);
  };

  // Focus goes back to where it was when the tour ends. The card is hidden until the guide arrives, so nothing
  // inside it is focused on mount.
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const card = cardRef.current;
    return () => {
      if (card) gsap.killTweensOf(card);
      previous?.focus?.();
    };
  }, []);

  // Find the next step whose target exists, in the given direction; -1 when none is left.
  function nextAvailable(from: number, dir: 1 | -1): number {
    for (let i = from + dir; i >= 0 && i < steps.length; i += dir) {
      if (findTarget(steps[i].target)) return i;
    }
    return -1;
  }

  // Next / Back: fade the card out where it is, then (hidden) swap its content and send the guide on.
  function go(dir: 1 | -1) {
    if (phaseRef.current !== "presenting") return;
    if (dir === 1 && last) return onFinish("completed", shown);
    if (dir === -1 && shown === 0) return;
    const target = nextAvailable(shown, dir);
    if (target < 0) {
      if (dir === 1) onFinish("completed", steps.length - 1);
      return;
    }
    direction.current = dir;
    setPhase("dismissing");
    const card = cardRef.current;
    const fx = fxRef.current;
    if (fx) gsap.to(fx, { opacity: 0, duration: 0.15, ease: "power1.out", overwrite: true });
    if (!card) return setShown(target);
    gsap.to(card, { autoAlpha: 0, duration: 0.15, ease: "power1.out", overwrite: true, onComplete: () => setShown(target) });
  }

  // Other dialogs (account menu, confirm) and the open assistant take priority: hide until they close.
  useEffect(() => {
    const timer = window.setInterval(() => setPaused(isOtherSurfaceOpen()), 300);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (paused) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onFinish("dismissed", shown);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [paused, shown, onFinish]);

  // Decorative idle effects stop while the tab is hidden.
  useEffect(() => {
    const sync = () => {
      const hidden = document.hidden;
      motion.current.idle?.paused(hidden);
      motion.current.extra.forEach((animation) => animation.paused(hidden));
      motion.current.motes.forEach((timeline) => timeline.paused(hidden));
    };
    document.addEventListener("visibilitychange", sync);
    return () => document.removeEventListener("visibilitychange", sync);
  }, []);

  // One run per shown step: the card is hidden and already holds this step's content when it starts.
  useLayoutEffect(() => {
    if (paused) return;
    const target = findTarget(step.target);
    if (!target) {
      // Fallback: skip to the next step that exists (never a blank card, never waiting forever).
      const i = nextAvailable(shown, direction.current);
      if (i >= 0) setShown(i);
      else onFinish("completed", Math.max(0, shown - 1));
      return;
    }
    const card = cardRef.current;
    const halo = haloRef.current;
    const fx = fxRef.current;
    const glow = glowRef.current;
    const motes = motesRef.current;
    const burst = burstRef.current;
    const echo = echoRef.current;
    const compMotes = compMotesRef.current;
    const comp = compRef.current;
    const art = artRef.current;
    const sparks = sparksRef.current;
    if (!card || !halo || !fx || !glow || !motes || !burst || !echo || !compMotes || !comp || !art || !sparks) return;
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const mobile = () => window.matchMedia(MOBILE_QUERY).matches;

    // Reveal an off-screen target once, instantly, then measure its final position. Later scrolling is the user's.
    const r0 = target.getBoundingClientRect();
    if (r0.top < 0 || r0.bottom > window.innerHeight || r0.left < 0 || r0.right > window.innerWidth) {
      target.scrollIntoView({ block: "center", inline: "nearest", behavior: "auto" });
    }

    const stopMotion = () => {
      const m = motion.current;
      m.tl?.kill();
      m.idle?.kill();
      m.extra.forEach((animation) => animation.kill());
      m.motes.forEach((timeline) => timeline.kill());
      if (m.guard) m.guard.alive = false;
      motion.current = { tl: null, idle: null, extra: [], motes: new Set(), guard: null };
      gsap.killTweensOf([halo, fx, comp, art, glow, echo, card, ...Array.from(sparks.children), ...Array.from(motes.children), ...Array.from(burst.children), ...Array.from(compMotes.children)]);
      gsap.set([sparks.children, motes.children, burst.children, compMotes.children], { opacity: 0 });
    };
    const haloBox = { w: 0, h: 0 };
    const placeHalo = (l: Layout) => {
      haloBox.w = l.halo.w;
      haloBox.h = l.halo.h;
      gsap.set(halo, { x: l.halo.x, y: l.halo.y, width: l.halo.w, height: l.halo.h, borderRadius: l.halo.radius });
    };
    const placeCard = (l: Layout) => { if (!mobile()) gsap.set(card, { x: l.card.x, y: l.card.y }); };
    // Position-only refresh (scroll, resize while presenting): no phase change, no animation restart.
    const place = () => {
      const l = computeLayout(target, card, spec);
      placeHalo(l);
      placeCard(l);
      gsap.set(comp, { x: l.comp.x, y: l.comp.y });
      return l;
    };

    // The target and the companion both glow from the moment the guide settles: slow breathing plus light motes.
    const startBreath = () => {
      if (calm) { gsap.set(glow, { opacity: 0.9 }); gsap.set(echo, { opacity: 0.6 }); return; }
      const guard = { alive: true };
      motion.current.guard = guard;
      const breathe = [
        gsap.fromTo(glow, { opacity: 1 }, { opacity: 0.68, duration: 3.4, ease: "sine.inOut", yoyo: true, repeat: -1 }),
        gsap.fromTo(echo, { opacity: 0.85 }, { opacity: 0.45, duration: 3, ease: "sine.inOut", yoyo: true, repeat: -1 }),
      ];
      breathe.forEach((animation) => animation.paused(document.hidden));
      motion.current.extra.push(...breathe);
      driftMotes(motes, () => haloBox, 6, 30, guard, motion.current.motes);
      driftMotes(compMotes, () => ({ w: spec.w, h: spec.h }), 10, 26, guard, motion.current.motes);
    };
    // Hover or keyboard focus on the target: a little brighter, plus one short sparkle burst.
    let lastBurst = 0;
    const heat = (on: boolean) => {
      halo.classList.toggle("guide__halo--hot", on);
      if (!on || calm || performance.now() - lastBurst < 1200) return;
      lastBurst = performance.now();
      Array.from(burst.children).forEach((el, i) => {
        const angle = (i / BURST) * Math.PI * 2 + Math.random() * 0.6;
        const x = haloBox.w / 2 + Math.cos(angle) * (haloBox.w / 2);
        const y = haloBox.h / 2 + Math.sin(angle) * (haloBox.h / 2);
        gsap.fromTo(el, { x, y, width: 4 + Math.random() * 3, height: 4 + Math.random() * 3, opacity: 0.95, scale: 1 },
          { x: x + Math.cos(angle) * 26, y: y + Math.sin(angle) * 26, opacity: 0, scale: 0.3, duration: 0.7, ease: "power2.out", overwrite: true });
      });
      gsap.fromTo(glow, { scale: 1 }, { scale: 1.03, duration: 0.25, ease: "sine.out", yoyo: true, repeat: 1, overwrite: "auto" });
    };
    const onEnter = () => heat(true);
    const onLeave = () => heat(false);
    target.addEventListener("pointerenter", onEnter);
    target.addEventListener("pointerleave", onLeave);
    target.addEventListener("focusin", onEnter);
    target.addEventListener("focusout", onLeave);

    const startIdle = () => {
      if (calm) return;
      motion.current.idle = gsap.to(art, { y: -spec.drift, rotation: spec.rest + spec.tilt, duration: spec.idle, ease: "sine.inOut", yoyo: true, repeat: -1 });
      motion.current.idle.paused(document.hidden);
    };
    const present = () => {
      card.style.pointerEvents = "";
      setPhase("presenting");
      nextRef.current?.focus({ preventScroll: true });
    };

    // arrival -> flight -> settle -> (pause) -> reveal card -> idle. The card stays fully hidden until the guide has
    // arrived; it is positioned from the target and never moves with the guide.
    const travel = () => {
      stopMotion();
      gsap.set(card, { autoAlpha: 0 });
      setPhase("preparing");
      const l = computeLayout(target, card, spec);
      placeCard(l);
      const first = !entered.current;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      let from = { x: Number(gsap.getProperty(comp, "x")), y: Number(gsap.getProperty(comp, "y")) };
      const startRot = first ? spec.rest : Number(gsap.getProperty(art, "rotation"));
      if (first) {
        // Enter from the viewport edge nearest the target.
        const dist = { left: l.comp.x, right: vw - l.comp.x, top: l.comp.y, bottom: vh - l.comp.y };
        const edge = (Object.keys(dist) as (keyof typeof dist)[]).reduce((a, b) => (dist[a] <= dist[b] ? a : b));
        from = edge === "left" ? { x: -spec.w - 40, y: l.comp.y }
          : edge === "right" ? { x: vw + 40, y: l.comp.y }
          : edge === "top" ? { x: l.comp.x, y: -spec.h - 40 }
          : { x: l.comp.x, y: vh + 40 };
        gsap.set(comp, { x: from.x, y: from.y, opacity: 0 });
        gsap.set(art, { rotation: spec.rest, y: 0, scale: 0.85 });
        gsap.set([halo, fx], { opacity: 0 });
        placeHalo(l);
      }
      const dx = l.comp.x - from.x;
      const dy = l.comp.y - from.y;
      const distance = Math.hypot(dx, dy);
      const duration = clamp(0.6 + distance / 1500, 0.6, 1.1);
      const bend = distance * 0.22 * (shown % 2 === 0 ? 1 : -1);
      const ctrl = {
        x: clamp((from.x + l.comp.x) / 2 + (-dy / (distance || 1)) * bend, -spec.w, vw),
        y: clamp((from.y + l.comp.y) / 2 + (dx / (distance || 1)) * bend, -spec.h, vh),
      };
      const lean = clamp((dx / (distance || 1)) * spec.lean, -spec.lean, spec.lean);
      const proxy = { t: 0 };
      let lastSpark = 0;
      let spark = 0;

      const tl = gsap.timeline();
      motion.current.tl = tl;
      entered.current = true;
      tl.set(fx, { opacity: 0 });
      tl.addLabel("arrival");
      tl.call(() => setPhase("travelling"), undefined, "arrival");
      tl.to(comp, { opacity: 1, duration: 0.25, ease: "power1.out" }, "arrival");
      tl.to(art, { scale: 1, duration: 0.4, ease: "power2.out" }, "arrival");
      tl.to(halo, { opacity: 1, duration: 0.4, ease: "power1.out" }, "arrival");
      if (!first) {
        // The dim "hole" glides to the new target while the guide flies.
        tl.to(halo, { x: l.halo.x, y: l.halo.y, width: l.halo.w, height: l.halo.h, borderRadius: l.halo.radius, duration: 0.5, ease: "power3.inOut" }, "arrival");
        tl.call(() => { haloBox.w = l.halo.w; haloBox.h = l.halo.h; }, undefined, "arrival");
      }
      tl.addLabel("flight", "arrival+=0.08");
      tl.to(proxy, {
        t: 1,
        duration,
        ease: spec.ease,
        onUpdate: () => {
          const t = proxy.t;
          const u = 1 - t;
          gsap.set(comp, { x: u * u * from.x + 2 * u * t * ctrl.x + t * t * l.comp.x, y: u * u * from.y + 2 * u * t * ctrl.y + t * t * l.comp.y });
          gsap.set(art, { rotation: startRot + (spec.rest - startRot) * t + lean * Math.sin(Math.PI * t) });
          const now = performance.now();
          if (now - lastSpark > 55 && t < 0.96) {
            lastSpark = now;
            const dot = sparks.children[spark++ % SPARKS];
            const cx = Number(gsap.getProperty(comp, "x")) + spec.w / 2 + (Math.random() - 0.5) * 14;
            const cy = Number(gsap.getProperty(comp, "y")) + spec.h / 2 + (Math.random() - 0.5) * 14;
            gsap.fromTo(dot, { x: cx, y: cy, opacity: 0.9, scale: 1 }, { y: cy + 12, opacity: 0, scale: 0.3, duration: 0.5, ease: "power1.out", overwrite: true });
          }
        },
      }, "flight");
      tl.addLabel("settle");
      tl.fromTo(art, { scale: isWand ? 1.06 : 1.04 }, { scale: 1, duration: 0.4, ease: "power2.out" }, "settle-=0.05");
      tl.fromTo(fx, { opacity: 0 }, { opacity: 1, duration: 0.45, ease: "power1.out" }, "settle-=0.1");
      tl.fromTo(glow, { scale: 0.97 }, { scale: 1, duration: 0.6, ease: "power2.out" }, "settle-=0.1");
      tl.call(() => { startBreath(); startIdle(); }, undefined, "settle");
      // Guide has arrived: give it a beat, re-measure, then fade the finished card in with a small rise.
      tl.addLabel("reveal", "settle+=0.2");
      tl.call(() => {
        setPhase("revealing");
        const fresh = place();
        // Killed with everything else on `card` by stopMotion, so a closed or restarted tour can never fade it in.
        if (!mobile()) gsap.fromTo(card, { y: fresh.card.y + 6 }, { y: fresh.card.y, duration: 0.22, ease: "power2.out" });
        gsap.to(card, { autoAlpha: 1, duration: 0.22, ease: "power2.out", onComplete: present });
      }, undefined, "reveal");
    };

    // Reduced motion: no long flight; place everything and fade the card in quickly.
    const direct = () => {
      stopMotion();
      gsap.set(card, { autoAlpha: 0 });
      setPhase("preparing");
      const l = place();
      gsap.set(comp, { opacity: 1 });
      gsap.set(art, { rotation: spec.rest, y: 0, scale: 1 });
      gsap.set([halo, fx], { opacity: 1 });
      startBreath();
      entered.current = true;
      const tl = gsap.timeline();
      motion.current.tl = tl;
      tl.call(() => setPhase("revealing"), undefined, 0.05);
      tl.to(card, { autoAlpha: 1, duration: 0.12, ease: "none" }, 0.05);
      tl.call(present, undefined, ">");
      void l;
    };

    if (calm) direct();
    else travel();

    let frame = 0;
    const onResize = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (phaseRef.current === "presenting") place();
        else if (calm) direct();
        else travel();
      });
    };
    // Scroll only re-anchors a presenting guide; mid-transition the reveal step re-measures anyway.
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (phaseRef.current === "presenting") place();
      });
    };
    window.addEventListener("resize", onResize);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("scroll", onScroll, true);
      target.removeEventListener("pointerenter", onEnter);
      target.removeEventListener("pointerleave", onLeave);
      target.removeEventListener("focusin", onEnter);
      target.removeEventListener("focusout", onLeave);
      halo.classList.remove("guide__halo--hot");
      stopMotion();
    };
    // nextAvailable/present only read props and refs that are stable for this tour.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shown, paused]);

  function onCardKey(event: React.KeyboardEvent) {
    if (event.key === "ArrowRight") { event.preventDefault(); go(1); }
    if (event.key === "ArrowLeft") { event.preventDefault(); go(-1); }
  }

  const cardLive = phase === "presenting";
  const escapeOn = phase === "preparing" || phase === "travelling" || phase === "dismissing";

  // Rendered on <body>, outside the app shell, so no shell ancestor (overflow, filter, stacking order) can dim or clip it.
  return createPortal(
    <div className="guide" data-role={role} data-phase={phase} hidden={paused}>
      <div ref={haloRef} className="guide__halo" aria-hidden="true">
        <div ref={fxRef} className="guide__fx">
          <div ref={glowRef} className="guide__glow" />
          <div ref={motesRef} className="guide__motes">{Array.from({ length: MOTES }, (_, i) => <i key={i} />)}</div>
          <div ref={burstRef} className="guide__motes">{Array.from({ length: BURST }, (_, i) => <i key={i} />)}</div>
        </div>
      </div>
      <div ref={sparksRef} className="guide__sparks" aria-hidden="true">
        {Array.from({ length: SPARKS }, (_, i) => <i key={i} />)}
      </div>
      <div ref={compRef} className="guide__companion" style={{ width: spec.w, height: spec.h }} aria-hidden="true">
        <div ref={artRef} className="guide__art">
          <img ref={echoRef} className="guide__echo" src={isWand ? quill : openBook} width={isWand ? 156 : 319} height={isWand ? 360 : 240} alt="" />
          {isWand
            ? <img className="guide__wand" src={quill} width={156} height={360} alt="" />
            : <img className="guide__book" src={openBook} width={319} height={240} alt="" />}
        </div>
        <div ref={compMotesRef} className="guide__motes">{Array.from({ length: COMP_MOTES }, (_, i) => <i key={i} />)}</div>
      </div>
      {/* While the guide travels the card is gone; this small fixed control is the only way out besides Escape. */}
      <button
        className={`guide__escape ${escapeOn ? "is-on" : ""}`}
        type="button"
        onClick={() => onFinish("dismissed", shown)}
        inert={!escapeOn}
        aria-label="Đóng hướng dẫn"
      >
        <svg viewBox="0 0 20 20" width="14" height="14" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
        Đóng
      </button>
      <div
        ref={cardRef}
        className="guide__card"
        role="dialog"
        aria-modal="false"
        aria-labelledby="guide-title"
        aria-hidden={!cardLive}
        data-guide-card=""
        inert={!cardLive}
        onKeyDown={onCardKey}
      >
        <button className="guide__close" type="button" onClick={() => onFinish("dismissed", shown)} aria-label="Đóng hướng dẫn">
          <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
        </button>
        <div className="guide__copy">
          <h2 id="guide-title" className="guide__title">{step.title}</h2>
          <p className="guide__text" aria-live="polite">{step.text}</p>
          {step.bullets && step.bullets.length > 0 && (
            <ul className="guide__list">{step.bullets.map((line) => <li key={line}>{line}</li>)}</ul>
          )}
          <p className="guide__meta">Bước {shown + 1}/{steps.length}</p>
        </div>
        <div className="guide__actions">
          <button className="guide__skip" type="button" onClick={() => onFinish("dismissed", shown)}>Bỏ qua</button>
          <span className="guide__nav">
            {shown > 0 && <button className="button button--secondary guide__btn" type="button" onClick={() => go(-1)}>Quay lại</button>}
            <button ref={nextRef} className="button button--primary guide__btn" type="button" onClick={() => go(1)}>{last ? "Hoàn tất" : "Tiếp"}</button>
          </span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
