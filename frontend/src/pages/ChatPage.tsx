import { useEffect, useMemo, useRef, useState } from "react";

import {
  askQuestion,
  askQuestionStream,
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

type Props = {
  activeCollectionId: string;
};

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

export default function ChatPage({ activeCollectionId }: Props) {
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<number | undefined>(undefined);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessions, setSessions] = useState<ChatSessionItem[]>([]);
  const [showSessions, setShowSessions] = useState(true);
  const [loading, setLoading] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [error, setError] = useState("");

  const chatStreamRef = useRef<HTMLDivElement | null>(null);
  const streamAbortRef = useRef<AbortController | null>(null);

  const scopeIds = useMemo(
    () => (activeCollectionId === "all" ? ["all"] : [activeCollectionId]),
    [activeCollectionId],
  );

  const cancelActiveStream = () => {
    if (streamAbortRef.current) {
      streamAbortRef.current.abort();
      streamAbortRef.current = null;
    }
  };

  const appendAssistantDelta = (delta: string) => {
    setMessages((prev) => {
      if (prev.length === 0) {
        return [{ role: "assistant", content: delta }];
      }
      const next = [...prev];
      const lastIndex = next.length - 1;
      if (next[lastIndex].role !== "assistant") {
        next.push({ role: "assistant", content: delta });
        return next;
      }
      next[lastIndex] = {
        ...next[lastIndex],
        content: `${next[lastIndex].content}${delta}`,
      };
      return next;
    });
  };

  const setAssistantTail = (content: string) => {
    setMessages((prev) => {
      if (prev.length === 0) {
        return [{ role: "assistant", content }];
      }
      const next = [...prev];
      const lastIndex = next.length - 1;
      if (next[lastIndex].role !== "assistant") {
        next.push({ role: "assistant", content });
        return next;
      }
      next[lastIndex] = { ...next[lastIndex], content };
      return next;
    });
  };

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
    cancelActiveStream();
    try {
      const res = await getChatSessionMessages(targetSessionId);
      const nextMessages: Message[] = res.items.map((item: ChatMessageItem) => ({
        role: item.role,
        content: item.content,
      }));
      setSessionId(targetSessionId);
      setMessages(nextMessages);
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

  useEffect(() => {
    return () => {
      cancelActiveStream();
    };
  }, []);

  const onNewSession = () => {
    cancelActiveStream();
    setSessionId(undefined);
    setMessages([]);
    setError("");
  };

  const onDeleteSession = async () => {
    if (!sessionId) {
      return;
    }
    cancelActiveStream();
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
    cancelActiveStream();
    try {
      await clearChatSessionMessages(sessionId);
      setMessages([]);
      await loadSessions(false);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const onSubmit = async () => {
    if (!input.trim()) {
      return;
    }

    cancelActiveStream();

    const question = input.trim();
    setInput("");
    setError("");
    setMessages((prev) => [...prev, { role: "user", content: question }, { role: "assistant", content: "" }]);
    setLoading(true);

    const controller = new AbortController();
    streamAbortRef.current = controller;

    let streamMeta: ChatAskResponse | null = null;
    let hasDelta = false;

    try {
      await askQuestionStream(question, sessionId, scopeIds, {
        signal: controller.signal,
        onDelta: (delta) => {
          hasDelta = true;
          appendAssistantDelta(delta);
        },
        onMeta: (meta) => {
          streamMeta = meta;
          setSessionId(meta.session_id);
        },
      });

      if (!streamMeta && !hasDelta) {
        const fallback = await askQuestion(question, sessionId, scopeIds);
        setSessionId(fallback.session_id);
        setAssistantTail(fallback.answer);
      }

      await loadSessions(false);
    } catch (err) {
      if (controller.signal.aborted) {
        return;
      }

      const streamError = (err as Error).message;
      if (!hasDelta) {
        try {
          const fallback = await askQuestion(question, sessionId, scopeIds);
          setSessionId(fallback.session_id);
          setAssistantTail(fallback.answer);
          await loadSessions(false);
        } catch (fallbackErr) {
          setError((fallbackErr as Error).message || streamError);
          setAssistantTail("请求失败，请稍后重试。");
        }
      } else {
        setError(streamError);
      }
    } finally {
      if (streamAbortRef.current === controller) {
        streamAbortRef.current = null;
      }
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
          </div>

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
