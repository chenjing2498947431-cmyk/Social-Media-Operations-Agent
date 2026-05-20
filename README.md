# 金融自媒体运营 Agent

基于 **LangGraph** 的金融自媒体内容生产 Agent：从「每日金融热点」出发，自动完成 **选题 → 写稿 → 审核 → 配图** 全流程，并在选题与审核两个环节引入 **人工介入（Human-in-the-Loop）**，由运营人员拍板。

文本与配图均接入 **火山方舟（Ark）大模型**；工作流状态通过 LangGraph Checkpointer 持久化到 PostgreSQL，支持中断恢复、进程重启不丢状态。

---

## 功能特性

- **多节点 Agent 工作流**：选题生成 → 人工选题 → 长文撰写 → 人工审核 → 改写循环 → 图片文案提炼 → 文生图。
- **人工介入**：基于 LangGraph `interrupt()`，工作流会在选题、审核两处暂停，等待运营人员决策后恢复。
- **真实大模型接入**：文本用火山方舟语言模型，配图用 `doubao-seedream` 文生图；可一键切回 Mock 模式离线跑通。
- **状态持久化**：LangGraph Checkpointer 落库 PostgreSQL，工作流可跨进程恢复。
- **前后端分离**：FastAPI 后端 + React/Ant Design 运营后台。

---

## 架构总览

三个独立服务：

| 服务 | 端口 | 职责 |
|---|---|---|
| `ai_service` | 8100 | LangGraph 工作流引擎，暴露薄 HTTP 接口 |
| `backend_api` | 8000 | 业务后台：campaign 落库、状态映射、桥接 AI 服务 |
| `frontend` | 5173 | 运营后台界面（React + Ant Design） |

数据流：

```
前端 (5173)  ──HTTP──▶  backend_api (8000)  ──HTTP──▶  ai_service (8100)
                              │                              │
                              ▼                              ▼
                     业务库 (SQLite/PG)           LangGraph Checkpointer (PG)
                     campaigns / content_assets   checkpoints / blobs / writes ...
```

### 工作流（LangGraph StateGraph）

```
START
  └─▶ generate_topics        Node A  生成 5 个备选选题
  └─▶ human_select_topic     Node B  【中断】等待人工选题
  └─▶ generate_article       Node C  根据选题撰写长文
  └─▶ human_review_article   Node D  【中断】等待人工审核
        ├─ reject ─▶ revise_article  Node E  按反馈改写 ─▶ 回到 Node D
        └─ approve ─▶ extract_image_content  Node F  提炼图片文案
                   └─▶ generate_images       Node G  文生图
                   └─▶ END
```

工作流阶段（`stage` / campaign `status`）：

| ai_service stage | campaign status | 含义 |
|---|---|---|
| `awaiting_topic` | `pending_topic` | 等待人工选题 |
| `awaiting_review` | `pending_review` | 等待人工审核草稿 |
| `running` | `generating` | 节点执行中 |
| `completed` | `completed` | 已完成，含正文与配图 |
| `failed` | `failed` | 执行失败 |

---

## 技术栈

**后端**：Python 3.11+ · FastAPI · LangGraph 1.x · SQLAlchemy 2.x (async) · Pydantic 2.x · openai SDK（接火山方舟）· psycopg / asyncpg

**前端**：React 18 · TypeScript · Vite 6 · Ant Design 5 · TanStack Query 5 · React Router 6 · axios · react-markdown

---

## 目录结构

```
Social-Media-Operations-Agent/
├── ai_service/              # LangGraph 工作流服务 (:8100)
│   ├── core/config.py       # 配置 (pydantic-settings)
│   ├── graph/
│   │   ├── builder.py       # StateGraph 组装
│   │   ├── state.py         # AgentState 定义
│   │   ├── nodes/           # 选题 / 写稿 / 审核 / 出图 节点
│   │   └── edges/           # 条件边（审核后路由）
│   ├── tools/
│   │   ├── llm_client.py    # 火山方舟文本模型封装
│   │   ├── image_gen_api.py # 火山方舟文生图封装
│   │   └── web_search.py    # 联网搜索（预留）
│   ├── prompts/             # Prompt 配置 (YAML)
│   ├── persistence/         # LangGraph Checkpointer
│   ├── routers/             # 工作流 HTTP 接口
│   └── main.py
├── backend_api/             # 业务后台服务 (:8000)
│   ├── core/                # 配置 + 数据库会话
│   ├── models/              # SQLAlchemy 模型 (campaign / content_asset)
│   ├── routers/             # campaigns / health
│   ├── services/            # 业务编排 + ai_service 客户端
│   └── main.py
├── frontend/                # React + Ant Design 前端 (:5173)
│   └── src/
│       ├── api/             # 接口封装
│       ├── hooks/           # React Query hooks
│       ├── pages/           # 任务列表页 / 详情页
│       └── components/      # 向导步骤组件
├── shared_libs/schemas/     # 前后端共享 Pydantic schema
├── scripts/                 # 冒烟测试脚本
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## 环境要求

- Python **3.11+**
- Node.js **18+**（前端）
- PostgreSQL（生产 / checkpoint 持久化；本地验证可省略）
- 火山方舟 API Key（真实大模型调用；Mock 模式可省略）

---

## 快速开始（本地开发）

### 1. 安装后端依赖

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置环境变量

复制示例文件并按需修改：

```bash
cp .env.example .env
```

最小可运行配置（Mock 模式，无需任何外部服务）：

```ini
USE_MOCK_LLM=true
USE_MOCK_IMAGE=true
LANGGRAPH_CHECKPOINT_DSN=          # 留空 → 内存 checkpointer
DATABASE_URL=sqlite+aiosqlite:///./backend.db
```

接入真实大模型与持久化（生产模式）：

```ini
USE_MOCK_LLM=false
USE_MOCK_IMAGE=false
ARK_API_KEY=你的火山方舟 API Key
LANGGRAPH_CHECKPOINT_DSN=postgresql://用户名:密码@主机:5432/数据库名
```

### 3. 启动后端服务

在项目根目录分别启动（两个终端）：

```bash
# AI 工作流服务
uvicorn ai_service.main:app --host 0.0.0.0 --port 8100 --reload

# 业务后台服务
uvicorn backend_api.main:app --host 0.0.0.0 --port 8000 --reload
```

- ai_service Swagger：http://localhost:8100/docs
- backend_api Swagger：http://localhost:8000/docs

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

打开 **http://localhost:5173** 即可使用。前端开发服务器已配置代理，`/api` 自动转发到 `backend_api`（8000）。

---

## 配置说明（`.env`）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `BACKEND_API_HOST` / `BACKEND_API_PORT` | `0.0.0.0` / `8000` | 业务后台监听地址 |
| `AI_SERVICE_HOST` / `AI_SERVICE_PORT` | `0.0.0.0` / `8100` | AI 服务监听地址 |
| `AI_SERVICE_BASE_URL` | `http://localhost:8100` | backend_api 调用 AI 服务的地址 |
| `DATABASE_URL` | `sqlite+aiosqlite:///./backend.db` | 业务库 DSN（SQLAlchemy） |
| `LANGGRAPH_CHECKPOINT_DSN` | 空 | LangGraph checkpoint 的 Postgres DSN；留空则用内存 checkpointer（重启丢状态） |
| `USE_MOCK_LLM` | `true` | `false` 走真实语言模型 |
| `USE_MOCK_IMAGE` | `true` | `false` 走真实文生图 |
| `ARK_API_KEY` | 空 | 火山方舟 API Key（`USE_MOCK_*=false` 时必填） |
| `ARK_BASE_URL` | `https://ark.cn-beijing.volces.com/api/v3` | 火山方舟接口地址 |
| `ARK_MODEL` | `ep-...` | 语言模型的推理接入点 ID |
| `ARK_IMAGE_MODEL` | `doubao-seedream-4-5-251128` | 文生图模型 |
| `CORS_ALLOW_ORIGINS` | `["*"]` | 允许跨域的前端来源，生产可收敛 |

> `.env` 含密钥，已被 `.gitignore` 忽略，请勿提交。

---

## API 概览

### backend_api（业务主入口，推荐）

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/campaigns` | 创建任务并启动工作流 |
| `GET` | `/api/v1/campaigns` | 列出所有任务 |
| `GET` | `/api/v1/campaigns/{id}` | 任务详情（含最新 workflow_state） |
| `POST` | `/api/v1/campaigns/{id}/select-topic` | 提交人工选定的选题 |
| `POST` | `/api/v1/campaigns/{id}/review-article` | 提交审核结果（approve / reject + feedback） |
| `GET` | `/healthz` | 健康检查 |

### ai_service（LangGraph 薄接口，便于单独调试）

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/ai/v1/workflows` | 启动工作流 |
| `POST` | `/ai/v1/workflows/{thread_id}/resume` | 恢复中断（选题 / 审核） |
| `GET` | `/ai/v1/workflows/{thread_id}/state` | 查询工作流状态 |
| `GET` | `/healthz` | 健康检查 |

---

## 数据存储

**业务库**（`backend_api`，SQLAlchemy）：

- `campaigns`：运营任务（context、status、thread_id 等）
- `content_assets`：最终产出（正文、图片文案、图片 URL）

**LangGraph Checkpointer**（`ai_service`）：

- 配置了 `LANGGRAPH_CHECKPOINT_DSN` → `AsyncPostgresSaver`，启动时自动建表
  `checkpoints` / `checkpoint_blobs` / `checkpoint_writes` / `checkpoint_migrations`
- 留空 → `InMemorySaver`，状态仅存内存，**进程重启即丢失**，仅适合本地快速验证

> 注意：业务库与 checkpoint 库是两套独立存储，可以是不同的数据库。

---

## Docker 部署

`docker-compose.yml` 内置 PostgreSQL 并编排三方依赖：

```bash
docker compose up --build
```

默认以 **Mock 模式** 启动（`USE_MOCK_LLM/IMAGE=true`）。接入真实大模型需在 compose 文件的 `ai_service.environment` 中补充 `ARK_API_KEY` 等变量并将 `USE_MOCK_*` 设为 `false`。

---

## 冒烟测试

```bash
# 不启 HTTP，直接驱动 LangGraph 跑完整流程
python -m scripts.smoke_graph

# 经由 HTTP 接口跑通流程
python -m scripts.smoke_http
```

---

## 备注

- 真实文生图返回的是带签名的临时 URL（约 24 小时失效）；若需长期保存，应下载转存至自有对象存储。
- 当前为内网运营工具定位，未内置鉴权；如需对外暴露请自行补充登录层。
