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
        width: 72, height: 72,
        borderRadius: 20,
        background: "linear-gradient(135deg, var(--accent) 0%, var(--accent-mid) 100%)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        boxShadow: "var(--accent-glow)",
        marginBottom: 26,
      }}>
                 <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                   <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                 </svg>

      </div>
      
      {/* Title */}
      <div style={{
        fontSize: 27,
        fontWeight: 700,
        color: "var(--text-primary)",
        marginBottom: 10,
        letterSpacing: "-0.6px",
      }}>
        Ask about any telecom workflow
      </div>

      {/* Description */}
      <div style={{
        fontSize: 14.5,
        color: "var(--text-secondary)",
        textAlign: "center",
        maxWidth: 420,
        lineHeight: 1.65,
        marginBottom: 30,
      }}>
        Query steps, approval chains, actors, edge cases, and process
        details across all indexed workflows.
      </div>

      {/* Suggestion grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 12,
        width: "100%",
        maxWidth: 600,
      }}>
        {SUGGESTIONS.map(s => (
          <button
            key={s}
            onClick={() => onSuggestionClick(s)}
            style={{
              padding: "15px 18px",
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-xl)",
              fontSize: 13.5,
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
