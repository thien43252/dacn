import type { Activity, LearningReport } from "../../api-client/types";
import { Icon } from "../../components/Icon";

/** Questions per day as thin bars; each bar has a tooltip and the numbers are also in its label. */
export function DailyBars({ daily }: { daily: Activity["daily"] }) {
  const peak = Math.max(1, ...daily.map((day) => day.questions));
  return (
    <figure className="ea-bars" aria-label="Số câu hỏi mỗi ngày">
      <div className="ea-bars__plot">
        {daily.map((day) => {
          const label = `${new Date(day.date).toLocaleDateString("vi-VN", { weekday: "short", day: "2-digit", month: "2-digit" })}: ${day.questions} câu`;
          return (
            <div key={day.date} className="ea-bars__col" title={label} aria-label={label} role="img">
              {day.questions > 0 && <span className="ea-bars__value">{day.questions}</span>}
              <span className="ea-bars__bar" style={{ height: `${(day.questions / peak) * 100}%` }} />
            </div>
          );
        })}
      </div>
      <div className="ea-bars__axis">
        {daily.map((day) => <span key={day.date}>{new Date(day.date).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" })}</span>)}
      </div>
      <figcaption className="ea-muted">Số câu hỏi mỗi ngày</figcaption>
    </figure>
  );
}

export function ReportView({ report, audience }: { report: LearningReport; audience: "parent" | "teacher" }) {
  const { activity, narrative } = report;
  const child = audience === "parent" ? "con" : "em";
  return (
    <div className="ea-page">
      {activity.wellbeing_alerts > 0 && (
        <div className="form-error" role="alert">
          <Icon name="alert" /> Có {activity.wellbeing_alerts} lần hệ thống ghi nhận dấu hiệu {child} buồn bã hoặc áp lực. Hãy dành thời gian
          trò chuyện với {child}. Nếu cần, gọi Tổng đài quốc gia bảo vệ trẻ em 111 (miễn phí, 24/7).
        </div>
      )}
      <div className="ea-stats">
        <div className="ea-stat"><span>Câu hỏi</span><strong>{activity.questions_asked}</strong></div>
        <div className="ea-stat"><span>Ngày có học</span><strong>{activity.active_days}/{activity.period_days}</strong></div>
        <div className="ea-stat"><span>Tin nhắn bị chặn</span><strong>{activity.blocked_messages}</strong></div>
        <div className="ea-stat"><span>Lần cuối</span><strong className="ea-stat__small">{activity.last_active ? new Date(activity.last_active).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "–"}</strong></div>
      </div>
      <section className="ea-card ea-page">
        <h3>Nhận xét</h3>
        <p>{narrative.summary}</p>
        {narrative.highlights.length > 0 && (<><h4>Điểm tích cực</h4><ul className="ea-reasons">{narrative.highlights.map((item) => <li key={item}>{item}</li>)}</ul></>)}
        {narrative.suggestions.length > 0 && (<><h4>{audience === "parent" ? "Gợi ý kèm con" : "Gợi ý hỗ trợ"}</h4><ul className="ea-reasons">{narrative.suggestions.map((item) => <li key={item}>{item}</li>)}</ul></>)}
        <p className="ea-muted">{narrative.generated_by === "llm" ? "Nhận xét do AI viết từ số liệu tổng hợp." : "Nhận xét tự động theo mẫu (chưa nối mô hình)."} Báo cáo không chứa nguyên văn tin nhắn của {child}.</p>
      </section>
      <div className="ea-detail">
        <section className="ea-card"><DailyBars daily={activity.daily} /></section>
        <aside className="ea-card ea-detail__side">
          <dl className="ea-facts">
            <div><dt>Môn hay hỏi</dt><dd>{Object.keys(activity.subjects).join(", ") || "–"}</dd></div>
            <div><dt>Agent đã dùng</dt><dd>{Object.entries(activity.agents_used).map(([slug, count]) => `@${slug} (${count})`).join(", ") || "–"}</dd></div>
            <div><dt>Từ khoá thường gặp</dt><dd>{activity.frequent_keywords.join(", ") || "–"}</dd></div>
          </dl>
        </aside>
      </div>
    </div>
  );
}
