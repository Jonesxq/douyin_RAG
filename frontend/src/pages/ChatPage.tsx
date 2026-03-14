import { useState } from "react";

import { askQuestion, type ChatResponse } from "../api";

type Message = {
  role: "user" | "assistant";
  content: string;
};

export default function ChatPage() {
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<number | undefined>(undefined);
  const [messages, setMessages] = useState<Message[]>([]);
  const [lastResponse, setLastResponse] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const onSubmit = async () => {
    if (!input.trim()) return;

    const question = input.trim();
    setInput("");
    setError("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);

    try {
      const res = await askQuestion(question, sessionId);
      setSessionId(res.session_id);
      setLastResponse(res);
      setMessages((prev) => [...prev, { role: "assistant", content: res.answer }]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="panel chat-panel">
      <h2>对话问答</h2>
      <p className="muted">默认优先总结/对比风格回答。</p>

      <div className="chat-box">
        {messages.map((msg, idx) => (
          <div key={`${msg.role}-${idx}`} className={`chat-item chat-${msg.role}`}>
            <strong>{msg.role === "user" ? "你" : "助手"}</strong>
            <p>{msg.content}</p>
          </div>
        ))}
        {messages.length === 0 ? <p className="muted">还没有消息，先问一个问题。</p> : null}
      </div>

      <div className="row">
        <input
          className="chat-input"
          placeholder="输入问题，例如：帮我总结收藏里关于增长策略的核心观点"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSubmit();
            }
          }}
        />
        <button onClick={onSubmit} disabled={loading}>
          {loading ? "生成中..." : "发送"}
        </button>
      </div>

      {error ? <p className="error">{error}</p> : null}

      {lastResponse ? (
        <div className="meta">
          <span>Session: {lastResponse.session_id}</span>
          <span>Latency: {lastResponse.latency_ms}ms</span>
          <span>Hits: {lastResponse.hits.length}</span>
        </div>
      ) : null}
    </section>
  );
}
