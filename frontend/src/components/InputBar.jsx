import { useRef } from "react";

export default function InputBar({ onSend, loading }) {
  const textareaRef = useRef(null);

  function autoResize(e) {
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 140) + "px";
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleSend() {
    const value = textareaRef.current?.value.trim();
    if (!value || loading) return;
    onSend(value);
    textareaRef.current.value = "";
    textareaRef.current.style.height = "auto";
  }

  return (
    <div style={{
      padding: "14px 32px 18px",
      background: "var(--surface)",
      borderTop: "1px solid var(--border)",
      flexShrink: 0,
      boxShadow: "0 -4px 16px rgba(47,56,144,0.05)",
    }}>

      {/* Input outer */}
      <div
        style={{
          background: "var(--bg)",
          border: "1.5px solid var(--border)",
          borderRadius: "var(--radius-xl)",
          overflow: "hidden",
          transition: "border-color var(--transition), box-shadow var(--transition)",
        }}
        onFocusCapture={e => {
          e.currentTarget.style.borderColor = "var(--accent)";
          e.currentTarget.style.boxShadow = "0 0 0 4px rgba(47,56,144,0.08), var(--shadow-md)";
        }}
        onBlurCapture={e => {
          e.currentTarget.style.borderColor = "var(--border)";
          e.currentTarget.style.boxShadow = "none";
        }}
      >
        <div style={{
          display: "flex",
          alignItems: "flex-end",
          padding: "10px 12px 10px 16px",
          gap: 10,
        }}>
          <textarea
            ref={textareaRef}
            rows={1}
            placeholder="Ask about a workflow, approval chain, or process step..."
            onChange={autoResize}
            onKeyDown={handleKeyDown}
            style={{
              flex: 1,
              border: "none",
              background: "transparent",
              fontSize: 14,
              fontFamily: "var(--font)",
              color: "var(--text-primary)",
              resize: "none",
              outline: "none",
              maxHeight: 140,
              lineHeight: 1.55,
            }}
          />

          {/* Send button */}
          <button
            onClick={handleSend}
            disabled={loading}
            style={{
              width: 36, height: 36,
              borderRadius: 10,
              background: "linear-gradient(135deg, var(--accent) 0%, var(--accent-mid) 100%)",
              border: "none",
              cursor: loading ? "not-allowed" : "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
              alignSelf: "flex-end",
              boxShadow: "0 2px 8px rgba(47,56,144,0.30)",
              opacity: loading ? 0.35 : 1,
              transition: "opacity var(--transition), box-shadow var(--transition), transform var(--transition)",
            }}
            onMouseEnter={e => {
              if (!loading) {
                e.currentTarget.style.boxShadow = "0 4px 14px rgba(47,56,144,0.40)";
                e.currentTarget.style.transform = "translateY(-1px)";
              }
            }}
            onMouseLeave={e => {
              e.currentTarget.style.boxShadow = "0 2px 8px rgba(47,56,144,0.30)";
              e.currentTarget.style.transform = "translateY(0)";
            }}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5">
              <line x1="22" y1="2" x2="11" y2="13"/>
              <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
      </div>

      {/* Hint */}
      <div style={{
        fontSize: 11,
        color: "var(--text-muted)",
        marginTop: 8,
        textAlign: "center",
      }}>
      </div>
    </div>
  );
}