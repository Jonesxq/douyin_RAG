# Douyin Favorites RAG

个人版“抖音收藏夹 RAG 知识库”本地项目：扫码登录抖音后手动同步收藏夹，按收藏夹一键入库（音频转写 -> 切块 -> Chroma 向量），再进行对话问答。

<img width="1846" height="786" alt="image" src="https://github.com/user-attachments/assets/595d088e-04d0-4f54-b13e-0b688f20641c" />

[点击这里观看视频](https://www.bilibili.com/video/BV1bhw2zvEXa?vd_source=91cc575981e4f125145bd5e62cf1f8e3)
## 技术栈

- Frontend: React + Vite + TypeScript + CSS
- Backend: FastAPI + SQLAlchemy + SQLite
- Vector DB: ChromaDB (本地持久化)
- ASR: faster-whisper (本地)
- LLM/Embedding: Qwen OpenAI-compatible + 本地 Embedding（默认 `BAAI/bge-small-zh-v1.5`）
- Python 依赖管理: uv


## 项目结构

```text
backend/
  app/
    main.py                 # FastAPI 入口
    api/
      router.py             # 路由聚合
      routes/
        auth.py             # 登录与状态
        favorites.py        # 收藏夹同步与查询
        knowledge.py        # 入库任务与统计
        chat.py             # 问答与会话管理
    core/
      config.py             # 配置与路径归一化
      startup_checks.py     # 启动自检
      logging.py            # 日志配置
    db/
      base.py               # ORM Base
      session.py            # Engine / Session
      init_db.py            # 建表与重建存储
    models/
      entities.py           # 数据表实体定义
    schemas/
      dto.py                # API DTO
    services/
      douyin_collector.py   # 抖音登录与收藏抓取
      favorites_service.py  # 收藏差异同步
      knowledge_service.py  # 入库任务执行
      media_service.py      # 音频下载与抽取
      asr_service.py        # 本地 ASR
      text_processing.py    # 清洗与切块
      chroma_service.py     # 向量库操作
      llm_service.py        # Qwen/Embedding 客户端
      rag_service.py        # 检索与答案生成
      worker.py             # 后台任务队列
frontend/
  src/
    App.tsx                 # 页面总入口
    pages/                  # 首页/工作台页面
    api.ts                  # 前后端 API 调用封装
```

## 环境准备

### 1) Python 3.12 + 后端依赖

```powershell
$env:UV_CACHE_DIR="E:\code\douyin_rag\.uv-cache"
uv sync --project backend --python 3.12
```

### 2) 安装 Playwright 浏览器

```powershell
$env:UV_CACHE_DIR="E:\code\douyin_rag\.uv-cache"
$env:PLAYWRIGHT_BROWSERS_PATH="E:\code\douyin_rag\backend\storage\playwright-browsers"
uv run --project backend playwright install chromium
```

### 3) 安装 ffmpeg（并加入 PATH）

Windows 可用 gyan.dev 的 `ffmpeg-git-essentials.7z`。

### 4) 配置环境变量

```powershell
Copy-Item backend/.env.example backend/.env
```

至少配置：

- `QWEN_API_KEY`
- `QWEN_BASE_URL`
- `QWEN_CHAT_MODEL`

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

## 清库重建（SQLite + Chroma）

```powershell
uv run --project backend python backend/scripts/rebuild_storage.py
```

## Docker 镜像

推送到 `main` 分支后，CI 的后端检查和前端构建都通过时，GitHub Actions 会构建并发布两个镜像到 GitHub Container Registry（GHCR）：

- 后端：`ghcr.io/jonesxq/douyin-rag-backend`
- 前端：`ghcr.io/jonesxq/douyin-rag-frontend`

每个镜像会带有 `latest` 和 `sha-<提交号>` 两个标签。当前工作流只构建并发布镜像，不会部署到服务器。GHCR 新建镜像包默认是私有的，可在仓库关联的 Packages 页面调整可见性。

运行容器时，需要把后端的 `/data` 挂载到持久化目录，并通过环境变量提供 Qwen 配置。SQLite、Chroma 数据、Playwright 登录状态和模型缓存都保存在该目录下。
前端镜像通过 Docker 网络中的 `backend:8000` 访问后端，因此两个容器运行时需要加入同一个 Docker 网络。

注意：当前抖音登录流程会在运行后端的机器上打开可见浏览器窗口，前端没有二维码截图接口。因此镜像可以构建和启动，但无桌面的容器环境暂时不能通过网页完成首次扫码登录；后续需要改造扫码展示流程或预先提供登录状态。

### 自动部署到本机 Docker Desktop

GitHub Actions 在主分支推送后运行 CI 并发布镜像。本机部署器每 5 分钟检查 GHCR 的 `latest` 镜像，有新镜像时执行 `docker compose up -d` 更新容器。部署后可在 `http://localhost:8080` 打开前端；后端数据保存在 Docker 命名卷 `douyin-rag-data` 中。部署日志保存在 `%LOCALAPPDATA%\DouyinRAG\deploy.log`。更新部署脚本后，重新运行安装脚本会停止旧任务并重启它。

本仓库是公开仓库。GitHub 提醒公开仓库的 self-hosted runner 可能被 fork PR 的工作流利用并在本机执行代码，因此这里不把本机注册为 GitHub runner；本地部署器只拉取 GHCR 镜像，不运行仓库的 Actions 工作流。

首次使用时，在 Docker Desktop 启用 Linux containers，并按顺序完成：

1. GHCR 镜像包默认私有。创建一个仅有 `read:packages` 权限的 GitHub classic personal access token，然后登录 GHCR。Token 只输入到 Docker 的登录提示，不要写进仓库文件。

   ```powershell
   # 登录 GHCR；按提示输入 Jonesxq 和有 read:packages 权限的 Token
   docker login ghcr.io -u Jonesxq
   ```

2. 在仓库目录运行安装脚本，它会把 Compose 文件和本地轮询脚本复制到 `%LOCALAPPDATA%\DouyinRAG`，生成 `.env` 配置模板，并创建当前 Windows 用户登录时启动的计划任务：

   ```powershell
   # 注册并立即启动本机镜像轮询任务
   powershell -ExecutionPolicy Bypass -File scripts/install-local-deploy-task.ps1
   ```

3. 编辑 `%LOCALAPPDATA%\DouyinRAG\.env`，填入 `QWEN_API_KEY`（没有也可启动，但问答功能不可用）。部署器每 5 分钟读取一次配置并检查镜像。

电脑需要保持开机、用户已登录且 Docker Desktop 正在运行，才能拉取和更新镜像。计划任务允许在电池供电时启动和继续运行。扫码登录仍受上文限制：当前无桌面容器不能展示首次登录二维码。

## 新 API

- `POST /auth/douyin/login/start`
- `GET /auth/douyin/login/status`
- `POST /favorites/sync`
- `GET /favorites/collections`
- `GET /favorites/collections/{collection_id}/videos?page=&size=`
- `POST /knowledge/sync`
- `GET /knowledge/sync/{task_id}`
- `GET /knowledge/stats`
- `POST /chat/ask`
- `POST /chat/ask/stream`

## 说明

- 收藏抓取仅使用抖音收藏夹接口链路（收藏夹列表 + 收藏夹视频列表），不再使用全页 DOM 抓取兜底。
- 同步与入库均为手动触发，避免页面自动膨胀和无效轮询。
- 媒体处理采用“仅音频”主链路，不保留完整视频文件。

