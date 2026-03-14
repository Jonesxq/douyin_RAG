import { useEffect, useMemo, useState } from "react";

import {
  createIngestJobs,
  getFavorites,
  getIngestJob,
  type FavoriteItem,
  type IngestJob,
} from "../api";

export default function FavoritesPage() {
  const [items, setItems] = useState<FavoriteItem[]>([]);
  const [page, setPage] = useState(1);
  const [size] = useState(20);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<Record<number, boolean>>({});
  const [jobs, setJobs] = useState<IngestJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setError("");
    setLoading(true);
    try {
      const data = await getFavorites(page, size);
      setItems(data.items);
      setTotal(data.total);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [page, size]);

  useEffect(() => {
    if (jobs.length === 0) return;
    const timer = window.setInterval(async () => {
      const updated = await Promise.all(jobs.map((job) => getIngestJob(job.id).catch(() => job)));
      setJobs(updated);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [jobs]);

  const selectedIds = useMemo(
    () => Object.keys(selected).filter((id) => selected[Number(id)]).map(Number),
    [selected],
  );

  const onToggle = (id: number) => {
    setSelected((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const onBatchIngest = async () => {
    if (selectedIds.length === 0) {
      setError("请先勾选要入库的收藏项");
      return;
    }

    setError("");
    try {
      const data = await createIngestJobs(selectedIds);
      setJobs((prev) => [...data.jobs, ...prev]);
      setSelected({});
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <section className="panel">
      <h2>收藏夹列表</h2>
      <div className="row">
        <button onClick={load} disabled={loading}>
          {loading ? "同步中..." : "同步收藏"}
        </button>
        <button onClick={onBatchIngest}>勾选项入库</button>
      </div>

      {error ? <p className="error">{error}</p> : null}

      <table className="table">
        <thead>
          <tr>
            <th></th>
            <th>ID</th>
            <th>标题</th>
            <th>状态</th>
            <th>链接</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>
                <input
                  type="checkbox"
                  checked={!!selected[item.id]}
                  onChange={() => onToggle(item.id)}
                />
              </td>
              <td>{item.platform_item_id}</td>
              <td>{item.title}</td>
              <td>{item.ingest_status}</td>
              <td>
                <a href={item.url} target="_blank" rel="noreferrer">
                  打开
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="row">
        <button onClick={() => setPage((v) => Math.max(1, v - 1))} disabled={page <= 1}>
          上一页
        </button>
        <span>
          第 {page} 页 / 共 {Math.max(1, Math.ceil(total / size))} 页
        </span>
        <button onClick={() => setPage((v) => v + 1)} disabled={page >= Math.ceil(total / size)}>
          下一页
        </button>
      </div>

      <h3>入库任务</h3>
      <ul className="job-list">
        {jobs.map((job) => (
          <li key={job.id}>
            <span>Job #{job.id}</span>
            <span className={`badge badge-${job.status}`}>{job.status}</span>
            <span>{job.step}</span>
            {job.error_msg ? <span className="error">{job.error_msg}</span> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
