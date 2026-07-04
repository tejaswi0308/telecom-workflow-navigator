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
      width: "var(--sidebar-w)",
      background: "var(--surface)",
      borderRight: "1px solid var(--border)",
      display: "flex",
      flexDirection: "column",
      overflow: "hidden",
      flexShrink: 0,
    }}
  >
    {/* New Chat Button */}
    <div style={{ padding: "14px 12px 10px" }}>
      <button
        onClick={onNewChat}
        style={{
          width: "100%",
          padding: "9px 14px",
          background:
            "linear-gradient(135deg, var(--accent) 0%, var(--accent-mid) 100%)",
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
        <img
          src="https://img.icons8.com/?size=100&id=1501&format=png&color=ffffff"
          alt="New Chat"
          width="16"
          height="16"
        />
        New chat
      </button>
    </div>

    {/* Divider */}
    <div
      style={{
        height: 1,
        background: "var(--border)",
        margin: "0 12px",
      }}
    />

    {/* Workflows Label */}
    <div style={{ padding: "14px 16px 6px" }}>
      <div
        style={{
          fontSize: 10,
          fontWeight: 600,
          letterSpacing: "0.9px",
          textTransform: "uppercase",
          color: "var(--text-muted)",
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
        padding: "2px 8px 16px",
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
              gap: 9,
              padding: "8px 10px",
              borderRadius: "var(--radius)",
              fontSize: 12.5,
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
              marginBottom: 1,
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
                background:
                  activeWorkflow === wf
                    ? "var(--accent-light)"
                    : "var(--surface-2)",
                border: `1px solid ${
                  activeWorkflow === wf
                    ? "var(--accent-mid)"
                    : "var(--border)"
                }`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                padding: "6px",
                borderRadius: "6px",
              }}
            >
              <img
                src="https://img.icons8.com/?size=100&id=14115&format=png&color=545ead"
                alt="Workflow"
                width="16"
                height="16"
              />
            </div>

            <span>{wf}</span>
          </div>
        ))}
    </div>
  </aside>
  );
}