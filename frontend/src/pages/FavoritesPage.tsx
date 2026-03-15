import { useEffect, useMemo, useState } from "react";

import {
  createKnowledgeSync,
  getCollections,
  getCollectionVideos,
  getKnowledgeTask,
  syncFavorites,
  type FavoriteCollection,
  type FavoriteVideo,
  type SyncTask,
} from "../api";

const STATUS_LABELS: Record<string, string> = {
  pending: "待处理",
  processing: "处理中",
  running: "处理中",
  retry_scheduled: "重试中",
  success: "已入库",
  failed: "失败",
};

const ACTIVE_TASK_STATUSES = new Set(["pending", "running", "retry_scheduled"]);

type Props = {
  activeCollectionId: string;
  onActiveCollectionChange: (collectionId: string) => void;
};

export default function FavoritesPage({ activeCollectionId, onActiveCollectionChange }: Props) {
  const [collections, setCollections] = useState<FavoriteCollection[]>([]);
  const [videos, setVideos] = useState<FavoriteVideo[]>([]);
  const [page, setPage] = useState(1);
  const [size] = useState(12);
  const [total, setTotal] = useState(0);
  const [tasks, setTasks] = useState<SyncTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [error, setError] = useState("");
  const [lastSyncSummary, setLastSyncSummary] = useState("");

  const loadCollections = async () => {
    const res = await getCollections();
    setCollections(res.items);
    if (!res.items.find((item) => item.collection_id === activeCollectionId) && res.items.length > 0) {
      onActiveCollectionChange(res.items[0].collection_id);
    }
  };

  const loadVideos = async (collectionId = activeCollectionId, currentPage = page) => {
    const res = await getCollectionVideos(collectionId, currentPage, size);
    setVideos(res.items);
    setTotal(res.total);
  };

  const refreshLocal = async () => {
    setError("");
    setLoading(true);
    try {
      await loadCollections();
      await loadVideos();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refreshLocal();
  }, []);

  useEffect(() => {
    void (async () => {
      setError("");
      setLoading(true);
      try {
        await loadVideos(activeCollectionId, page);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, [activeCollectionId, page]);

  useEffect(() => {
    const activeTasks = tasks.filter((task) => ACTIVE_TASK_STATUSES.has(task.status));
    if (activeTasks.length === 0) {
      return;
    }

    const timer = window.setInterval(async () => {
      if (document.visibilityState !== "visible") {
        return;
      }

      const updates = await Promise.all(
        activeTasks.map(async (task) => {
          const next = await getKnowledgeTask(task.id).catch(() => task);
          return [task.id, next] as const;
        }),
      );
      const byId = new Map<number, SyncTask>(updates);
      setTasks((prev) => prev.map((task) => byId.get(task.id) ?? task));
      await loadVideos().catch(() => null);
    }, 5000);

    return () => window.clearInterval(timer);
  }, [tasks]);

  const onSync = async () => {
    setError("");
    setSyncing(true);
    try {
      const result = await syncFavorites();
      setLastSyncSummary(
        `已同步：收藏夹 ${result.collections_total}，视频 ${result.videos_total}，新增 ${result.added_videos}，移除 ${result.removed_videos}`,
      );
      setPage(1);
      await refreshLocal();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSyncing(false);
    }
  };

  const onIngestCollection = async () => {
    setError("");
    setIngesting(true);
    try {
      const payload = activeCollectionId === "all" ? [] : [activeCollectionId];
      const data = await createKnowledgeSync(payload);
      setTasks((prev) => [...data.tasks, ...prev]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIngesting(false);
    }
  };

  const pageCount = Math.max(1, Math.ceil(total / size));
  const currentCollection = useMemo(
    () => collections.find((item) => item.collection_id === activeCollectionId),
    [collections, activeCollectionId],
  );

  return (
    <section className="workspace-card favorites-card">
      <div className="card-head">
        <div>
          <h2>收藏夹</h2>
          <p>
            {currentCollection?.title ?? "全部收藏"} · {total} 条
          </p>
        </div>
        <div className="card-actions">
          <button className="ghost" onClick={() => void onSync()} disabled={syncing}>
            {syncing ? "同步中..." : "手动同步"}
          </button>
          <button className="primary" onClick={() => void onIngestCollection()} disabled={ingesting || loading}>
            {ingesting ? "入库中..." : "一键入库当前收藏夹"}
          </button>
        </div>
      </div>

      {collections.length > 0 ? (
        <div className="collection-list">
          {collections.map((collection) => (
            <button
              key={collection.collection_id}
              className={collection.collection_id === activeCollectionId ? "collection-chip active" : "collection-chip"}
              onClick={() => {
                setPage(1);
                onActiveCollectionChange(collection.collection_id);
              }}
            >
              {collection.title} ({collection.item_count})
            </button>
          ))}
        </div>
      ) : null}

      {lastSyncSummary ? <p className="muted">{lastSyncSummary}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      <div className="favorite-list">
        {videos.map((video) => (
          <article key={`${video.collection_id}-${video.platform_item_id}`} className="favorite-item">
            <div className="favorite-row no-checkbox">
              <div className="favorite-body">
                <strong>{video.title}</strong>
                <span>
                  {video.author || "未知作者"} · {video.platform_item_id}
                </span>
              </div>
              <span className={`status-pill status-${video.status}`}>{STATUS_LABELS[video.status] ?? video.status}</span>
            </div>
            <div className="favorite-meta">
              <a href={video.url} target="_blank" rel="noreferrer">
                打开原视频
              </a>
            </div>
          </article>
        ))}
        {videos.length === 0 ? <p className="muted">暂无收藏数据。请先点击“手动同步”。</p> : null}
      </div>

      <div className="card-foot">
        <div className="pager">
          <button onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={page <= 1}>
            上一页
          </button>
          <span>
            第 {page} / {pageCount} 页
          </span>
          <button onClick={() => setPage((value) => Math.min(pageCount, value + 1))} disabled={page >= pageCount}>
            下一页
          </button>
        </div>
      </div>

      <div className="job-feed">
        {tasks.slice(0, 6).map((task) => (
          <div key={task.id} className="job-item">
            <span>#{task.id}</span>
            <span>{task.status}</span>
            <span>
              {task.progress_done}/{task.progress_total} · {task.step}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

