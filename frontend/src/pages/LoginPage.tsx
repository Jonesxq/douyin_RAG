import type { LoginStatus } from "../api";

type Props = {
  status: LoginStatus;
  loading: boolean;
  error: string;
  onStartLogin: () => Promise<void>;
  onOpenWorkspace: () => void;
};

export default function LoginPage({ status, loading, error, onStartLogin, onOpenWorkspace }: Props) {
  return (
    <section className="hero-panel">
      <h2>douyinRAG</h2>
      <p className="hero-sub">不让你的收藏视频在收藏夹里吃灰。</p>

      <div className="hero-actions">
        <button className="primary" onClick={() => void onStartLogin()} disabled={loading}>
          {loading ? "启动中..." : "扫码登录"}
        </button>
        <button className="ghost" onClick={onOpenWorkspace}>
          打开工作台
        </button>
      </div>

      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}
