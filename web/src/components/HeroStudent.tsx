import base from "../assets/illustrations/derived/hero-base-student.webp";
import openBook from "../assets/illustrations/derived/prop-open-book.webp";
import orangeBook from "../assets/illustrations/derived/prop-orange-book.webp";
import bookStack from "../assets/illustrations/derived/prop-book-stack.webp";
import { ArtworkMotion } from "./ArtworkMotion";

/**
 * Layout in percent of one shared canvas, from the vector bounding boxes of the layers
 * (design-assets/illustrations/scripts/cut_from_vectors.py): canvas aspect 0.6715.
 */
const BASE = { left: 0, top: 18.27, width: 82.81 };
const PROPS = {
  open: { src: openBook, left: 60.28, top: 0, width: 39.73, w: 319, h: 240, delay: 0.5 },
  orange: { src: orangeBook, left: 70.86, top: 44.38, width: 26.42, w: 400, h: 240, delay: 1.1 },
  stack: { src: bookStack, left: 0.52, top: 46.83, width: 21.85, w: 386, h: 240, delay: 0.8 },
} as const;

export type HeroProp = keyof typeof PROPS;

/**
 * The student stays grounded (entrance only); the books that float free of her are separate vector-exact cutouts that
 * drift independently. `scope` keeps the once-per-page entrances of different screens separate.
 */
export function HeroStudent({ scope, props }: { scope: string; props: readonly HeroProp[] }) {
  return (
    <div className="hero-layers">
      <ArtworkMotion id={`${scope}-base`} variant="hero" className="hero-layers__layer" style={{ left: `${BASE.left}%`, top: `${BASE.top}%`, width: `${BASE.width}%` }}>
        <img src={base} width={748} height={1100} alt="Một học sinh ôm sách, ngước nhìn cuốn sách phát sáng đang bay lên giữa những cuốn sách khác." />
      </ArtworkMotion>
      {props.map((key) => {
        const p = PROPS[key];
        return (
          <ArtworkMotion key={key} id={`${scope}-${key}`} variant="accent" loop="float" delay={p.delay} className="hero-layers__layer"
            style={{ left: `${p.left}%`, top: `${p.top}%`, width: `${p.width}%` }}>
            <img src={p.src} width={p.w} height={p.h} alt="" />
          </ArtworkMotion>
        );
      })}
    </div>
  );
}
