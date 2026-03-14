# Douyin Favorites RAG MVP

本项目实现个人版“抖音收藏夹 RAG 知识库”MVP：扫码登录抖音后同步收藏列表，勾选视频手动入库，完成音频转写、向量索引，并提供对话问答。

## 技术栈

- Frontend: React + Vite + TypeScript + CSS
- Backend: FastAPI + SQLAlchemy + SQLite
- Vector DB: ChromaDB (本地持久化)
- ASR: faster-whisper
- LLM/Embedding: Qwen (OpenAI compatible API)
- Python dependency manager: uv

## 目录结构

```text
backend/      FastAPI, 入库流水线, RAG 服务
frontend/     React Web UI
```

## 环境准备

### 1) 后端依赖（uv）

> 必须使用 Python 3.12（ChromaDB 在 Python 3.14 下存在兼容问题）。

```powershell
$env:UV_CACHE_DIR="E:\code\douyin_rag\.uv-cache"
uv sync --project backend --python 3.12
```

安装采集所需浏览器（Playwright Chromium）：

```powershell
$env:UV_CACHE_DIR="E:\code\douyin_rag\.uv-cache"
$env:PLAYWRIGHT_BROWSERS_PATH="E:\code\douyin_rag\backend\storage\playwright-browsers"
uv run --project backend playwright install chromium
```

系统需安装并加入 PATH：

- ffmpeg

### 2) 配置环境变量

```powershell
Copy-Item backend/.env.example backend/.env
```

编辑 `backend/.env`，至少配置：

- `QWEN_API_KEY`
- `QWEN_BASE_URL`
- `QWEN_CHAT_MODEL`
- `QWEN_EMBEDDING_MODEL`

> 默认使用 `SQLite + ChromaDB` 本地持久化，不需要额外启动数据库服务。

## 启动

### 后端

```powershell
$env:UV_CACHE_DIR="E:\code\douyin_rag\.uv-cache"
uv run --project backend uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir backend
```

### 前端

```powershell
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173`。

## API

- `POST /auth/douyin/login/start`
- `GET /auth/douyin/login/status`
- `GET /douyin/favorites?page=&size=&sync=true`
- `POST /ingest/jobs`
- `GET /ingest/jobs/{job_id}`
- `POST /chat/query`

## 说明

- 收藏抓取基于 Playwright 页面抓取，受抖音页面结构变化影响。
- 入库任务并发默认 `2`，可在 `.env` 调整 `INGEST_WORKER_CONCURRENCY`。
- 问答采用 Chroma 向量检索 + SQLite 关键词召回融合（RRF）。




