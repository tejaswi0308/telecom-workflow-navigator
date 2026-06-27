import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble.jsx";
import TypingIndicator from "./TypingIndicator.jsx";
import EmptyState from "./EmptyState.jsx";
import InputBar from "./InputBar.jsx";

export default function ChatArea({ messages, loading, onSend, onFeedback }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <main style={{
      flex: 1,
      display: "flex",
      flexDirection: "column",
      overflow: "hidden",
      minWidth: 0,
      background: "var(--bg)",
    }}>

      {/* Messages or Empty State */}
      {messages.length === 0 && !loading ? (
        <EmptyState onSuggestionClick={onSend} />
      ) : (
        <div style={{
          flex: 1,
          overflowY: "auto",
          padding: "28px 0 8px",
          display: "flex",
          flexDirection: "column",
        }}>
          {messages.map(msg => (
            <MessageBubble
              key={msg.id}
              message={msg}
              onFeedback={onFeedback}
            />
          ))}

          {loading && <TypingIndicator />}

          <div ref={bottomRef} />
        </div>
      )}

      {/* Input */}
      <InputBar onSend={onSend} loading={loading} />
    </main>
  );
}