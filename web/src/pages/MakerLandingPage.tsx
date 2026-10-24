import { LazyMotion, domAnimation, m, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

import { getHomePath, navigate } from "../app/router";
import { useAuth } from "../auth/AuthContext";
import { ArtworkMotion } from "../components/ArtworkMotion";
import { HeroStudent } from "../components/HeroStudent";
import { Icon } from "../components/Icon";
import { AppMark } from "../components/AppMark";
import { Mascot, type MascotName } from "../components/Mascot";
import { JourneySketch } from "./landing/MakerScene";
import motifOpenBook from "../assets/illustrations/derived/motif-open-book.webp";
import "../styles/maker-landing.css";

const journey = [
  { title: "Tạo lớp trong một phút.", action: "Tạo lớp", copy: "Giáo viên tạo lớp, gửi mã cho học sinh và phụ huynh. Không cần trường mua, không cần cài đặt.", note: "Lớp 8A1 · Toán · mã 7KQ2PX" },
  { title: "Chọn agent phù hợp.", action: "Tìm trên Hub", copy: "Agent Hub có agent do nền tảng và các giáo viên khác chia sẻ, lọc theo môn và khối lớp.", note: "Gia sư Toán Socratic · đã kiểm định" },
  { title: "Dạy bằng tài liệu của bạn.", action: "Thêm tài liệu", copy: "Tải giáo án, đề cương lên lớp. Agent trả lời dựa trên tài liệu và chính sách của lớp.", note: "Chương 3: Phương trình bậc nhất" },
  { title: "Theo dõi và an tâm.", action: "Giám sát an toàn", copy: "Mọi agent đi qua lớp bảo vệ. Giáo viên xem nhật ký, phụ huynh nhận báo cáo học tập của con.", note: "Đã chặn 1 yêu cầu làm hộ bài." },
];

const guides: { name: MascotName; label: string; role: string; copy: string }[] = [
  { name: "cat", label: "Gia sư Socratic", role: "Gợi mở thay vì giải hộ", copy: "Hỏi lại từng bước để học sinh tự tìm ra lời giải." },
  { name: "panda", label: "Tạo đề", role: "Soạn đề theo tài liệu lớp", copy: "Sinh câu hỏi trắc nghiệm, tự luận kèm đáp án cho giáo viên." },
  { name: "penguin", label: "Lớp bảo vệ", role: "Kiểm duyệt mọi câu trả lời", copy: "Chặn nội dung không phù hợp lứa tuổi và lộ thông tin cá nhân." },
  { name: "owl", label: "Trợ lý phụ huynh", role: "Đồng hành cùng gia đình", copy: "Tóm tắt việc học của con và gợi ý cách kèm con ở nhà." },
];

function StudioBrand() {
  return <a className="maker-brand" href="/" aria-label="EduAgent Hub, trang chủ">
    <span className="logo__mark" aria-hidden="true"><AppMark /></span>
    <span><small>EduAgent</small><strong>Hub<span className="maker-brand__dot">.</span></strong></span>
  </a>;
}

/** A scoped landing experiment. All entry actions use the existing auth destinations. */
export function MakerLandingPage() {
  const { status, user } = useAuth();
  const authenticated = status === "authenticated" && Boolean(user);
  const workspacePath = getHomePath(user?.role ?? "student");
  const startPath = authenticated ? workspacePath : "/register";
  const reducedMotion = useReducedMotion();
  const [heroReady, setHeroReady] = useState(false);

  useEffect(() => {
    // Content is visible before JS animation starts, and remains so if animation is unavailable.
    setHeroReady(true);
  }, []);

  const entrance = (delay: number) => ({
    initial: false as const,
    animate: heroReady && !reducedMotion ? { y: [12, 0], opacity: [0.75, 1] } : { y: 0, opacity: 1 },
    transition: { duration: 0.65, delay: reducedMotion ? 0 : delay, ease: [0.16, 1, 0.3, 1] as const },
  });

  return <LazyMotion features={domAnimation}>
    <div className="maker-landing">
      <a href="#maker-main" className="maker-skip">Đến nội dung chính</a>
      <div className="maker-opening">
        <header className="maker-nav maker-wrap">
          <StudioBrand />
          <nav aria-label="Điều hướng trang giới thiệu">
            <a href="#how-it-works">Cách hoạt động</a><a href="#features">Agent mẫu</a><a href="#greenpulse">An toàn</a>
          </nav>
          <a className="maker-nav__entry" href={authenticated ? workspacePath : "/login"} onClick={(event) => { event.preventDefault(); navigate(authenticated ? workspacePath : "/login"); }}>
            {authenticated ? "Vào lớp học" : "Đăng nhập"}<Icon name="arrow-right" />
          </a>
        </header>
        <main id="maker-main">
          <section className="maker-hero maker-wrap" aria-labelledby="maker-promise">
            <div className="maker-hero__copy">
              <m.h1 id="maker-promise" {...entrance(0)}>Lớp học của bạn,<br />thêm những<br /><span>trợ giảng AI.</span></m.h1>
              <m.p {...entrance(0.08)}>EduAgent Hub giúp giáo viên tạo lớp, chọn agent đã được kiểm định an toàn và đưa vào lớp cho học sinh và phụ huynh.</m.p>
              <m.div className="maker-hero__actions" {...entrance(0.16)}>
                <m.a className="maker-cta" href={startPath} onClick={(event) => { event.preventDefault(); navigate(startPath); }} whileHover={reducedMotion ? undefined : { y: -3 }} whileTap={reducedMotion ? undefined : { scale: 0.98 }}>Tạo lớp miễn phí <Icon name="arrow-right" /></m.a>
                <a className="maker-journey-link" href="#how-it-works">Xem cách hoạt động <Icon name="chevron-down" /></a>
              </m.div>
              <m.div className="maker-hero__invite" {...entrance(0.25)}>
                <Mascot character="fox" mood="still" size={47} />
                <p>Giáo viên, học sinh, phụ huynh.<br /><strong>Một lớp học, nhiều trợ thủ.</strong></p>
              </m.div>
            </div>
            <div className="maker-hero__scene">
              <HeroStudent scope="landing" props={["open", "orange", "stack"]} />
            </div>
          </section>
          <div className="maker-opening__foot maker-wrap">
            <span>Nền tảng mở cho mọi giáo viên, không giới hạn ở một trường.</span>
            <a href="#how-it-works" aria-label="Cuộn đến cách hoạt động"><span>Cuộn để khám phá</span><Icon name="chevron-down" /></a>
          </div>

          <section className="maker-journey maker-wrap" id="how-it-works" aria-labelledby="maker-journey-title">
            <div className="maker-section-head">
              <h2 id="maker-journey-title">Bốn bước<br />để <span>lớp học có agent.</span></h2>
              <p>Không cần biết lập trình.<br />Giáo viên biết kỹ thuật có thể tự tạo agent và chia sẻ.</p>
            </div>
            <ol className="maker-journey__trail">
              {journey.map((step, index) => <m.li key={step.action} initial={false} whileInView={reducedMotion ? undefined : { y: [18, 0], opacity: [0.65, 1] }} viewport={{ once: true, amount: 0.3 }} transition={{ duration: 0.55, delay: index * 0.06 }}>
                <div className="maker-journey__sketch"><ArtworkMotion id={`journey-${index}`} variant="accent"><JourneySketch stage={index} /></ArtworkMotion><span>{index + 1}</span></div>
                <p className="maker-journey__action">{step.action}</p>
                <h3>{step.title}</h3><p>{step.copy}</p>
                <blockquote>{step.note}</blockquote>
              </m.li>)}
            </ol>
          </section>

          <section className="maker-project maker-wrap" id="greenpulse" aria-labelledby="maker-project-title">
            <div className="maker-project__drawing">
              <span className="maker-project__tape" aria-hidden="true" />
              <span className="maker-project__example">Kiểm định trước khi chia sẻ</span>
              <div className="maker-project__sketch"><ArtworkMotion id="project-sketch" variant="accent"><JourneySketch stage={2} /></ArtworkMotion></div>
              <span className="maker-project__annotation maker-project__annotation--one">Thử bằng câu hỏi khó</span>
              <span className="maker-project__annotation maker-project__annotation--two">Chấm an toàn, đúng vai</span>
              <span className="maker-project__signature">Báo cáo kiểm định / Gia sư Toán</span>
            </div>
            <div className="maker-project__copy">
              <h2 id="maker-project-title">Agent nào lên Hub<br />cũng phải <span>qua kiểm định.</span></h2>
              <p>Mỗi agent được chạy thử với hàng trăm câu hỏi khó trước khi được chia sẻ.</p>
              <p>Agent dễ bị lừa làm hộ bài, nói điều không phù hợp lứa tuổi hay làm lộ thông tin cá nhân sẽ bị từ chối kèm lý do cụ thể.</p>
              <div className="maker-project__question"><Icon name="sparkles" /><span>Chỉ agent đã kiểm định mới đến được với học sinh.</span></div>
              <a className="maker-inline-link" href={startPath} onClick={(event) => { event.preventDefault(); navigate(startPath); }}>Bắt đầu ngay <Icon name="arrow-right" /></a>
            </div>
          </section>

          <section className="maker-support" id="features" aria-labelledby="maker-support-title">
            <div className="maker-wrap">
              <div className="maker-section-head">
                <h2 id="maker-support-title">Agent mẫu<br />sẵn sàng <span>cho lớp bạn.</span></h2>
                <p>Mỗi agent có một việc riêng.<br />Tất cả làm việc cùng nhau theo chính sách của lớp.</p>
              </div>
              <div className="maker-guides">
                {guides.map((guide) => <article key={guide.name} className={`maker-guide maker-guide--${guide.name}`}>
                  <div className="maker-guide__portrait"><Mascot character={guide.name} mood="still" size={112} /></div>
                  <h3>{guide.label}</h3><strong>{guide.role}</strong><p>{guide.copy}</p>
                </article>)}
              </div>
              <div className="maker-human" id="principles">
                <Icon name="book" />
                <div><h3>AI gợi ý. Học sinh tự làm. Thầy cô và phụ huynh đồng hành.</h3><p>Giáo viên đặt chính sách cho lớp, phụ huynh quyết định quyền dùng của con. Agent chỉ hỗ trợ, không thay người học.</p></div>
              </div>
            </div>
          </section>

          <section className="maker-close maker-wrap" aria-labelledby="maker-close-title">
            <div className="maker-close__sprout" aria-hidden="true"><ArtworkMotion id="close-sprout" variant="accent"><JourneySketch stage={0} /></ArtworkMotion></div>
            <ArtworkMotion id="landing-motif" variant="accent" loop="float" className="maker-motif-wrap"><img className="maker-motif" src={motifOpenBook} width={550} height={240} alt="" /></ArtworkMotion>
            <h2 id="maker-close-title">Lớp học tiếp theo<br />có thể bắt đầu <span>từ bạn.</span></h2>
            <p>Tạo lớp, mời học sinh và chọn agent đầu tiên.</p>
            <m.a className="maker-cta" href={startPath} onClick={(event) => { event.preventDefault(); navigate(startPath); }} whileHover={reducedMotion ? undefined : { y: -3 }} whileTap={reducedMotion ? undefined : { scale: 0.98 }}>Tạo lớp miễn phí <Icon name="arrow-right" /></m.a>
          </section>
        </main>
      </div>
      <footer className="maker-footer maker-wrap"><StudioBrand /><span>Nền tảng mở cho lớp học có AI.</span><a href="#maker-main">Về đầu trang <Icon name="chevron-up" /></a></footer>
    </div>
  </LazyMotion>;
}
