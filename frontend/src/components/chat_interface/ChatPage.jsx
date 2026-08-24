import { useState, useEffect } from "react";
import Header from "./Header.jsx";
import Sidebar from "./Sidebar.jsx";
import ChatArea from "./ChatArea.jsx";

// ---------------------------------------------------------------------------
// sessionStorage keys — chat state persists across reloads within the SAME TAB only —
// closing the tab clears it (sessionStorage), and it also resets on
// "New Chat"
// ---------------------------------------------------------------------------
const SESSION_ID_KEY = "twn_session_id";
const MESSAGES_KEY = "twn_messages";
const ACTIVE_WORKFLOW_KEY = "twn_active_workflow";

function loadOrCreateSessionId() {
  let id = sessionStorage.getItem(SESSION_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(SESSION_ID_KEY, id);
  }
  return id;
}

function loadStoredMessages() {
  try {
    const raw = sessionStorage.getItem(MESSAGES_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // time was serialized as an ISO string — convert back to Date objects
    return parsed.map(m => ({ ...m, time: new Date(m.time) }));
  } catch {
    return [];
  }
}

function loadStoredActiveWorkflow() {
  return sessionStorage.getItem(ACTIVE_WORKFLOW_KEY) || null;
}

export default function ChatPage() {
  // Lazy initializers — run once on mount, read whatever was saved before reload
  const [sessionId, setSessionId] = useState(loadOrCreateSessionId);
  const [messages, setMessages] = useState(loadStoredMessages);
  const [loading, setLoading] = useState(false);
  const [activeWorkflow, setActiveWorkflow] = useState(loadStoredActiveWorkflow);

  // Persist messages whenever they change
  useEffect(() => {
    sessionStorage.setItem(MESSAGES_KEY, JSON.stringify(messages));
  }, [messages]);

  // Persist active workflow whenever it changes
  useEffect(() => {
    if (activeWorkflow) {
      sessionStorage.setItem(ACTIVE_WORKFLOW_KEY, activeWorkflow);
    } else {
      sessionStorage.removeItem(ACTIVE_WORKFLOW_KEY);
    }
  }, [activeWorkflow]);

  async function sendMessage(text) {
    const question = text.trim();
    if (!question || loading) return;

    const userMsg = {
      id: Date.now(),
      role: "user",
      text: question,
      time: new Date(),
    };

    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, session_id: sessionId }),
      });

      const data = await res.json();

      const assistantMsg = {
        id: Date.now() + 1,
        role: "assistant",
        text: data.answer || "No answer found.",
        sources: data.sources || [],
        time: new Date(),
      };

      setMessages(prev => [...prev, assistantMsg]);
    } catch {
      setMessages(prev => [
        ...prev,
        {
          id: Date.now() + 1,
          role: "assistant",
          text: "Could not reach the server. Make sure the backend is running.",
          sources: [],
          time: new Date(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleWorkflowClick(wf) {
    setActiveWorkflow(wf);
    sendMessage(`What are the steps in the ${wf} workflow?`);
  }

  function handleNewChat() {
    // Clear frontend state
    setMessages([]);
    setActiveWorkflow(null);

    // Clear persisted state so a reload doesn't bring the old chat back
    sessionStorage.removeItem(MESSAGES_KEY);
    sessionStorage.removeItem(ACTIVE_WORKFLOW_KEY);

    // Start a brand new Langfuse session for the next conversation. This
    // alone is enough to guarantee a clean context window — the new
    // session_id has no server-side memory file yet, so the no-history
    // guardrail in guardrails.py already sees "no prior conversation"
    // without anything needing to be deleted.
    //
    // Deliberately NOT calling DELETE /api/history for the ending session
    // anymore — that used to wipe the just-finished session's memory file
    // to [], which had no effect on the guardrail (it checks the NEW
    // session, not the old one) and only served to destroy that
    // conversation's saved transcript on disk. The old session's file is
    // now left untouched in memory/rag_memory_<old_session_id>.json.
    const newSessionId = crypto.randomUUID();
    sessionStorage.setItem(SESSION_ID_KEY, newSessionId);
    setSessionId(newSessionId);
  }

  async function handleFeedback(feedback) {
    // message_id is just a client-side Date.now() tag — meaningless on its
    // own. Look up the actual answer text, and the user question that came
    // right before it, so the feedback row in SQLite is self-explanatory.
    const assistantIndex = messages.findIndex(
      m => String(m.id) === String(feedback.messageId)
    );
    const answerMsg = assistantIndex !== -1 ? messages[assistantIndex] : null;

    let questionText = null;
    for (let i = assistantIndex - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        questionText = messages[i].text;
        break;
      }
    }

    try {
      await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message_id: String(feedback.messageId),
          type: feedback.type,
          comment: feedback.comment || null,
          session_id: sessionId,
          question: questionText,
          answer: answerMsg ? answerMsg.text : null,
        }),
      });
    } catch {
      // feedback is non-critical — silently ignore if it fails
      console.warn("Feedback submission failed:", feedback);
    }
  }

  return (
    <div style={{
      display: "flex",
      height: "100vh",
      overflow: "hidden",
    }}>
      <div style={{
        display: "flex",
        flexDirection: "column",
        width: "var(--sidebar-w)",
        flexShrink: 0,
        borderRight: "1px solid var(--border)",
        background: "var(--surface)",
      }}>
        <Header />

        <Sidebar
          activeWorkflow={activeWorkflow}
          onWorkflowClick={handleWorkflowClick}
          onNewChat={handleNewChat}
        />
      </div>

      <ChatArea
        messages={messages}
        loading={loading}
        onSend={sendMessage}
        onFeedback={handleFeedback}
      />
    </div>
  );
}