export type LoginStatus = {
  status: "idle" | "pending" | "logged_in" | "failed";
  message: string;
};

export type FavoriteCollection = {
  id: number;
  collection_id: string;
  title: string;
  item_count: number;
  is_active: boolean;
};

export type FavoriteCollectionsResponse = {
  items: FavoriteCollection[];
};

export type FavoriteVideo = {
  id: number;
  collection_id: string;
  platform_item_id: string;
  url: string;
  title: string;
  author: string;
  duration_sec: number | null;
  status: string;
};

export type FavoriteVideosResponse = {
  items: FavoriteVideo[];
  page: number;
  size: number;
  total: number;
};

export type FavoritesSyncResponse = {
  collections_total: number;
  videos_total: number;
  added_videos: number;
  removed_videos: number;
};

export type SyncTask = {
  id: number;
  task_type: string;
  collection_id: string | null;
  status: string;
  step: string;
  progress_total: number;
  progress_done: number;
  message: string;
  error_msg: string;
  retry_count: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type KnowledgeSyncResponse = {
  tasks: SyncTask[];
};

export type KnowledgeStats = {
  total_collections: number;
  total_videos: number;
  processed_videos: number;
  total_chunks: number;
};

export type ChatHit = {
  chunk_id: string;
  platform_item_id: string;
  title: string;
  score: number;
  text: string;
};

export type ChatAskResponse = {
  session_id: number;
  route_type: string;
  answer: string;
  latency_ms: number;
  hits: ChatHit[];
};

export type ChatSessionItem = {
  id: number;
  title: string;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
};

export type ChatSessionsResponse = {
  items: ChatSessionItem[];
};

export type ChatMessageItem = {
  id: number;
  session_id: number;
  role: "user" | "assistant";
  content: string;
  route_type: string;
  created_at: string;
};

export type ChatMessagesResponse = {
  session_id: number;
  items: ChatMessageItem[];
};

export type ChatStreamHandlers = {
  onDelta: (text: string) => void;
  onMeta?: (meta: ChatAskResponse) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
  signal?: AbortSignal;
};

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

function parseSseEvent(rawBlock: string): { event: string; payload: unknown } | null {
  const lines = rawBlock
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) {
    return null;
  }

  let event = "message";
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  const rawData = dataLines.join("\n");
  if (!rawData) {
    return { event, payload: {} };
  }

  try {
    return { event, payload: JSON.parse(rawData) };
  } catch {
    return { event, payload: { text: rawData } };
  }
}

export async function askQuestionStream(
  query: string,
  sessionId: number | undefined,
  collectionIds: string[] | undefined,
  handlers: ChatStreamHandlers,
): Promise<void> {
  const response = await fetch(`${API_BASE}/chat/ask/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      query,
      session_id: sessionId ?? null,
      collection_ids: collectionIds ?? null,
    }),
    signal: handlers.signal,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed: ${response.status}`);
  }

  if (!response.body) {
    throw new Error("Stream is not available");
  }

  const decoder = new TextDecoder("utf-8");
  const reader = response.body.getReader();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });

    while (true) {
      const splitIndex = buffer.indexOf("\n\n");
      if (splitIndex < 0) {
        break;
      }

      const block = buffer.slice(0, splitIndex);
      buffer = buffer.slice(splitIndex + 2);

      const parsed = parseSseEvent(block);
      if (!parsed) {
        continue;
      }

      if (parsed.event === "delta") {
        const payload = parsed.payload as { text?: string };
        if (payload.text) {
          handlers.onDelta(payload.text);
        }
        continue;
      }

      if (parsed.event === "meta") {
        handlers.onMeta?.(parsed.payload as ChatAskResponse);
        continue;
      }

      if (parsed.event === "done") {
        handlers.onDone?.();
        continue;
      }

      if (parsed.event === "error") {
        const payload = parsed.payload as { message?: string };
        const message = payload.message || "Stream request failed";
        handlers.onError?.(message);
        throw new Error(message);
      }
    }
  }
}

export function startLogin(): Promise<{ started: boolean; message: string }> {
  return request("/auth/douyin/login/start", { method: "POST" });
}

export function getLoginStatus(): Promise<LoginStatus> {
  return request("/auth/douyin/login/status");
}

export function logoutLogin(): Promise<{ success: boolean; message: string }> {
  return request("/auth/douyin/login/logout", { method: "POST" });
}

export function syncFavorites(): Promise<FavoritesSyncResponse> {
  return request("/favorites/sync", { method: "POST" });
}

export function getCollections(): Promise<FavoriteCollectionsResponse> {
  return request("/favorites/collections");
}

export function getCollectionVideos(collectionId: string, page = 1, size = 20): Promise<FavoriteVideosResponse> {
  return request(`/favorites/collections/${encodeURIComponent(collectionId)}/videos?page=${page}&size=${size}`);
}

export function createKnowledgeSync(collectionIds: string[]): Promise<KnowledgeSyncResponse> {
  return request("/knowledge/sync", {
    method: "POST",
    body: JSON.stringify({ collection_ids: collectionIds }),
  });
}

export function getKnowledgeTask(taskId: number): Promise<SyncTask> {
  return request(`/knowledge/sync/${taskId}`);
}

export function getKnowledgeStats(): Promise<KnowledgeStats> {
  return request("/knowledge/stats");
}

export function askQuestion(query: string, sessionId?: number, collectionIds?: string[]): Promise<ChatAskResponse> {
  return request("/chat/ask", {
    method: "POST",
    body: JSON.stringify({
      query,
      session_id: sessionId ?? null,
      collection_ids: collectionIds ?? null,
    }),
  });
}

export function listChatSessions(limit = 30): Promise<ChatSessionsResponse> {
  return request(`/chat/sessions?limit=${limit}`);
}

export function getChatSessionMessages(sessionId: number): Promise<ChatMessagesResponse> {
  return request(`/chat/sessions/${sessionId}/messages`);
}

export function deleteChatSession(sessionId: number): Promise<{ deleted: boolean }> {
  return request(`/chat/sessions/${sessionId}`, { method: "DELETE" });
}

export function clearChatSessionMessages(sessionId: number): Promise<{ cleared: boolean }> {
  return request(`/chat/sessions/${sessionId}/messages`, { method: "DELETE" });
}
