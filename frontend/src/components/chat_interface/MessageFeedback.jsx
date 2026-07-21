import { useState } from "react";

export default function MessageFeedback({ messageId, onFeedback }) {
  const [vote, setVote] = useState(null);
  const [showInput, setShowInput] = useState(false);
  const [commentText, setCommentText] = useState("");
  const [submitted, setSubmitted] = useState(false);

  function handleVote(type) {
    // If clicking the same vote again — deselect and reset
    if (vote === type) {
      setVote(null);
      setShowInput(false);
      return;
    }

    setVote(type);

    if (type === "up") {
      // Instantly submit for positive feedback, no comment box
      onFeedback({ messageId, type: "up", comment: null });
      setShowInput(false);
      setSubmitted(true);
    } else {
      // Open comment prompt for downvotes
      setShowInput(true);
      setSubmitted(false);
    }
  }

  function handleSubmit() {
    // Submit vote + optional comment
    onFeedback({
      messageId,
      type: vote,
      comment: commentText.trim() || null,
    });
    setShowInput(false);
    setSubmitted(true);
    setCommentText("");
  }

  function handleSkip() {
    // Submit vote only, no comment
    onFeedback({ messageId, type: vote, comment: null });
    setShowInput(false);
    setSubmitted(true);
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
      {/* Vote buttons */}
      <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
        <button
          style={{
            ...btnBase,  
            ...(vote === "up"
              ? { background: "var(--green-bg)", borderColor: "var(--green)" }
              : {}),
          }}
          onClick={() => handleVote("up")}
          title="Helpful"
          disabled={submitted}
        >
          👍
        </button>

        <button
          style={{
            ...btnBase,
            ...(vote === "down"
              ? { background: "var(--red-bg)", borderColor: "var(--red)" }
              : {}),
          }}
          onClick={() => handleVote("down")}
          title="Not helpful"
          disabled={submitted}
        >
          👎
        </button>

        {submitted && (
          <span style={{
            fontSize: 11,
            color: "var(--green)",
            marginLeft: 4,
            display: "flex",
            alignItems: "center",
            gap: 3,
          }}>
            Thanks for your feedback {":)"}
          </span>
        )}
      </div>

      {/* Comment prompt — only triggers for downvotes now */}
      {showInput && (
        <div style={{
          marginTop: 8,
          maxWidth: "480px",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-lg)",
          overflow: "hidden",
          boxShadow: "var(--shadow-md)",
        }}>
          <div style={{ padding: "12px 14px" }}>
            <div style={{
              fontSize: 12,
              color: "var(--text-secondary)",
              marginBottom: 8,
              lineHeight: 1.4,
            }}>
              Sorry about that. What could be improved? (optional)
            </div>
            <textarea
              rows={2}
              placeholder="Add a comment..."
              value={commentText}
              onChange={e => setCommentText(e.target.value)}
              autoFocus
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
              onKeyDown={e => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit();
                }
              }}
            />
          </div>

          <div style={{
            display: "flex",
            gap: 8,
            padding: "8px 14px",
            justifyContent: "flex-end",
            borderTop: "1px solid var(--border)",
            background: "var(--surface-2)",
          }}>
            <button
              onClick={handleSkip}
              style={{
                background: "none",
                color: "var(--text-secondary)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                padding: "5px 12px",
                fontSize: 12,
                cursor: "pointer",
                fontFamily: "var(--font)",
              }}
            >
              Skip
            </button>
            <button
              onClick={handleSubmit}
              style={{
                background: "var(--accent)",
                color: "#fff",
                border: "none",
                borderRadius: "var(--radius)",
                padding: "5px 16px",
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