export default function TypingIndicator() {
  return (
    <div style={{ padding: "6px 32px" }}>

      {/* Role label */}
      <div style={{
        fontSize: 10.5,
        fontWeight: 600,
        letterSpacing: "0.4px",
        textTransform: "uppercase",
        color: "var(--text-muted)",
        display: "flex",
        alignItems: "center",
        gap: 6,
        marginBottom: 5,
      }}>
        <div style={{
          width: 18, height: 18,
          borderRadius: 4,
          background: "var(--surface-3)",
          color: "var(--accent)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 9,
          fontWeight: 700,
        }}>
          AI
        </div>
        Navigator
      </div>

      {/* Dots bubble */}
      <div style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        padding: "12px 16px",
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-lg)",
        borderBottomLeftRadius: 4,
        boxShadow: "var(--shadow-sm)",
      }}>
        {[0, 0.2, 0.6].map((delay, i) => (
          <div
            key={i}
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: "var(--accent-mid)",
              animation: `typingPulse 1.4s ease-in-out ${delay}s infinite`,
            }}
          />
        ))}
      </div>

      <style>{`
        @keyframes typingPulse {
          0%, 60%, 100% { opacity: 0.2; transform: scale(0.8); }
          30% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  );
}