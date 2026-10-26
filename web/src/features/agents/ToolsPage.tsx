import { useResource } from "../../app/useResource";
import { toolsApi } from "../../api-client/agents";
import { ROLE_LABELS } from "../../api-client/types";

/** Read-only view of the tool registry exposed through the platform MCP server. */
export function ToolsPage() {
  const tools = useResource(() => toolsApi.list(), []);
  return (
    <div className="ea-page">
      <div className="ea-notice">
        Agent chỉ dùng được công cụ trong danh mục này. Mọi lời gọi đi qua MCP server của nền tảng
        (<code>uv run python -m app.tools.server</code>) sau khi tool guard kiểm tra vai trò, lớp và tham số.
      </div>
      {tools.error && <div className="ea-error">{tools.error}</div>}
      <div className="ea-table-wrap">
        <table className="ea-table">
          <thead><tr><th>Công cụ</th><th>Vai trò được dùng</th><th>Tham số mô hình điền</th></tr></thead>
          <tbody>
            {(tools.data ?? []).map((tool) => (
              <tr key={tool.name}>
                <td>
                  <strong>{tool.title}</strong> <code>{tool.name}</code>
                  <br /><span className="ea-muted">{tool.description}</span>
                  {tool.needs_class && <><br /><span className="ea-chip">Cần ngữ cảnh lớp</span></>}
                </td>
                <td>{tool.roles.map((role) => ROLE_LABELS[role]).join(", ")}</td>
                <td>
                  <ul className="ea-param-list">
                    {Object.entries(tool.parameters.properties ?? {}).map(([name, schema]) => (
                      <li key={name}><code>{name}</code>{schema.description ? " – " + schema.description : ""}</li>
                    ))}
                  </ul>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
