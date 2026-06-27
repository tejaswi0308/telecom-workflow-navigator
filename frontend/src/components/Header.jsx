export default function Header() {
  return (
    <header style={{
      height: "var(--header-h)",
      background: "var(--surface)",
      borderBottom: "1px solid var(--border)",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      padding: "0 24px",
      boxShadow: "var(--shadow-sm)",
      zIndex: 20,
      flexShrink: 0,
    }}>
      {/* Brand */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{
          width: 34, height: 34,
          background: "linear-gradient(135deg, var(--accent) 0%, var(--accent-mid) 100%)",
          borderRadius: 9,
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 2px 8px rgba(47,56,144,0.30)",
        }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.2">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
        </div>
        <div>
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)", letterSpacing: "-0.3px" }}>
            Workflow Navigator
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 1 }}>
            Telecom Process Intelligence
          </div>
        </div>
      </div>

      {/* Status */}
      <div style={{
        display: "flex", alignItems: "center", gap: 6,
        fontSize: 12, color: "var(--text-secondary)",
        background: "var(--surface-2)", border: "1px solid var(--border)",
        padding: "4px 10px", borderRadius: 20,
      }}>
        <div style={{
          width: 7, height: 7, borderRadius: "50%",
          background: "var(--green)",
          boxShadow: "0 0 0 2px var(--green-bg)",
        }} />
        <span>Index ready</span>
      </div>
    </header>
  );
}