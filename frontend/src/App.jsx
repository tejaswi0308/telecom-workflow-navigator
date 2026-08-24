import { Routes, Route } from "react-router-dom";
import LandingPage from "./components/home_page/landing_page.jsx";
import ChatPage from "./components/chat_interface/ChatPage.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/chat" element={<ChatPage />} />
    </Routes>
  );
}
