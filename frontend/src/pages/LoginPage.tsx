import { useEffect, useState } from "react";

import { getLoginStatus, startLogin, type LoginStatus } from "../api";

export default function LoginPage() {
  const [status, setStatus] = useState<LoginStatus>({ status: "idle", message: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const refreshStatus = async () => {
    try {
      const data = await getLoginStatus();
      setStatus(data);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  useEffect(() => {
    refreshStatus();
    const timer = window.setInterval(refreshStatus, 3000);
    return () => window.clearInterval(timer);
  }, []);

  const onStartLogin = async () => {
    setError("");
    setLoading(true);
    try {
      await startLogin();
      await refreshStatus();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="panel">
      <h2>抖音扫码登录</h2>
      <p className="muted">点击后会在本机打开浏览器，请在浏览器中扫码。</p>
      <button onClick={onStartLogin} disabled={loading}>
        {loading ? "启动中..." : "开始扫码登录"}
      </button>
      <div className="status">
        <span className={`badge badge-${status.status}`}>{status.status}</span>
        <span>{status.message || "等待操作"}</span>
      </div>
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}
