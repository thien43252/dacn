// Adapted from page-mascot 0.1.0 (MIT © Kamran Ahmed, https://github.com/nilbuild/page-mascot; license in
// src/assets/mascots/LICENSE): the cursor tracking and boop are kept, and a `mood` adds the looping poses the
// chat needs (thinking, writing, a happy loop for an unread reply, and a still face for small avatars).
import { type CSSProperties, useEffect, useRef, useState } from "react";

import "../styles/mascot.css";

// Every sheet in the folder, by file name; a sheet is only fetched once a mascot using it is on screen.
const SHEETS = import.meta.glob<string>("../assets/mascots/*.webp", { eager: true, query: "?url", import: "default" });
const sheet = (file: string) => SHEETS[`../assets/mascots/${file}.webp`];

/** Animals only. The first five belong to the assistant and the four core agents. */
const LABELS = {
  fox: "cáo",
  cat: "mèo",
  panda: "gấu trúc",
  penguin: "chim cánh cụt",
  owl: "cú",
  bear: "gấu",
  bunny: "thỏ",
  deer: "nai",
  frog: "ếch",
  hamster: "hamster",
  hedgehog: "nhím",
  koala: "koala",
  otter: "rái cá",
  raccoon: "gấu mèo",
  redpanda: "gấu trúc đỏ",
} as const;

export type MascotName = keyof typeof LABELS;

/** What an admin may give an extension agent; the Platform holds the same list and refuses any other. */
export const EXTENSION_MASCOTS = ["bear", "bunny", "deer", "frog", "hamster", "hedgehog", "koala", "otter", "raccoon", "redpanda"] as const;
export type ExtensionMascot = (typeof EXTENSION_MASCOTS)[number];

const ALL_DIRECTIONS = ["up-left", "up", "up-right", "left", "center", "right", "down-left", "down", "down-right"] as const;
type Direction = (typeof ALL_DIRECTIONS)[number];
const UPPER: Direction[] = ["up-left", "up", "up-right", "left", "center", "right"];

/**
 * Where a blink keeps the head as it is: the directions whose cell of `<name>-blink.webp` (made by
 * scripts/make-mascot-blink.mjs, then checked by eye) closes the eyes cleanly. Elsewhere, and for an animal with no
 * blink sheet, the blink is the expression sheet's front-facing one, so it is shown only while the head faces front.
 */
const BLINK_DIRECTIONS: Partial<Record<MascotName, readonly Direction[]>> = {
  fox: ALL_DIRECTIONS,
  owl: ALL_DIRECTIONS,
  penguin: ALL_DIRECTIONS,
  bunny: ALL_DIRECTIONS,
  hamster: ALL_DIRECTIONS,
  hedgehog: ALL_DIRECTIONS,
  bear: UPPER,
  redpanda: UPPER,
  deer: ["up", "up-right", "center", "right", "down"],
  otter: ["up", "center", "down"],
  raccoon: ["left", "center", "right"],
};

type Sheets = { directions: string; reactions: string; blink?: string; blinkDirections: readonly Direction[]; label: string };

/** Each character is two 3x3 sheets, nine head directions and nine expressions, and for some a sheet of closed eyes. */
export const MASCOTS = Object.fromEntries(
  (Object.keys(LABELS) as MascotName[]).map((name) => [
    name,
    {
      directions: sheet(`${name}-directions`),
      reactions: sheet(`${name}-reactions`),
      blink: BLINK_DIRECTIONS[name] && sheet(`${name}-blink`),
      blinkDirections: BLINK_DIRECTIONS[name] ?? [],
      label: LABELS[name],
    },
  ]),
) as Record<MascotName, Sheets>;

/** The extension animal the Platform named, or a fixed one from `key` when an older reply carries none. */
export function extensionMascot(mascot: string | null | undefined, key: string): ExtensionMascot {
  if (mascot && (EXTENSION_MASCOTS as readonly string[]).includes(mascot)) return mascot as ExtensionMascot;
  let hash = 0;
  for (const char of key) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return EXTENSION_MASCOTS[hash % EXTENSION_MASCOTS.length];
}

/** The assistant itself (launcher, panel header, Orchestrator) is the fox; each business agent has its own animal. */
export const AGENT_MASCOTS: Record<string, MascotName> = {
  orchestrator: "fox",
  project_design: "cat",
  planner: "cat",
  feasibility: "panda",
  safety: "penguin",
  progress: "owl",
};

export function mascotFor(agent: string | undefined): MascotName {
  return (agent && AGENT_MASCOTS[agent]) || "fox";
}

const DIRECTIONS = ALL_DIRECTIONS;
const REACTIONS = ["blink", "heart", "sparkle", "surprised", "wink", "bashful", "sleepy", "dizzy", "delighted"] as const;

type Reaction = (typeof REACTIONS)[number];

/**
 * Every mood but `still` blinks now and then. idle: follows the cursor. thinking: glances up from side to side (the Orchestrator deciding).
 * writing: looks down along the lines it writes (an agent replying). happy: a reply is waiting. still: a small face.
 */
export type MascotMood = "idle" | "thinking" | "writing" | "happy" | "still";

type Beat = { direction?: Direction; reaction?: Reaction; ms: number };

const SCRIPTS: Partial<Record<MascotMood, Beat[]>> = {
  thinking: [
    { direction: "up-left", ms: 900 },
    { direction: "up", ms: 350 },
    { direction: "up-right", ms: 900 },
    { direction: "up", ms: 500 },
  ],
  writing: [
    { direction: "down-left", ms: 650 },
    { direction: "down", ms: 450 },
    { direction: "down-right", ms: 650 },
    { direction: "down", ms: 400 },
  ],
  happy: [
    { reaction: "delighted", ms: 900 },
    { direction: "center", ms: 700 },
    { reaction: "heart", ms: 1100 },
    { direction: "center", ms: 2300 },
  ],
};

// Clockwise from the right, matching atan2 with y pointing down.
const CLOCKWISE: Direction[] = ["right", "down-right", "down", "down-left", "left", "up-left", "up", "up-right"];
const SECTOR = (Math.PI * 2) / CLOCKWISE.length;
const HYSTERESIS = 0.12;
const DEAD_ZONE = 70;

const PAYOFFS: Reaction[] = ["heart", "sparkle", "delighted"];
const BOOP_PAYOFF = 120;
const BOOP_END = 560;
const SQUASH_MS = 420;
const DIZZY_AFTER = 4;
const DIZZY_WINDOW = 1600;
const DIZZY_END = 1100;
// Blinks run on their own clock over every mood: eyes shut for a moment every few seconds, sometimes twice.
const BLINK_SHUT = 180;
const BLINK_GAP = 130;
const BLINK_EVERY = [1800, 4200] as const;
const DOUBLE_BLINK = 0.3;

const SQUASH: Keyframe[] = [
  { transform: "scale(1, 1)", easing: "ease-in" },
  { transform: "scale(1.10, 0.86)", offset: 0.18, easing: "ease-out" },
  { transform: "scale(0.95, 1.08)", offset: 0.45, easing: "ease-in-out" },
  { transform: "scale(1.03, 0.97)", offset: 0.72, easing: "ease-in-out" },
  { transform: "scale(1, 1)" },
];

// background-size 300% makes each cell a clean 0/50/100% step on both axes.
function cell(index: number): CSSProperties {
  return { backgroundPosition: `${(index % 3) * 50}% ${Math.floor(index / 3) * 50}%` };
}

function wrap(angle: number) {
  return Math.atan2(Math.sin(angle), Math.cos(angle));
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

/** The pose a mood starts in, so the server render and a reduced-motion page show the right face without timers. */
function restingDirection(mood: MascotMood): Direction {
  if (mood === "thinking") return "up-right";
  if (mood === "writing") return "down";
  return "center";
}

export type MascotProps = {
  character: MascotName;
  mood?: MascotMood;
  /** Px; omit to size it from CSS. */
  size?: number;
  /** A button the reader can boop; otherwise a decorative span hidden from assistive technology. */
  interactive?: boolean;
  /** Follow the cursor while idle. Defaults to on for interactive mascots. */
  track?: boolean;
  className?: string;
};

export function Mascot({ character, mood = "idle", size, interactive = false, track = interactive, className }: MascotProps) {
  const { directions, reactions, blink, blinkDirections, label } = MASCOTS[character];
  const rootRef = useRef<HTMLElement | null>(null);
  const squashRef = useRef<HTMLSpanElement>(null);
  const boopTimers = useRef<number[]>([]);
  const boops = useRef({ count: 0, at: 0 });
  const [direction, setDirection] = useState<Direction>(() => restingDirection(mood));
  const [beat, setBeat] = useState<Reaction | null>(null);
  const [blinking, setBlinking] = useState(false);
  const [boopFace, setBoopFace] = useState<Reaction | null>(null);

  // Scripted moods loop their beats (where to look, which face to make).
  useEffect(() => {
    setBeat(null);
    setDirection(restingDirection(mood));
    const script = SCRIPTS[mood];
    if (!script || prefersReducedMotion()) return;
    let timer = 0;
    let index = 0;
    const step = () => {
      const next = script[index % script.length];
      index += 1;
      setBeat(next.reaction ?? null);
      if (next.direction) setDirection(next.direction);
      timer = window.setTimeout(step, next.ms);
    };
    step();
    return () => window.clearTimeout(timer);
  }, [mood]);

  // Blinking: at uneven intervals so it never looks metronomic, now and then a quick double blink.
  const blinks = mood !== "still";
  useEffect(() => {
    setBlinking(false);
    if (!blinks || prefersReducedMotion()) return;
    let timer = 0;
    const later = (ms: number, next: () => void) => {
      timer = window.setTimeout(next, ms);
    };
    const wait = () => later(BLINK_EVERY[0] + Math.random() * (BLINK_EVERY[1] - BLINK_EVERY[0]), blink);
    const shut = (then: () => void) => {
      setBlinking(true);
      later(BLINK_SHUT, () => {
        setBlinking(false);
        then();
      });
    };
    const blink = () => shut(() => (Math.random() < DOUBLE_BLINK ? later(BLINK_GAP, () => shut(wait)) : wait()));
    wait();
    return () => window.clearTimeout(timer);
  }, [blinks]);

  useEffect(() => {
    if (!track || mood !== "idle" || !window.matchMedia?.("(hover: hover) and (pointer: fine)").matches) return;

    let sector = -1;
    let pointer: { x: number; y: number } | null = null;

    const aim = () => {
      const root = rootRef.current;
      if (!root || !pointer) return;
      const box = root.getBoundingClientRect();
      const dx = pointer.x - (box.left + box.width / 2);
      const dy = pointer.y - (box.top + box.height / 2);
      if (Math.hypot(dx, dy) < DEAD_ZONE) {
        sector = -1;
        setDirection("center");
        return;
      }
      // Hold the current sector until the pointer is well past its edge.
      const angle = Math.atan2(dy, dx);
      if (sector !== -1 && Math.abs(wrap(angle - sector * SECTOR)) < SECTOR / 2 + HYSTERESIS) return;
      sector = (Math.round(angle / SECTOR) + CLOCKWISE.length) % CLOCKWISE.length;
      setDirection(CLOCKWISE[sector]);
    };
    const onPointerMove = (event: PointerEvent) => {
      pointer = { x: event.clientX, y: event.clientY };
      aim();
    };

    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("scroll", aim, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("scroll", aim);
    };
  }, [track, mood]);

  useEffect(() => () => boopTimers.current.forEach(window.clearTimeout), []);

  const boop = () => {
    boopTimers.current.forEach(window.clearTimeout);
    boopTimers.current = [];
    const later = (ms: number, next: Reaction | null) => {
      boopTimers.current.push(window.setTimeout(() => setBoopFace(next), ms));
    };

    const now = Date.now();
    const count = boops.current;
    count.count = now - count.at < DIZZY_WINDOW ? count.count + 1 : 1;
    count.at = now;

    if (count.count >= DIZZY_AFTER) {
      count.count = 0;
      setBoopFace("dizzy");
      later(DIZZY_END, null);
    } else {
      setBoopFace("blink");
      later(BOOP_PAYOFF, PAYOFFS[(count.count - 1) % PAYOFFS.length]);
      later(BOOP_END, null);
    }

    if (prefersReducedMotion()) return;
    // Per-keyframe easing with the effect itself linear: an easing on the effect would front-load the bounce.
    squashRef.current?.animate?.(SQUASH, { duration: SQUASH_MS, easing: "linear" });
  };

  // A boop's face wins, then a scripted face; a blink shows only between them, so it never hides a heart. It closes
  // the eyes where the head looks; with no closed-eye cell for that direction it waits for the head to face front.
  const face = boopFace ?? beat;
  const lidded = !face && blinking && Boolean(blink) && blinkDirections.includes(direction);
  const reaction = face ?? (blinking && !lidded && direction === "center" ? "blink" : null);
  const body = (
    <span ref={squashRef} className="mascot__squash">
      <span className="mascot__layer" style={{ backgroundImage: `url(${directions})`, ...cell(DIRECTIONS.indexOf(direction)), opacity: reaction || lidded ? 0 : 1 }} />
      {/* Mounted with the others so a blink never waits for its sheet; a still face never blinks and skips it. */}
      {blink && blinks && <span className="mascot__layer" style={{ backgroundImage: `url(${blink})`, ...cell(DIRECTIONS.indexOf(direction)), opacity: lidded ? 1 : 0 }} />}
      {/* Always mounted so the sheet is fetched up front, never on the first blink. */}
      <span className="mascot__layer" style={{ backgroundImage: `url(${reactions})`, ...cell(REACTIONS.indexOf(reaction ?? "blink")), opacity: reaction ? 1 : 0 }} />
    </span>
  );
  const shared = {
    className: `mascot${className ? ` ${className}` : ""}`,
    "data-mascot": character,
    "data-mood": mood,
    style: size ? { width: size, height: size } : undefined,
  };

  return interactive ? (
    <button {...shared} ref={(node) => { rootRef.current = node; }} type="button" onClick={boop} aria-label={`Chạm vào ${label}`}>
      {body}
    </button>
  ) : (
    <span {...shared} ref={(node) => { rootRef.current = node; }} aria-hidden="true">
      {body}
    </span>
  );
}
