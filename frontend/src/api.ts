export type LoginStatus = {
  status: "idle" | "pending" | "logged_in" | "failed";
  message: string;
};

export type FavoriteItem = {
  id: number;
  platform_item_id: string;
  url: string;
  title: string;
  author: string;
  duration_sec: number | null;
  fav_time: string | null;
  ingest_status: string;
};

export type FavoriteListResponse = {
  items: FavoriteItem[];
  page: number;
  size: number;
  total: number;
};

export type IngestJob = {
  id: number;
  source_item_id: number;
  status: string;
  step: string;
  error_msg: string;
  retry_count: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type CreateIngestJobsResponse = {
  jobs: IngestJob[];
};

export type ChunkHit = {
  chunk_id: number;
  source_item_id: number;
  score: number;
  text: string;
};

export type ChatResponse = {
  session_id: number;
  answer: string;
  latency_ms: number;
  hits: ChunkHit[];
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

export function startLogin(): Promise<{ started: boolean; message: string }> {
  return request("/auth/douyin/login/start", { method: "POST" });
}

export function getLoginStatus(): Promise<LoginStatus> {
  return request("/auth/douyin/login/status");
}

export function getFavorites(page = 1, size = 20): Promise<FavoriteListResponse> {
  return request(`/douyin/favorites?page=${page}&size=${size}&sync=true`);
}

export function createIngestJobs(itemIds: number[]): Promise<CreateIngestJobsResponse> {
  return request("/ingest/jobs", {
    method: "POST",
    body: JSON.stringify({ item_ids: itemIds }),
  });
}

export function getIngestJob(jobId: number): Promise<IngestJob> {
  return request(`/ingest/jobs/${jobId}`);
}

export function askQuestion(query: string, sessionId?: number): Promise<ChatResponse> {
  return request("/chat/query", {
    method: "POST",
    body: JSON.stringify({ query, session_id: sessionId ?? null }),
  });
}
