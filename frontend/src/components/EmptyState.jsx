import { SUGGESTIONS } from "../constants/index.js";

export default function EmptyState({ onSuggestionClick }) {
  return (
    <div style={{
      flex: 1,
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      padding: "40px 20px",
      gap: 0,
    }}>

      {/* Icon */}
      <div style={{
        width: 64, height: 64,
        borderRadius: 18,
        background: "linear-gradient(135deg, var(--accent) 0%, var(--accent-mid) 100%)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        boxShadow: "0 8px 28px rgba(47,56,144,0.30)",
        marginBottom: 20,
      }}>
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="1.8">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
      </div>

      {/* Title */}
      <div style={{
        fontSize: 18,
        fontWeight: 600,
        color: "var(--text-primary)",
        marginBottom: 8,
        letterSpacing: "-0.4px",
      }}>
        Ask about any telecom workflow
      </div>

      {/* Description */}
      <div style={{
        fontSize: 13.5,
        color: "var(--text-secondary)",
        textAlign: "center",
        maxWidth: 360,
        lineHeight: 1.65,
        marginBottom: 24,
      }}>
        Query steps, approval chains, actors, edge cases, and process
        details across all indexed workflows.
      </div>

      {/* Suggestion grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 8,
        width: "100%",
        maxWidth: 540,
      }}>
        {SUGGESTIONS.map(s => (
          <button
            key={s}
            onClick={() => onSuggestionClick(s)}
            style={{
              padding: "10px 14px",
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-lg)",
              fontSize: 12.5,
              color: "var(--text-secondary)",
              cursor: "pointer",
              textAlign: "left",
              lineHeight: 1.4,
              boxShadow: "var(--shadow-sm)",
              fontFamily: "var(--font)",
              transition: "all var(--transition)",
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = "var(--accent)";
              e.currentTarget.style.color = "var(--accent)";
              e.currentTarget.style.background = "var(--accent-light)";
              e.currentTarget.style.boxShadow = "var(--shadow-md)";
              e.currentTarget.style.transform = "translateY(-1px)";
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = "var(--border)";
              e.currentTarget.style.color = "var(--text-secondary)";
              e.currentTarget.style.background = "var(--surface)";
              e.currentTarget.style.boxShadow = "var(--shadow-sm)";
              e.currentTarget.style.transform = "translateY(0)";
            }}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}