import { useEffect, useRef, useState, type CSSProperties, type PointerEvent } from "react";

export interface ControllerOption {
  id: string;
  label: string;
  targetId: string;
}

interface GlassControllerProps {
  options: ControllerOption[];
}

type ControllerPhase = "idle" | "collapsing" | "collapsed" | "expanding";

export function GlassController({ options }: GlassControllerProps) {
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [phase, setPhase] = useState<ControllerPhase>("idle");
  const [status, setStatus] = useState("Chọn một giai đoạn để khám phá");
  const timerRef = useRef<number | null>(null);
  const buttonRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => () => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
  }, []);

  const activeIndex = selectedIndex ?? highlightedIndex;
  const capsuleLeft = activeIndex === 0 ? "-5px" : `${activeIndex * 20}%`;
  const capsuleWidth = activeIndex === 0 || activeIndex === 4 ? "calc(20% + 5px)" : "20%";
  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  const duration = reducedMotion ? 1 : 980;

  function choose(index: number) {
    if (phase !== "idle" || selectedIndex !== null) return;
    const option = options[index - 1];
    setSelectedIndex(index);
    setPhase("collapsing");
    setStatus(`Đang mở giai đoạn ${option.label}`);
    document.getElementById(option.targetId)?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });

    timerRef.current = window.setTimeout(() => {
      setPhase("collapsed");
      setStatus(`Đang xem giai đoạn ${option.label}. Chọn Đặt lại để mở các lựa chọn.`);
      buttonRefs.current[index - 1]?.focus({ preventScroll: true });
    }, duration);
  }

  function reset(index: number) {
    if (phase !== "collapsed" || selectedIndex !== index) return;
    setPhase("expanding");
    setStatus("Đang mở lại bộ điều khiển");
    timerRef.current = window.setTimeout(() => {
      setSelectedIndex(null);
      setHighlightedIndex(index);
      setPhase("idle");
      setStatus("Đã mở lại các lựa chọn");
      buttonRefs.current[index - 1]?.focus({ preventScroll: true });
    }, duration);
  }

  function updatePointer(event: PointerEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = Math.max(0, Math.min(100, ((event.clientX - rect.left) / rect.width) * 100));
    const y = Math.max(0, Math.min(100, ((event.clientY - rect.top) / rect.height) * 100));
    event.currentTarget.style.setProperty("--controller-glass-x", `${x}%`);
    event.currentTarget.style.setProperty("--controller-glass-y", `${y}%`);
  }

  const isCompact = phase === "collapsing" || phase === "collapsed";
  const style = {
    "--controller-cap-left": isCompact ? "calc(50% - 100px)" : capsuleLeft,
    "--controller-cap-width": isCompact ? "200px" : capsuleWidth,
  } as CSSProperties;

  return (
    <div
      className={`glass-controller glass-controller--${phase} ${highlightedIndex > 0 ? "is-highlighted" : ""}`}
      style={style}
      role="group"
      aria-label="Chọn giai đoạn bước"
      onPointerMove={updatePointer}
      onPointerLeave={() => {
        if (phase === "idle" && !document.activeElement?.closest(".glass-controller")) setHighlightedIndex(0);
      }}
    >
      <div className="glass-controller__track glass-controller__glass" aria-hidden="true" />
      <div className="glass-controller__capsule glass-controller__glass" aria-hidden="true" />
      <div className="glass-controller__cells">
        <div className="glass-controller__cell glass-controller__prompt">Chọn chặng</div>
        {options.map((option, optionIndex) => {
          const index = optionIndex + 1;
          const chosen = selectedIndex === index;
          return (
            <button
              className={`glass-controller__cell ${chosen ? "is-chosen" : ""}`}
              key={option.id}
              ref={(element) => { buttonRefs.current[optionIndex] = element; }}
              type="button"
              style={{ "--controller-travel": `${(2 - index) * 100}%` } as CSSProperties}
              disabled={phase !== "idle" && !chosen}
              aria-hidden={phase !== "idle" && !chosen}
              aria-pressed={chosen}
              tabIndex={phase !== "idle" && !chosen ? -1 : 0}
              onMouseEnter={() => { if (phase === "idle") setHighlightedIndex(index); }}
              onMouseLeave={() => { if (phase === "idle") setHighlightedIndex(0); }}
              onFocus={() => { if (phase === "idle") setHighlightedIndex(index); }}
              onBlur={() => { if (phase === "idle") setHighlightedIndex(0); }}
              onClick={() => chosen ? reset(index) : choose(index)}
            >
              {chosen && phase === "collapsed" ? "Đặt lại" : option.label}
            </button>
          );
        })}
      </div>
      <span className="visually-hidden" aria-live="polite">{status}</span>
    </div>
  );
}
