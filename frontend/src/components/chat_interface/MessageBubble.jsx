import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import MessageFeedback from "./MessageFeedback.jsx";
import Sources from "./Sources.jsx";

function formatTime(date) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// Maps markdown elements to inline styles that match the bubble's existing
// look (same font-size, spacing, and CSS variables used everywhere else).
const markdownComponents = {
  p: ({ children }) => (
    <p style={{ margin: "0 0 8px", lineHeight: 1.65 }}>{children}</p>
  ),
  h1: ({ children }) => (
    <h1 style={{ fontSize: 17, fontWeight: 700, margin: "12px 0 8px" }}>{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 style={{ fontSize: 15.5, fontWeight: 700, margin: "12px 0 6px" }}>{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 style={{ fontSize: 14.5, fontWeight: 600, margin: "10px 0 6px" }}>{children}</h3>
  ),
  strong: ({ children }) => (
    <strong style={{ fontWeight: 700 }}>{children}</strong>
  ),
  em: ({ children }) => <em style={{ fontStyle: "italic" }}>{children}</em>,
  ul: ({ children }) => (
    <ul style={{ margin: "4px 0 8px", paddingLeft: 20 }}>{children}</ul>
  ),
  ol: ({ children }) => (
    <ol style={{ margin: "4px 0 8px", paddingLeft: 20 }}>{children}</ol>
  ),
  li: ({ children }) => (
    <li style={{ margin: "3px 0", lineHeight: 1.6 }}>{children}</li>
  ),
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      style={{ color: "var(--accent)", textDecoration: "underline" }}
    >
      {children}
    </a>
  ),
  code: ({ inline, children }) =>
    inline ? (
      <code
        style={{
          background: "var(--surface-3)",
          padding: "1.5px 5px",
          borderRadius: 4,
          fontSize: 12.5,
          fontFamily: "monospace",
        }}
      >
        {children}
      </code>
    ) : (
      <pre
        style={{
          background: "var(--surface-3)",
          padding: "10px 12px",
          borderRadius: 8,
          overflowX: "auto",
          fontSize: 12.5,
          fontFamily: "monospace",
          margin: "6px 0",
        }}
      >
        <code>{children}</code>
      </pre>
    ),
  blockquote: ({ children }) => (
    <blockquote
      style={{
        margin: "8px 0",
        paddingLeft: 12,
        borderLeft: "3px solid var(--border)",
        color: "var(--text-muted)",
      }}
    >
      {children}
    </blockquote>
  ),
  hr: () => (
    <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "10px 0" }} />
  ),
  table: ({ children }) => (
    <div style={{ overflowX: "auto", margin: "8px 0" }}>
      <table style={{ borderCollapse: "collapse", fontSize: 13 }}>{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th
      style={{
        border: "1px solid var(--border)",
        padding: "6px 10px",
        textAlign: "left",
        background: "var(--surface-3)",
      }}
    >
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td style={{ border: "1px solid var(--border)", padding: "6px 10px" }}>{children}</td>
  ),
};

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
          whiteSpace: isUser ? "pre-wrap" : "normal",
          wordBreak: "break-word",
        }}>
          {isUser ? (
            message.text
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {message.text}
            </ReactMarkdown>
          )}
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

      {/* Sources */}
      {!isUser && message.sources?.length > 0 && (
        <Sources sources={message.sources} />
      )}
    </div>
  );
}