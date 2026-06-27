import { WORKFLOWS } from "../constants/index.js";

export default function Sidebar({ activeWorkflow, onWorkflowClick, onNewChat }) {
  return (
    <aside style={{
      width: "var(--sidebar-w)",
      background: "var(--surface)",
      borderRight: "1px solid var(--border)",
      display: "flex",
      flexDirection: "column",
      overflow: "hidden",
      flexShrink: 0,
    }}>

      {/* New Chat Button */}
      <div style={{ padding: "14px 12px 10px" }}>
        <button
          onClick={onNewChat}
          style={{
            width: "100%",
            padding: "9px 14px",
            background: "linear-gradient(135deg, var(--accent) 0%, var(--accent-mid) 100%)",
            color: "#fff",
            border: "none",
            borderRadius: "var(--radius)",
            fontSize: 13,
            fontWeight: 500,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 7,
            boxShadow: "0 2px 8px rgba(47,56,144,0.25)",
            letterSpacing: "-0.1px",
            fontFamily: "var(--font)",
          }}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <line x1="12" y1="5" x2="12" y2="19"/>
            <line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          New chat
        </button>
      </div>

      {/* Divider */}
      <div style={{ height: 1, background: "var(--border)", margin: "0 12px" }} />

      {/* Workflows Label */}
      <div style={{ padding: "14px 16px 6px" }}>
        <div style={{
          fontSize: 10,
          fontWeight: 600,
          letterSpacing: "0.9px",
          textTransform: "uppercase",
          color: "var(--text-muted)",
        }}>
          Workflows
        </div>
      </div>

      {/* Workflow List */}
      <div style={{ flex: 1, overflowY: "auto", padding: "2px 8px 16px" }}>
        {WORKFLOWS.map(wf => (
          <div
            key={wf}
            onClick={() => onWorkflowClick(wf)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 9,
              padding: "8px 10px",
              borderRadius: "var(--radius)",
              fontSize: 12.5,
              color: activeWorkflow === wf ? "var(--accent)" : "var(--text-secondary)",
              background: activeWorkflow === wf ? "var(--accent-light)" : "transparent",
              fontWeight: activeWorkflow === wf ? 500 : 400,
              cursor: "pointer",
              marginBottom: 1,
              transition: "background var(--transition), color var(--transition)",
              fontFamily: "var(--font)",
            }}
            onMouseEnter={e => {
              if (activeWorkflow !== wf) {
                e.currentTarget.style.background = "var(--surface-2)";
                e.currentTarget.style.color = "var(--text-primary)";
              }
            }}
            onMouseLeave={e => {
              if (activeWorkflow !== wf) {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.color = "var(--text-secondary)";
              }
            }}
          >
            {/* Icon */}
            <div style={{
              width: 22, height: 22,
              borderRadius: 5,
              background: activeWorkflow === wf ? "var(--accent-light)" : "var(--surface-2)",
              border: `1px solid ${activeWorkflow === wf ? "var(--accent-mid)" : "var(--border)"}`,
              display: "flex", alignItems: "center", justifyContent: "center",
              flexShrink: 0,
            }}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
                stroke={activeWorkflow === wf ? "var(--accent)" : "var(--text-muted)"}
                strokeWidth="2">
                <rect x="3" y="3" width="6" height="6" rx="1"/>
                <rect x="15" y="3" width="6" height="6" rx="1"/>
                <rect x="9" y="15" width="6" height="6" rx="1"/>
                <line x1="6" y1="9" x2="6" y2="12"/>
                <line x1="18" y1="9" x2="18" y2="12"/>
                <line x1="6" y1="12" x2="12" y2="12"/>
                <line x1="18" y1="12" x2="12" y2="12"/>
                <line x1="12" y1="12" x2="12" y2="15"/>
              </svg>
            </div>
            <span>{wf}</span>
          </div>
        ))}
      </div>
    </aside>
  );
}