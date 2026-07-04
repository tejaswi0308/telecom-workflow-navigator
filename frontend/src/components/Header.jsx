export default function Header() {
  return (
    <header style={{
      height: "var(--header-h)",
      background: "var(--surface)",
      borderBottom: "1px solid var(--border)",
      display: "flex",
      alignItems: "center",
      padding: "34px 24px",
      boxShadow: "var(--shadow-sm)",
      zIndex: 20,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{
          width: 34, height: 34,
          background: "linear-gradient(135deg, var(--accent) 0%, var(--accent-mid) 100%)",
          borderRadius: 9,
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 2px 8px rgba(47,56,144,0.30)",
        }}>
          <img src="https://img.icons8.com/?size=100&id=QhlCcbzScElq&format=png&color=ffffff" alt="Logo" style={{ width: 20, height: 20 }} />
        </div>
        <div>
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)", letterSpacing: "-0.3px" }}>
            Telecom Workflow Navigator
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 1 }}>
            Operations Workflow Copilot 
          </div>
        </div>
      </div>
    </header>
  );
}