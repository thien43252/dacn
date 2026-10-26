import { type FormEvent, useEffect, useMemo, useState } from "react";

import { navigate, useLocation } from "../../app/router";
import { errorMessage, useResource } from "../../app/useResource";
import { builderApi, toolsApi } from "../../api-client/agents";
import { type AgentDetail, type AgentManifest, type AgentRole, ROLE_LABELS, SUBJECT_LABELS } from "../../api-client/types";
import { ChatThread, mascotOf, NO_MESSAGES } from "../../components/chat/ChatThread";
import { Icon } from "../../components/Icon";
import { Mascot, type MascotName } from "../../components/Mascot";
import { AgentDetailDialog, CertificationBadge } from "./AgentCard";

const AVATARS: MascotName[] = ["owl", "cat", "panda", "penguin", "bear", "bunny", "deer", "frog", "hamster", "hedgehog", "koala", "otter", "raccoon", "redpanda"];
const ROLES: AgentRole[] = ["student", "teacher", "parent"];

export function slugify(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "d")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
}

const BLANK: AgentManifest = {
  slug: "",
  name: "",
  description: "",
  avatar: "owl",
  subjects: ["toan"],
  grades: [],
  target_roles: ["student"],
  age_range: null,
  capabilities: [],
  tools: ["class_doc_search"],
  knowledge: "class_documents",
  system_prompt: "",
  examples: [],
  starter_prompts: [],
};

export function BuilderPage() {
  const { search } = useLocation();
  const selected = new URLSearchParams(search).get("agent");
  const mine = useResource(() => builderApi.mine(), []);
  const creating = selected === "new";
  const current = mine.data?.find((agent) => agent.id === selected) ?? null;

  function select(id: string | null) {
    navigate(id ? `/teacher/builder?agent=${encodeURIComponent(id)}` : "/teacher/builder");
  }

  return (
    <div className="ea-builder">
      <aside className="ea-card ea-builder__list">
        <button className="button button--primary button--full" type="button" onClick={() => select("new")}><Icon name="plus" /> Tạo agent mới</button>
        {mine.error && <div className="ea-error">{mine.error}</div>}
        {mine.data && mine.data.length === 0 && <p className="ea-muted">Chưa có agent nào. Tạo mới hoặc tạo bản sao từ Agent Hub.</p>}
        <ul>
          {(mine.data ?? []).map((agent) => (
            <li key={agent.id}>
              <button type="button" className={agent.id === selected ? "is-active" : ""} onClick={() => select(agent.id)}>
                <Mascot character={mascotOf((agent.draft_manifest ?? agent.manifest).avatar)} mood="still" size={32} />
                <span><strong>{(agent.draft_manifest ?? agent.manifest).name}</strong><small>{agent.version ? `Phiên bản ${agent.version}` : "Bản nháp"}</small></span>
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <section className="ea-builder__main">
        {creating && <AgentEditor key="new" onSaved={(agent) => { mine.reload(); select(agent.id); }} />}
        {current && <AgentEditor key={current.id} agent={current} onSaved={() => mine.reload()} />}
        {!creating && !current && (
          <div className="ea-empty">
            <Icon name="sparkles" />
            <p>Chọn một agent để chỉnh, hoặc tạo agent mới từ các công cụ đã kiểm chứng của nền tảng.</p>
          </div>
        )}
      </section>
    </div>
  );
}

function lines(text: string): string[] {
  return text.split("\n").map((line) => line.trim()).filter(Boolean);
}

function AgentEditor({ agent, onSaved }: { agent?: AgentDetail; onSaved: (agent: AgentDetail) => void }) {
  const tools = useResource(() => toolsApi.list(), []);
  const [form, setForm] = useState<AgentManifest>(agent?.draft_manifest ?? agent?.manifest ?? BLANK);
  const [capabilities, setCapabilities] = useState(form.capabilities.join("\n"));
  const [starters, setStarters] = useState(form.starter_prompts.join("\n"));
  const [slugTouched, setSlugTouched] = useState(Boolean(agent));
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [trying, setTrying] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [tryRole, setTryRole] = useState<AgentRole>(form.target_roles[0] ?? "student");
  const [tryConversation, setTryConversation] = useState<string | null>(null);
  const [tryRun, setTryRun] = useState(0);
  const set = <K extends keyof AgentManifest>(key: K, value: AgentManifest[K]) => setForm((value_) => ({ ...value_, [key]: value }));
  const manifest = useMemo(() => ({ ...form, capabilities: lines(capabilities), starter_prompts: lines(starters).slice(0, 6) }), [form, capabilities, starters]);
  const dirty = JSON.stringify(manifest) !== JSON.stringify(agent?.draft_manifest ?? BLANK);

  useEffect(() => {
    if (!slugTouched) setForm((value) => ({ ...value, slug: slugify(value.name) }));
  }, [form.name, slugTouched]);

  function toggle<T>(list: T[], item: T): T[] {
    return list.includes(item) ? list.filter((value) => value !== item) : [...list, item];
  }

  async function run(action: () => Promise<AgentDetail>, ok: string) {
    setBusy(true);
    setStatus(null);
    try {
      const saved = await action();
      setStatus({ kind: "ok", text: ok });
      onSaved(saved);
    } catch (reason) {
      setStatus({ kind: "error", text: errorMessage(reason) });
    } finally {
      setBusy(false);
    }
  }

  function save(event?: FormEvent) {
    event?.preventDefault();
    return run(() => (agent ? builderApi.update(agent.id, manifest) : builderApi.create(manifest)), "Đã lưu bản nháp.");
  }

  return (
    <div className="ea-page">
      <form className="ea-card ea-form" onSubmit={save}>
        <div className="ea-toolbar">
          <h2>{agent ? manifest.name || agent.slug : "Agent mới"}</h2>
          <div className="ea-toolbar__actions">
            {agent?.versions[0] && <CertificationBadge status={agent.versions[0].certification_status} />}
          </div>
        </div>

        <div className="ea-form__row">
          <label className="field"><span>Tên agent</span><input value={form.name} maxLength={80} onChange={(event) => set("name", event.target.value)} placeholder="Ôn thi Hoá 9" /></label>
          <label className="field">
            <span>Mã gọi (@mã)</span>
            <input value={form.slug} maxLength={48} disabled={Boolean(agent)} onChange={(event) => { setSlugTouched(true); set("slug", slugify(event.target.value)); }} />
            <small className="field__hint">{agent ? "Không đổi được sau khi tạo." : "Chữ thường không dấu và dấu gạch ngang."}</small>
          </label>
        </div>
        <label className="field"><span>Mô tả ngắn</span><textarea rows={2} maxLength={500} value={form.description} onChange={(event) => set("description", event.target.value)} /></label>

        <div className="field">
          <span>Hình đại diện</span>
          <div className="ea-avatar-picker" role="radiogroup" aria-label="Hình đại diện">
            {AVATARS.map((avatar) => (
              <button key={avatar} type="button" role="radio" aria-checked={form.avatar === avatar} className={form.avatar === avatar ? "is-active" : ""} onClick={() => set("avatar", avatar)}>
                <Mascot character={avatar} mood="still" size={40} />
              </button>
            ))}
          </div>
        </div>

        <div className="ea-form__row">
          <fieldset className="field ea-checks">
            <span>Dành cho</span>
            {ROLES.map((role) => (
              <label key={role} className="ea-switch"><input type="checkbox" checked={form.target_roles.includes(role)} onChange={() => set("target_roles", toggle(form.target_roles, role))} /><span>{ROLE_LABELS[role]}</span></label>
            ))}
          </fieldset>
          <fieldset className="field ea-checks">
            <span>Môn</span>
            <select multiple value={form.subjects} onChange={(event) => set("subjects", Array.from(event.target.selectedOptions, (option) => option.value))} size={5}>
              <option value="chung">Chung (mọi môn)</option>
              {Object.entries(SUBJECT_LABELS).map(([code, label]) => <option key={code} value={code}>{label}</option>)}
            </select>
          </fieldset>
          <fieldset className="field ea-checks">
            <span>Khối lớp (để trống = mọi khối)</span>
            <div className="ea-grade-picker">
              {Array.from({ length: 12 }, (_, index) => index + 1).map((grade) => (
                <button key={grade} type="button" className={form.grades.includes(grade) ? "is-active" : ""} aria-pressed={form.grades.includes(grade)} onClick={() => set("grades", toggle(form.grades, grade).sort((a, b) => a - b))}>{grade}</button>
              ))}
            </div>
          </fieldset>
        </div>

        <label className="field">
          <span>Agent làm được gì (mỗi dòng một ý, orchestrator dùng để chọn agent)</span>
          <textarea rows={3} value={capabilities} onChange={(event) => setCapabilities(event.target.value)} placeholder={"ôn tập hoá học lớp 9\ngiải thích phản ứng hoá học"} />
        </label>

        <fieldset className="field">
          <span>Công cụ của nền tảng</span>
          <div className="ea-tool-picker">
            {(tools.data ?? []).map((tool) => (
              <label key={tool.name} className={`ea-tool-option${form.tools.includes(tool.name) ? " is-active" : ""}`}>
                <input type="checkbox" checked={form.tools.includes(tool.name)} onChange={() => set("tools", toggle(form.tools, tool.name))} />
                <span><strong>{tool.title}</strong><small>{tool.description}</small><small className="ea-muted">Vai trò: {tool.roles.map((role) => ROLE_LABELS[role]).join(", ")}</small></span>
              </label>
            ))}
          </div>
        </fieldset>
        <label className="ea-switch">
          <input type="checkbox" checked={form.knowledge === "class_documents"} onChange={(event) => set("knowledge", event.target.checked ? "class_documents" : "none")} />
          <span>Được đọc tài liệu của lớp nơi agent được cài</span>
        </label>

        <label className="field">
          <span>Hướng dẫn hệ thống</span>
          <textarea rows={10} maxLength={8000} value={form.system_prompt} onChange={(event) => set("system_prompt", event.target.value)}
            placeholder={"Mô tả agent là ai, làm việc thế nào, không làm gì.\nVí dụ: Bạn giúp học sinh lớp 9 ôn Hoá. Hỏi lại học sinh đã hiểu đến đâu, gợi ý từng bước, không đưa đáp án bài tập về nhà."} />
          <small className="field__hint">Quy tắc an toàn của nền tảng và chính sách của lớp luôn được áp lên trên hướng dẫn này. Hướng dẫn được hiển thị công khai trên Hub.</small>
        </label>
        <label className="field">
          <span>Câu gợi ý cho người dùng (mỗi dòng một câu)</span>
          <textarea rows={2} value={starters} onChange={(event) => setStarters(event.target.value)} />
        </label>

        {status && <div className={status.kind === "ok" ? "ea-notice" : "form-error"} role="status">{status.text}</div>}
        <div className="ea-toolbar__actions">
          <button className="button button--primary" type="submit" disabled={busy || !dirty}><Icon name="check" /> {agent ? "Lưu bản nháp" : "Tạo agent"}</button>
          {agent && (
            <>
              <button className="button button--secondary" type="button" disabled={busy || dirty} title={dirty ? "Lưu bản nháp trước" : undefined}
                onClick={() => void run(() => builderApi.snapshot(agent.id), "Đã tạo phiên bản mới. Phiên bản cần qua kiểm định trước khi học sinh dùng được.")}>
                <Icon name="layers" /> Tạo phiên bản
              </button>
              <button className="button button--secondary" type="button" disabled={dirty} onClick={() => { setTryConversation(null); setTryRun((value) => value + 1); setTrying(true); }}><Icon name="play" /> Thử ngay</button>
              <button className="button button--ghost" type="button" disabled={!agent.version} onClick={() => setInstalling(true)}><Icon name="plus" /> Cài vào lớp</button>
            </>
          )}
        </div>
      </form>

      {agent && agent.versions.length > 0 && (
        <section className="ea-card">
          <h3>Phiên bản</h3>
          <ul className="ea-versions">
            {agent.versions.map((version) => (
              <li key={version.id}>
                <strong>v{version.version}</strong>
                <CertificationBadge status={version.certification_status} />
                <span className="ea-muted">{new Date(version.created_at).toLocaleString("vi-VN")}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {agent && trying && (
        <section className="ea-card ea-sandbox">
          <div className="ea-toolbar">
            <h3>Thử bản nháp</h3>
            <div className="ea-toolbar__actions">
              <label className="ea-inline-select">
                Đóng vai
                <select value={tryRole} onChange={(event) => { setTryRole(event.target.value as AgentRole); setTryConversation(null); setTryRun((value) => value + 1); }}>
                  {form.target_roles.map((role) => <option key={role} value={role}>{ROLE_LABELS[role]}</option>)}
                </select>
              </label>
              <button className="icon-button" type="button" aria-label="Đóng thử nghiệm" onClick={() => setTrying(false)}><Icon name="x" /></button>
            </div>
          </div>
          <div className="ea-sandbox__chat">
            <ChatThread
              key={`${agent.id}:${tryRole}:${tryRun}`}
              endpoint={builderApi.tryPath(agent.id)}
              requestFields={{ as_role: tryRole }}
              agents={[{ slug: manifest.slug, name: manifest.name, description: manifest.description, avatar: manifest.avatar, source: "sandbox", certification_status: "uncertified", starter_prompts: manifest.starter_prompts }]}
              conversationId={tryConversation}
              initialMessages={NO_MESSAGES}
              onConversation={setTryConversation}
              emptyHint="Đây là phòng thử: agent chạy với bản nháp, ngoài mọi lớp, vẫn qua quy tắc an toàn của nền tảng."
            />
          </div>
        </section>
      )}

      {agent && installing && <AgentDetailDialog agentId={agent.id} onClose={() => setInstalling(false)} />}
    </div>
  );
}
