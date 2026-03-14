import { useState } from "react";

import ChatPage from "./pages/ChatPage";
import FavoritesPage from "./pages/FavoritesPage";
import LoginPage from "./pages/LoginPage";

type Tab = "login" | "favorites" | "chat";

export default function App() {
  const [tab, setTab] = useState<Tab>("login");

  return (
    <div className="app-shell">
      <header className="topbar">
        <h1>抖音收藏夹 RAG</h1>
        <nav>
          <button className={tab === "login" ? "active" : ""} onClick={() => setTab("login")}>
            登录
          </button>
          <button
            className={tab === "favorites" ? "active" : ""}
            onClick={() => setTab("favorites")}
          >
            收藏入库
          </button>
          <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>
            对话问答
          </button>
        </nav>
      </header>

      <main>
        {tab === "login" ? <LoginPage /> : null}
        {tab === "favorites" ? <FavoritesPage /> : null}
        {tab === "chat" ? <ChatPage /> : null}
      </main>
    </div>
  );
}
