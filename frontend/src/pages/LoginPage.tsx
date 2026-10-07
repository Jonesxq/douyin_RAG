import type { LoginStatus } from "../api";

type Props = {
  status: LoginStatus;
  qrImageUrl: string | null;
  loading: boolean;
  error: string;
  onStartLogin: () => Promise<void>;
  onOpenWorkspace: () => void;
};

export default function LoginPage({ status, qrImageUrl, loading, error, onStartLogin, onOpenWorkspace }: Props) {
  return (
    <section className="hero-panel">
      <h2>douyinRAG</h2>
      <p className="hero-sub">不让你的收藏视频在收藏夹里吃灰。</p>

      <div className="hero-actions">
        <button
          className="primary"
          onClick={() => void onStartLogin()}
          disabled={loading || status.status === "pending"}
        >
          {loading ? "启动中..." : status.status === "pending" ? "等待扫码..." : "扫码登录"}
        </button>
        <button className="ghost" onClick={onOpenWorkspace}>
          打开工作台
        </button>
      </div>

      {status.status === "pending" ? (
        <section className="login-qr-card" aria-live="polite">
          <p>请使用抖音 App 扫描下方二维码完成登录。</p>
          {qrImageUrl ? (
            <img className="login-qr-image" src={qrImageUrl} alt="抖音扫码登录二维码" />
          ) : (
            <div className="login-qr-placeholder">正在获取二维码…</div>
          )}
          <p className="muted">{status.message || "等待扫码确认"}</p>
        </section>
      ) : null}

      {error || status.status === "failed" ? (
        <p className="error">{error || status.message}</p>
      ) : null}
    </section>
  );
}
