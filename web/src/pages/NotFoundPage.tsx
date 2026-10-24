import { navigate } from "../app/router";
import { Icon } from "../components/Icon";
import { Logo } from "../components/Logo";

export function NotFoundPage() {
  return <main className="system-page"><Logo /><div className="system-card frosted"><span className="eyebrow">404 · KHÔNG TÌM THẤY</span><h1>Không tìm thấy trang này.</h1><p>Kiểm tra lại đường dẫn hoặc quay về trang giới thiệu.</p><button className="button button--primary" type="button" onClick={() => navigate("/", true)}>Về trang giới thiệu <Icon name="arrow-right" /></button></div></main>;
}
