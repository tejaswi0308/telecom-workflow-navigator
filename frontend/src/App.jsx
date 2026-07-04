import { useState } from "react";
import Header from "./components/Header.jsx";
import Sidebar from "./components/Sidebar.jsx";
import ChatArea from "./components/ChatArea.jsx";

export default function App() {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeWorkflow, setActiveWorkflow] = useState(null);

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
        body: JSON.stringify({ question, top_k: 8 }),
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
    sendMessage(`Tell me about the ${wf} workflow`);
  }

  async function handleNewChat() {
    // Clear frontend state
    setMessages([]);
    setActiveWorkflow(null);

    // Clear server-side memory so next conversation
    // starts with a completely clean context window
    try {
      await fetch("/api/history", { method: "DELETE" });
    } catch {
      // non-critical — UI is already cleared
      console.warn("Could not clear server-side chat history.");
    }
  }

  async function handleFeedback(feedback) {
    try {
      await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message_id: String(feedback.messageId),
          type: feedback.type,
          comment: feedback.comment || null,
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
      flexDirection: "column",
      height: "100vh",
      overflow: "hidden",
    }}>
      <Header />

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <Sidebar
          activeWorkflow={activeWorkflow}
          onWorkflowClick={handleWorkflowClick}
          onNewChat={handleNewChat}
        />

        <ChatArea
          messages={messages}
          loading={loading}
          onSend={sendMessage}
          onFeedback={handleFeedback}
        />
      </div>
    </div>
  );
}