import gsap from "gsap";
import { type CSSProperties, type ReactNode, useEffect, useLayoutEffect, useRef } from "react";

/**
 * One shared GSAP treatment for artwork (UI_SPEC §4b). It animates the whole asset only, never a redrawn part.
 *
 * Entrance (outer wrapper, plays once per `id` per page load, when the art first scrolls into view):
 * - `hero`   large grounded art: 0.9s rise + fade
 * - `scene`  flattened scene crop: 0.9s slide-in from the right
 * - `accent` small prop/motif: 0.7s pop with a slight tilt
 * - `empty`  onboarding / empty-state art: 0.7s rise
 *
 * Loop (inner wrapper, so it never fights the entrance or the artwork's own CSS transform); runs only while the art is
 * on screen and the tab is visible, and never under `prefers-reduced-motion`:
 * - `float` independent floating prop: 12px lift with a ±3° tilt over 4.5s
 * - `drift` scene-level: 14px slide and 3.5% push-in over 7s (parent clips it)
 */
export type ArtworkVariant = "hero" | "scene" | "accent" | "empty";
export type ArtworkLoop = "float" | "drift";

const ENTRANCE: Record<ArtworkVariant, { from: gsap.TweenVars; duration: number }> = {
  hero: { from: { autoAlpha: 0, y: 28, scale: 0.97 }, duration: 0.9 },
  scene: { from: { autoAlpha: 0, x: 48 }, duration: 0.9 },
  accent: { from: { autoAlpha: 0, y: 16, rotation: -3, scale: 0.92 }, duration: 0.7 },
  empty: { from: { autoAlpha: 0, y: 18 }, duration: 0.7 },
};

const played = new Set<string>();

// Layout effect on the client so the hidden start state is set before first paint.
const useIsoLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

interface ArtworkMotionProps {
  /** Stable key; the entrance plays once per id. */
  id: string;
  variant: ArtworkVariant;
  loop?: ArtworkLoop;
  /** Seconds before the entrance and the loop start (stagger independent props). */
  delay?: number;
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
}

export function ArtworkMotion({ id, variant, loop, delay = 0, className, style, children }: ArtworkMotionProps) {
  const outer = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);

  useIsoLayoutEffect(() => {
    const target = outer.current;
    const mover = inner.current;
    if (!target || !mover) return;
    const media = gsap.matchMedia();

    media.add("(prefers-reduced-motion: no-preference)", () => {
      let onScreen = false;
      let tabVisible = !document.hidden;
      const tween = !loop ? null : loop === "float"
        ? gsap.fromTo(mover, { y: 0, rotation: -3 }, { y: -12, rotation: 3, duration: 4.5, ease: "sine.inOut", yoyo: true, repeat: -1, paused: true, delay })
        : gsap.fromTo(mover, { x: 0, scale: 1 }, { x: -14, scale: 1.035, duration: 7, ease: "sine.inOut", yoyo: true, repeat: -1, paused: true, transformOrigin: "100% 50%" });
      const syncLoop = () => {
        if (!tween) return;
        if (onScreen && tabVisible) tween.resume();
        else tween.pause();
      };

      const { from, duration } = ENTRANCE[variant];
      if (!played.has(id)) gsap.set(target, from);

      const observer = new IntersectionObserver(([entry]) => {
        onScreen = entry.isIntersecting;
        if (onScreen && !played.has(id)) {
          gsap.to(target, {
            autoAlpha: 1, x: 0, y: 0, scale: 1, rotation: 0, duration, delay, ease: "power3.out",
            onStart: () => played.add(id),
            onComplete: () => { gsap.set(target, { clearProps: "transform,opacity,visibility" }); },
          });
        }
        syncLoop();
      }, { threshold: 0.1 });
      observer.observe(target);

      const onVisibility = () => { tabVisible = !document.hidden; syncLoop(); };
      document.addEventListener("visibilitychange", onVisibility);

      return () => {
        observer.disconnect();
        document.removeEventListener("visibilitychange", onVisibility);
      };
    });

    return () => media.revert();
  }, [id, variant, loop, delay]);

  return (
    <div ref={outer} className={className ? `artwork-motion ${className}` : "artwork-motion"} style={style}>
      <div ref={inner} className="artwork-motion__inner">{children}</div>
    </div>
  );
}
