import { useEffect, useState } from "react";

import { getLoginStatus, logoutLogin, startLogin, type LoginStatus } from "./api";
import ChatPage from "./pages/ChatPage";
import FavoritesPage from "./pages/FavoritesPage";
import LoginPage from "./pages/LoginPage";

type View = "home" | "workspace";
type ThemeMode = "night" | "day";

export default function App() {
  const [view, setView] = useState<View>("home");
  const [status, setStatus] = useState<LoginStatus>({ status: "idle", message: "" });
  const [loadingLogin, setLoadingLogin] = useState(false);
  const [loadingLogout, setLoadingLogout] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [activeCollectionId, setActiveCollectionId] = useState("all");
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => {
    const saved = window.localStorage.getItem("theme_mode");
    return saved === "day" ? "day" : "night";
  });

  const refreshStatus = async () => {
    try {
      const data = await getLoginStatus();
      setStatus(data);
      if (data.status === "logged_in") {
        setView("workspace");
      }
    } catch (err) {
      setLoginError((err as Error).message);
    }
  };

  useEffect(() => {
    void refreshStatus();
  }, []);

  useEffect(() => {
    if (status.status !== "pending") {
      return;
    }
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible") {
        return;
      }
      void refreshStatus();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [status.status]);

  useEffect(() => {
    document.body.classList.toggle("theme-day", themeMode === "day");
    window.localStorage.setItem("theme_mode", themeMode);
  }, [themeMode]);

  const onLogout = async () => {
    setLoginError("");
    setLoadingLogout(true);
    try {
      await logoutLogin();
      setView("home");
      await refreshStatus();
    } catch (err) {
      setLoginError((err as Error).message);
    } finally {
      setLoadingLogout(false);
    }
  };

  const onStartLogin = async () => {
    setLoginError("");
    setLoadingLogin(true);
    try {
      await startLogin();
      await refreshStatus();
    } catch (err) {
      setLoginError((err as Error).message);
    } finally {
      setLoadingLogin(false);
    }
  };

  return (
    <div className="bm-root">
      <header className="bm-topbar">
        <div className="brand">
          <div className="brand-icon" aria-hidden="true">
            ◈
          </div>
          <div>
            <h1>douyinRAG</h1>
          </div>
        </div>

        <div className="theme-center">
          <button
            className="theme-icon-btn"
            onClick={() => setThemeMode((value) => (value === "night" ? "day" : "night"))}
            aria-label={themeMode === "night" ? "切换到白天模式" : "切换到夜晚模式"}
            title={themeMode === "night" ? "切换到白天模式" : "切换到夜晚模式"}
          >
            {themeMode === "night" ? "🌙" : "☀"}
          </button>
        </div>

        <div className="top-actions">
          <button className={view === "home" ? "ghost active" : "ghost"} onClick={() => setView("home")}>
            首页
          </button>
          <button className={view === "workspace" ? "ghost active" : "ghost"} onClick={() => setView("workspace")}>
            工作台
          </button>
          {status.status === "logged_in" ? (
            <>
              <span className="login-chip">已登录</span>
              <button className="ghost" onClick={() => void onLogout()} disabled={loadingLogout}>
                {loadingLogout ? "退出中..." : "退出登录"}
              </button>
            </>
          ) : (
            <button className="primary" onClick={() => void onStartLogin()} disabled={loadingLogin}>
              {loadingLogin ? "启动中..." : "扫码登录"}
            </button>
          )}
        </div>
      </header>

      <main className="bm-main">
        {view === "home" ? (
          <LoginPage
            status={status}
            loading={loadingLogin}
            error={loginError}
            onStartLogin={onStartLogin}
            onOpenWorkspace={() => setView("workspace")}
          />
        ) : (
          <section className="workspace-grid">
            <FavoritesPage
              activeCollectionId={activeCollectionId}
              onActiveCollectionChange={setActiveCollectionId}
            />
            <ChatPage activeCollectionId={activeCollectionId} />
          </section>
        )}
      </main>

      <footer className="bm-footer">douyinRAG © 2026 · 仅处理你本人可访问收藏内容</footer>
    </div>
  );
}
