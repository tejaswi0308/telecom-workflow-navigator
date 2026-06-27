import MessageFeedback from "./MessageFeedback.jsx";
import Sources from "./Sources.jsx";

function formatTime(date) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function MessageBubble({ message, onFeedback }) {
  const isUser = message.role === "user";

  return (
    <div>
      {/* Message group */}
      <div style={{
        padding: "4px 32px",
        display: "flex",
        flexDirection: "column",
        alignItems: isUser ? "flex-end" : "flex-start",
      }}>

        {/* Role label */}
        <div style={{
          fontSize: 10.5,
          fontWeight: 600,
          letterSpacing: "0.4px",
          textTransform: "uppercase",
          color: isUser ? "var(--accent)" : "var(--text-muted)",
          display: "flex",
          alignItems: "center",
          gap: 6,
          marginBottom: 5,
          flexDirection: isUser ? "row-reverse" : "row",
        }}>
          {/* Avatar */}
          <div style={{
            width: 18, height: 18,
            borderRadius: 4,
            background: isUser
              ? "linear-gradient(135deg, var(--accent), var(--accent-mid))"
              : "var(--surface-3)",
            color: isUser ? "#fff" : "var(--accent)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 9,
            fontWeight: 700,
          }}>
            {isUser ? "U" : "AI"}
          </div>
          {isUser ? "You" : "Navigator"}
        </div>

        {/* Bubble */}
        <div style={{
          maxWidth: "72%",
          padding: "13px 17px",
          fontSize: 14,
          lineHeight: 1.65,
          background: isUser
            ? "linear-gradient(135deg, var(--accent) 0%, var(--accent-mid) 100%)"
            : "var(--surface)",
          color: isUser ? "#fff" : "var(--text-primary)",
          borderRadius: isUser
            ? "var(--radius-lg) var(--radius-lg) 4px var(--radius-lg)"
            : "var(--radius-lg) var(--radius-lg) var(--radius-lg) 4px",
          border: isUser ? "none" : "1px solid var(--border)",
          boxShadow: isUser ? "var(--shadow-md)" : "var(--shadow-sm)",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}>
          {message.text}
        </div>

        {/* Meta row — time + feedback */}
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginTop: 5,
          padding: "0 2px",
          flexDirection: isUser ? "row-reverse" : "row",
        }}>
          <span style={{ fontSize: 10.5, color: "var(--text-muted)" }}>
            {formatTime(message.time)}
          </span>
          {!isUser && (
            <MessageFeedback messageId={message.id} onFeedback={onFeedback} />
          )}
        </div>
      </div>

      {/* Sources — only for assistant */}
      {!isUser && message.sources?.length > 0 && (
        <Sources sources={message.sources} />
      )}
    </div>
  );
}   