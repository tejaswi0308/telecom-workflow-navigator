import { useState, useEffect } from "react";

export default function Sidebar({ activeWorkflow, onWorkflowClick, onNewChat }) {
  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/api/workflows")
      .then(res => {
        if (!res.ok) throw new Error("Failed to fetch workflows");
        return res.json();
      })
      .then(data => {
        setWorkflows(data.workflows || []);
        setLoading(false);
      })
      .catch(err => {
        setError("Could not load workflows");
        setLoading(false);
      });
  }, []);

  return (

  <aside
    style={{
      width: "100%",
      flex: 1,
      minHeight: 0,
      background: "var(--surface)",
      display: "flex",
      flexDirection: "column",
      overflow: "hidden",
    }}
  >
    {/* New Chat Button */}
    <div style={{ padding: "18px 14px 14px" }}>
      <button
        onClick={onNewChat}
        style={{
          width: "100%",
          padding: "14px 13px",
          background:
            "linear-gradient(135deg, var(--accent) 0%, var(--accent-mid) 100%)",
          color: "#fff",
          border: "none",
          borderRadius: "var(--radius-lg)",
          fontSize: 13.5,
          fontWeight: 500,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 8,
          boxShadow: "var(--accent-glow)",
          letterSpacing: "-0.1px",
          fontFamily: "var(--font)",
          transition: "transform var(--transition), box-shadow var(--transition)",
        }}
        onMouseEnter={e => {
          e.currentTarget.style.transform = "translateY(-1px)";
          e.currentTarget.style.boxShadow = "0 10px 26px rgba(83,77,231,0.48), 0 3px 8px rgba(83,77,231,0.30)";
        }}
        onMouseLeave={e => {
          e.currentTarget.style.transform = "translateY(0)";
          e.currentTarget.style.boxShadow = "var(--accent-glow)";
        }}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round">
          <line x1="12" y1="5" x2="12" y2="19"/>
          <line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        New chat
      </button>
    </div>

    {/* Workflows Label */}
    <div style={{ padding: "18px 18px 10px" }}>
      <div
        style={{
          fontSize: 10.5,
          fontWeight: 600,
          letterSpacing: "1.4px",
          textTransform: "uppercase",
          color: "#ADB2CC",
        }}
      >
        Workflows
      </div>
    </div>

    {/* Workflow List */}
    <div
      style={{
        flex: 1,
        overflowY: "auto",
        padding: "2px 10px 16px",
      }}
    >
      {/* Loading State */}
          {loading && (
            <div
              style={{
                padding: "12px 10px",
                fontSize: 12,
                color: "var(--text-muted)",
              }}
            >
              Loading workflows...
            </div>
          )}

      {/* Error State */}
      {error && (
        <div
          style={{
            padding: "12px 10px",
            fontSize: 12,
            color: "var(--red)",
          }}
        >
          {error}
        </div>
      )}

      {/* Workflow Items */}
      {!loading &&
        !error &&
        workflows.map((wf) => (
          <div
            key={wf}
            onClick={() => onWorkflowClick(wf)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "11px 12px",
              borderRadius: "var(--radius)",
              fontSize: 13.5,
              color:
                activeWorkflow === wf
                  ? "var(--accent)"
                  : "var(--text-secondary)",
              background:
                activeWorkflow === wf
                  ? "var(--accent-light)"
                  : "transparent",
              fontWeight: activeWorkflow === wf ? 500 : 400,
              cursor: "pointer",
              marginBottom: 4,
              transition:
                "background var(--transition), color var(--transition)",
              fontFamily: "var(--font)",
            }}
            onMouseEnter={(e) => {
              if (activeWorkflow !== wf) {
                e.currentTarget.style.background = "var(--surface-2)";
                e.currentTarget.style.color = "var(--text-primary)";
              }
            }}
            onMouseLeave={(e) => {
              if (activeWorkflow !== wf) {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.color = "var(--text-secondary)";
              }
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                opacity: activeWorkflow === wf ? 1 : 0.72,
              }}
            >
              <svg
                width="16" height="16" viewBox="0 0 24 24"
                fill="none"
                stroke={activeWorkflow === wf ? "var(--accent)" : "#8A93C7"}
                strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
              >
                <rect x="2.5" y="2.5" width="7" height="7" rx="1.5"/>
                <rect x="14.5" y="14.5" width="7" height="7" rx="1.5"/>
                <path d="M9.5 6h4a4 4 0 0 1 4 4v4.5"/>
                <path d="M14.5 18h-4a4 4 0 0 1-4-4V9.5"/>
              </svg>
            </div>

            <span>{wf}</span>
          </div>
        ))}
    </div>
  </aside>
  );
}