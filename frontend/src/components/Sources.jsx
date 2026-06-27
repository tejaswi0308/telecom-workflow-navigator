import { useState } from "react";

export default function Sources({ sources }) {
  const [open, setOpen] = useState(false);

  if (!sources || sources.length === 0) return null;

  return (
    <div style={{ padding: "2px 32px 8px" }}>

      {/* Toggle */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          fontSize: 11.5,
          color: "var(--text-muted)",
          display: "flex",
          alignItems: "center",
          gap: 5,
          padding: "3px 0",
          fontWeight: 500,
          fontFamily: "var(--font)",
        }}
      >
        <svg
          width="10" height="10" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth="2.5"
          style={{ transform: open ? "rotate(90deg)" : "rotate(0deg)", transition: "transform var(--transition)" }}
        >
          <polyline points="9 18 15 12 9 6"/>
        </svg>
        <span>{sources.length} source{sources.length > 1 ? "s" : ""} used</span>
      </button>

      {/* Chips */}
      {open && (
        <div style={{ marginTop: 7, display: "flex", flexWrap: "wrap", gap: 6 }}>
          {sources.map((src, i) => (
            <div
              key={i}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "4px 11px 4px 8px",
                borderRadius: 20,
                background: "var(--surface)",
                border: "1px solid var(--border-strong)",
                fontSize: 11,
                color: "var(--text-secondary)",
                fontWeight: 500,
                boxShadow: "var(--shadow-sm)",
              }}
            >
              {/* Dot */}
              <div style={{
                width: 6, height: 6,
                borderRadius: "50%",
                background: "var(--accent-mid)",
                flexShrink: 0,
              }} />

              <span>{src.workflow}</span>

              {src.score != null && (
                <span style={{
                  color: "var(--text-muted)",
                  fontFamily: "var(--font-mono)",
                  fontSize: 10,
                }}>
                  {typeof src.score === "number" ? src.score.toFixed(3) : src.score}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}