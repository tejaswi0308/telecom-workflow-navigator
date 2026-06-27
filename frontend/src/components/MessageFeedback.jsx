import { useState } from "react";

export default function MessageFeedback({ messageId, onFeedback }) {
  const [vote, setVote] = useState(null);
  const [showComment, setShowComment] = useState(false);
  const [commentText, setCommentText] = useState("");
  const [submitted, setSubmitted] = useState(false);

  function handleVote(type) {
    const newVote = vote === type ? null : type;
    setVote(newVote);
    if (newVote) onFeedback({ messageId, type: newVote, comment: null });
  }

  function submitComment() {
    if (!commentText.trim()) return;
    onFeedback({ messageId, type: vote || "comment", comment: commentText });
    setShowComment(false);
    setSubmitted(true);
    setCommentText("");
  }

  const btnBase = {
    background: "none",
    border: "1px solid transparent",
    borderRadius: 6,
    padding: "3px 8px",
    fontSize: 13,
    cursor: "pointer",
    color: "var(--text-muted)",
    lineHeight: 1,
    fontFamily: "var(--font)",
    transition: "all var(--transition)",
  };

  return (
    <div>
      {/* Vote Row */}
      <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
        <button
          style={{
            ...btnBase,
            ...(vote === "up" ? { background: "var(--green-bg)", borderColor: "var(--green)" } : {}),
          }}
          onClick={() => handleVote("up")}
          title="Helpful"
        >👍</button>

        <button
          style={{
            ...btnBase,
            ...(vote === "down" ? { background: "var(--red-bg)", borderColor: "var(--red)" } : {}),
          }}
          onClick={() => handleVote("down")}
          title="Not helpful"
        >👎</button>

        <button
          style={{
            ...btnBase,
            ...(showComment ? { background: "var(--accent-light)", borderColor: "var(--accent)" } : {}),
          }}
          onClick={() => setShowComment(s => !s)}
          title="Add comment"
        >💬</button>

        {submitted && (
          <span style={{ fontSize: 11, color: "var(--green)", marginLeft: 4, display: "flex", alignItems: "center", gap: 3 }}>
            ✓ Saved
          </span>
        )}
      </div>

      {/* Comment Box */}
      {showComment && (
        <div style={{
          marginTop: 8,
          maxWidth: "72%",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-lg)",
          overflow: "hidden",
          boxShadow: "var(--shadow-md)",
        }}>
          <div style={{ padding: "12px 14px" }}>
            <div style={{
              fontSize: 11, fontWeight: 600,
              color: "var(--text-muted)",
              marginBottom: 8,
              letterSpacing: "0.3px",
              textTransform: "uppercase",
            }}>
              Your feedback
            </div>
            <textarea
              rows={3}
              placeholder="What could be improved?"
              value={commentText}
              onChange={e => setCommentText(e.target.value)}
              style={{
                width: "100%",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                padding: "8px 10px",
                fontSize: 13,
                fontFamily: "var(--font)",
                resize: "none",
                background: "var(--surface-2)",
                color: "var(--text-primary)",
                outline: "none",
                lineHeight: 1.5,
              }}
              onFocus={e => {
                e.target.style.borderColor = "var(--accent)";
                e.target.style.background = "var(--surface)";
              }}
              onBlur={e => {
                e.target.style.borderColor = "var(--border)";
                e.target.style.background = "var(--surface-2)";
              }}
            />
          </div>

          {/* Footer */}
          <div style={{
            display: "flex", gap: 8,
            padding: "10px 14px",
            justifyContent: "flex-end",
            borderTop: "1px solid var(--border)",
            background: "var(--surface-2)",
          }}>
            <button
              onClick={() => setShowComment(false)}
              style={{
                background: "none",
                color: "var(--text-secondary)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                padding: "6px 12px",
                fontSize: 12,
                cursor: "pointer",
                fontFamily: "var(--font)",
              }}
            >
              Cancel
            </button>
            <button
              onClick={submitComment}
              style={{
                background: "var(--accent)",
                color: "#fff",
                border: "none",
                borderRadius: "var(--radius)",
                padding: "6px 16px",
                fontSize: 12,
                fontWeight: 500,
                cursor: "pointer",
                fontFamily: "var(--font)",
              }}
            >
              Submit
            </button>
          </div>
        </div>
      )}
    </div>
  );
}