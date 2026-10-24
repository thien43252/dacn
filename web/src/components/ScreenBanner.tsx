import classroomDesk from "../assets/illustrations/derived/art-classroom-desk.webp";
import classroomGirl from "../assets/illustrations/derived/art-classroom-girl.webp";
import classroomQuill from "../assets/illustrations/derived/art-classroom-quill.webp";
import forestGirl from "../assets/illustrations/derived/art-forest-girl.webp";
import adminWizard from "../assets/illustrations/derived/admin-wizard-character-cutout.webp";
import libraryBoy from "../assets/illustrations/derived/art-library-boy.webp";
import libraryGirl from "../assets/illustrations/derived/art-library-girl.webp";
import teacherBook from "../assets/illustrations/derived/art-teacher-book.webp";
import teacherLadder from "../assets/illustrations/derived/art-teacher-ladder.webp";
import teacherReading from "../assets/illustrations/derived/art-teacher-reading.webp";
import workshopShelves from "../assets/illustrations/derived/library-header-shelves.webp";
import workshopBookGlow from "../assets/illustrations/derived/library-header-book-glow.webp";
import workshopRowA from "../assets/illustrations/derived/library-header-books-row-a.webp";
import workshopRowB from "../assets/illustrations/derived/library-header-books-row-b.webp";
import workshopRowC from "../assets/illustrations/derived/library-header-books-row-c.webp";
import motifOpenBook from "../assets/illustrations/derived/motif-open-book.webp";
import { ArtworkMotion } from "./ArtworkMotion";

export type Tone = "lemon" | "moss" | "aqua" | "soft";

/** One transparent, vector-exact cutout in the banner cast. `float` props drift on their own; the rest stay grounded. */
interface CastItem {
  key: string;
  src: string;
  w: number;
  h: number;
  /** Height as a percentage of the banner art area. */
  size: number;
  float?: boolean;
  /** Seconds before the entrance/float starts (staggers props). */
  delay?: number;
  /** Props sit high (beside a character's raised hand); characters stand on the banner baseline. */
  high?: boolean;
}

interface ScreenTreatment {
  /** Dominant supporting colour of the screen (UI_SPEC §3): the banner, a soft page wash and heading highlights. */
  tone: Tone;
  cast: CastItem[];
  /** A complete scene when the surrounding environment is part of the screen's meaning. */
  /** Lets a slim (compact) banner grow just enough to show the full silhouette of its single character. */
  feature?: boolean;
  /** Library header: stationary shelves with floating books and the glowing open book, all transparent cutouts. */
  workshop?: boolean;
  scene?: { src: string; srcSet: string; width: number; height: number };
}

const classroomGirlItem: CastItem = { key: "cl-girl", src: classroomGirl, w: 704, h: 760, size: 100 };
const forestGirlItem: CastItem = { key: "fo-girl", src: forestGirl, w: 374, h: 760, size: 100 };
const reading: CastItem = { key: "tl-reading", src: teacherReading, w: 1046, h: 620, size: 94 };
const ladder: CastItem = { key: "tl-ladder", src: teacherLadder, w: 435, h: 520, size: 100 };
const book = (size: number, delay = 0.4): CastItem => ({ key: "book", src: motifOpenBook, w: 551, h: 240, size, float: true, delay, high: true });

/** Screen to treatment. Student Home and the landing page keep their own dark heroes and are not listed. */
export const SCREEN_TREATMENTS: Record<string, ScreenTreatment> = {
  "/teacher/classes": { tone: "soft", cast: [reading] },
  "/teacher/classes/:classId": { tone: "aqua", cast: [ladder, { key: "tl-book", src: teacherBook, w: 609, h: 98, size: 16 }] },
  "/teacher/hub": { tone: "aqua", cast: [], workshop: true },
  "/teacher/builder": { tone: "moss", feature: true, cast: [{ key: "admin-wizard", src: adminWizard, w: 368, h: 760, size: 100 }] },
  "/teacher/audit": { tone: "lemon", cast: [ladder, book(30)] },
  "/student/home": { tone: "lemon", cast: [{ key: "quill", src: classroomQuill, w: 156, h: 360, size: 46, float: true, delay: 0.5, high: true }, classroomGirlItem] },
  "/student/classes": { tone: "aqua", cast: [{ key: "lib-girl", src: libraryGirl, w: 866, h: 760, size: 100 }, { key: "lib-boy", src: libraryBoy, w: 373, h: 520, size: 64 }] },
  "/student/hub": { tone: "aqua", cast: [], workshop: true },
  "/student/agents": { tone: "moss", cast: [forestGirlItem] },
  "/parent/home": { tone: "soft", cast: [{ key: "cl-desk", src: classroomDesk, w: 757, h: 560, size: 94 }] },
  "/parent/reports": { tone: "moss", cast: [{ key: "cl-desk", src: classroomDesk, w: 757, h: 560, size: 90 }, book(30, 0.4)] },
  "/parent/hub": { tone: "aqua", cast: [], workshop: true },
  "/parent/consent": { tone: "lemon", cast: [{ key: "lib-boy", src: libraryBoy, w: 373, h: 520, size: 88 }, book(30, 0.6)] },
  "/admin/certification": { tone: "lemon", cast: [reading] },
  "/admin/agents": { tone: "aqua", cast: [], workshop: true },
  "/admin/tools": { tone: "moss", feature: true, cast: [{ key: "admin-wizard", src: adminWizard, w: 368, h: 760, size: 100 }] },
  "/admin/audit": { tone: "soft", cast: [] },
};

export function toneOf(pathname: string): Tone | undefined {
  return SCREEN_TREATMENTS[pathname]?.tone;
}

interface ScreenBannerProps {
  pathname: string;
  title: string;
  eyebrow?: string;
  description?: string;
  /** Slim variant for screens that fill the viewport (the agent canvas). */
  compact?: boolean;
}

/** Colour-led header for a work screen with a small cast of cutouts. Copy comes from the existing route metadata. */
export function ScreenBanner({ pathname, title, eyebrow, description, compact = false }: ScreenBannerProps) {
  const treatment = SCREEN_TREATMENTS[pathname];
  if (!treatment) return null;
  return (
    <header className={`screen-banner${compact ? " screen-banner--compact" : ""}${treatment.scene ? " screen-banner--library" : ""}${treatment.feature ? " screen-banner--feature" : ""}${treatment.workshop ? " screen-banner--workshop" : ""}`} data-tone={treatment.tone}>
      <div className="screen-banner__copy">
        {eyebrow && <span className="screen-banner__eyebrow">{eyebrow}</span>}
        <h1>{title}</h1>
        {description && !compact && <p>{description}</p>}
      </div>
      {treatment.workshop ? (
        <div className="library-art" aria-hidden="true">
          <div className="library-art__canvas">
            <img className="library-art__shelves" src={workshopShelves} width={1920} height={600} alt="" decoding="async" />
            <ArtworkMotion id={`banner-${pathname}-glow`} variant="accent" loop="float" delay={0.2} className="library-art__item library-art__glow">
              <img src={workshopBookGlow} width={518} height={200} alt="" />
            </ArtworkMotion>
            <ArtworkMotion id={`banner-${pathname}-row-a`} variant="accent" loop="float" delay={0.6} className="library-art__item library-art__row-a">
              <img src={workshopRowA} width={306} height={220} alt="" />
            </ArtworkMotion>
            <ArtworkMotion id={`banner-${pathname}-row-b`} variant="accent" loop="float" delay={1} className="library-art__item library-art__row-b">
              <img src={workshopRowB} width={254} height={220} alt="" />
            </ArtworkMotion>
            <ArtworkMotion id={`banner-${pathname}-row-c`} variant="accent" loop="float" delay={1.4} className="library-art__item library-art__row-c">
              <img src={workshopRowC} width={256} height={220} alt="" />
            </ArtworkMotion>
          </div>
        </div>
      ) : treatment.scene ? (
        <ArtworkMotion id={`banner-${pathname}-scene`} variant="scene" className="screen-banner__scene">
          <img src={treatment.scene.src} srcSet={treatment.scene.srcSet} sizes="(max-width: 960px) 300px, 560px"
            width={treatment.scene.width} height={treatment.scene.height} alt="" decoding="async" />
        </ArtworkMotion>
      ) : <div className="screen-banner__cast" aria-hidden="true">
        {treatment.cast.map((item) => (
          <ArtworkMotion
            key={item.key}
            id={`banner-${pathname}-${item.key}`}
            variant={item.float ? "accent" : "hero"}
            loop={item.float ? "float" : undefined}
            delay={item.delay ?? 0}
            className={`screen-banner__item${item.high ? " is-high" : ""}`}
            style={{ height: `${item.size}%` }}
          >
            <img src={item.src} width={item.w} height={item.h} alt="" />
          </ArtworkMotion>
        ))}
      </div>}
    </header>
  );
}
