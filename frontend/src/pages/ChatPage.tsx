import { useEffect, useMemo, useRef, useState } from "react";

import {
  askQuestion,
  clearChatSessionMessages,
  deleteChatSession,
  getChatSessionMessages,
  listChatSessions,
  type ChatAskResponse,
  type ChatMessageItem,
  type ChatSessionItem,
} from "../api";

type Message = {
  role: "user" | "assistant";
  content: string;
};

const LIST_LINE_RE = /^(\d+[.)、]|[-*•])\s+/;

function normalizeAssistantBlocks(content: string): string[] {
  const normalized = content.replace(/\r\n/g, "\n").trim();
  if (!normalized) {
    return [];
  }

  return normalized
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);
}

function normalizeAssistantParagraph(block: string): string {
  const lines = block
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length === 0) {
    return "";
  }

  const isList = lines.every((line) => LIST_LINE_RE.test(line));
  if (isList) {
    return lines.join("\n");
  }

  return lines.join(" ");
}

type Props = {
  activeCollectionId: string;
};

export default function ChatPage({ activeCollectionId }: Props) {
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<number | undefined>(undefined);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessions, setSessions] = useState<ChatSessionItem[]>([]);
  const [showSessions, setShowSessions] = useState(true);
  const [lastResponse, setLastResponse] = useState<ChatAskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [error, setError] = useState("");
  const chatStreamRef = useRef<HTMLDivElement | null>(null);

  const scopeIds = useMemo(
    () => (activeCollectionId === "all" ? ["all"] : [activeCollectionId]),
    [activeCollectionId],
  );

  const loadSessions = async (autoOpenLatest = false) => {
    setLoadingSessions(true);
    try {
      const res = await listChatSessions(30);
      setSessions(res.items);
      if (autoOpenLatest && res.items.length > 0) {
        await onSelectSession(res.items[0].id);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoadingSessions(false);
    }
  };

  const onSelectSession = async (targetSessionId: number) => {
    try {
      const res = await getChatSessionMessages(targetSessionId);
      const nextMessages: Message[] = res.items.map((item: ChatMessageItem) => ({
        role: item.role,
        content: item.content,
      }));
      setSessionId(targetSessionId);
      setMessages(nextMessages);
      setLastResponse(null);
      setError("");
    } catch (err) {
      setError((err as Error).message);
    }
  };

  useEffect(() => {
    void loadSessions(true);
  }, []);

  useEffect(() => {
    if (!chatStreamRef.current) {
      return;
    }
    chatStreamRef.current.scrollTop = chatStreamRef.current.scrollHeight;
  }, [messages, loading]);

  const onNewSession = () => {
    setSessionId(undefined);
    setMessages([]);
    setLastResponse(null);
    setError("");
  };

  const onDeleteSession = async () => {
    if (!sessionId) {
      return;
    }
    try {
      await deleteChatSession(sessionId);
      onNewSession();
      await loadSessions(false);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const onClearMessages = async () => {
    if (!sessionId) {
      return;
    }
    try {
      await clearChatSessionMessages(sessionId);
      setMessages([]);
      setLastResponse(null);
      await loadSessions(false);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const onSubmit = async () => {
    if (!input.trim()) {
      return;
    }

    const question = input.trim();
    setInput("");
    setError("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);

    try {
      const response = await askQuestion(question, sessionId, scopeIds);
      setSessionId(response.session_id);
      setLastResponse(response);
      setMessages((prev) => [...prev, { role: "assistant", content: response.answer }]);
      await loadSessions(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const canSubmit = input.trim().length > 0 && !loading;

  return (
    <section className="workspace-card chat-card">
      <div className="card-head">
        <div>
          <h2>对话工作台</h2>
          <p>当前范围：{activeCollectionId === "all" ? "全部收藏" : `收藏夹 ${activeCollectionId}`}</p>
        </div>
        <div className="card-actions">
          <button className="ghost" onClick={() => setShowSessions((value) => !value)}>
            {showSessions ? "隐藏会话栏" : "显示会话栏"}
          </button>
        </div>
      </div>

      <div className={showSessions ? "chat-layout" : "chat-layout chat-layout-solo"}>
        {showSessions ? (
          <aside className="chat-sessions">
            <div className="chat-sessions-head">
              <strong>会话记录</strong>
              <button className="ghost" onClick={onNewSession}>
                新建
              </button>
            </div>

            <div className="chat-session-list">
              {loadingSessions ? <p className="muted">加载中...</p> : null}
              {sessions.map((item) => (
                <button
                  key={item.id}
                  className={item.id === sessionId ? "chat-session-item active" : "chat-session-item"}
                  onClick={() => void onSelectSession(item.id)}
                >
                  <strong>{item.title || `会话 ${item.id}`}</strong>
                  <span>
                    {item.message_count} 条 · {item.last_message_at ? new Date(item.last_message_at).toLocaleString() : "无"}
                  </span>
                </button>
              ))}
              {!loadingSessions && sessions.length === 0 ? <p className="muted">暂无会话记录</p> : null}
            </div>

            <div className="chat-session-actions">
              <button className="ghost wide" onClick={() => void onClearMessages()} disabled={!sessionId}>
                清空当前会话
              </button>
              <button className="ghost wide" onClick={() => void onDeleteSession()} disabled={!sessionId}>
                删除当前会话
              </button>
            </div>
          </aside>
        ) : null}

        <div className="chat-main">
          <div ref={chatStreamRef} className="chat-stream">
            {messages.length === 0 ? (
              <div className="chat-item chat-assistant">
                <p>
                  你可以直接问：
                  <br />
                  1) 这个收藏夹主要讲了什么
                  <br />
                  2) 列出收藏里和某主题相关的视频
                  <br />
                  3) 基于收藏内容给我行动清单
                </p>
              </div>
            ) : null}

            {messages.map((message, index) => (
              <div key={`${message.role}-${index}`} className={`chat-item chat-${message.role}`}>
                {message.role === "assistant" ? (
                  <div className="chat-rich">
                    {normalizeAssistantBlocks(message.content).map((block, blockIndex) => {
                      const paragraph = normalizeAssistantParagraph(block);
                      if (!paragraph) {
                        return null;
                      }

                      if (paragraph.includes("\n")) {
                        return (
                          <ul key={blockIndex} className="chat-rich-list">
                            {paragraph.split("\n").map((line, lineIndex) => (
                              <li key={`${blockIndex}-${lineIndex}`}>{line.replace(LIST_LINE_RE, "")}</li>
                            ))}
                          </ul>
                        );
                      }

                      return <p key={blockIndex}>{paragraph}</p>;
                    })}
                  </div>
                ) : (
                  <p>{message.content}</p>
                )}
              </div>
            ))}

            {loading ? (
              <div className="chat-item chat-assistant">
                <p>正在整理答案...</p>
              </div>
            ) : null}
          </div>

          {lastResponse ? (
            <div className="chat-meta">
              <span>会话: {lastResponse.session_id}</span>
              <span>耗时: {lastResponse.latency_ms}ms</span>
              <span>命中: {lastResponse.hits.length}</span>
            </div>
          ) : null}

          {error ? <p className="error">{error}</p> : null}

          <div className="chat-input-row">
            <textarea
              className="chat-input"
              rows={3}
              placeholder="输入问题（Enter 发送，Shift+Enter 换行）"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  if (canSubmit) {
                    void onSubmit();
                  }
                }
              }}
            />
            <button className="primary" onClick={() => void onSubmit()} disabled={!canSubmit}>
              {loading ? "生成中..." : "发送"}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
