# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A **Financial Self-Media Operations AI Agent** that automates social media content production for financial topics. The pipeline is: Topic Selection → Article Writing → Human Review → Image Generation → Xiaohongshu (小红书) copy. Human-in-the-loop decisions are managed via LangGraph's `interrupt()` mechanism.

LLM and image generation use Bytedance's **Volcano Ark API** (OpenAI-compatible), configured via `ARK_API_KEY`.

## Commands

### Running Services (Development)

```bash
# From financial_agent_project/
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env           # then fill in ARK_API_KEY etc.

# Terminal 1 — AI service (must use python -m, not uvicorn directly)
python -m ai_service.main

# Terminal 2 — Backend API
uvicorn backend_api.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 3 — Frontend
cd frontend && npm install && npm run dev
```

Access: Frontend http://localhost:5173 | Backend docs http://localhost:8000/docs | AI service docs http://localhost:8100/docs

### Docker

```bash
docker compose up --build
```

### Tests

```bash
# All tests (from financial_agent_project/)
pytest

# Single test file
pytest tests/test_topic_node.py

# Smoke tests (require running services + valid API keys)
python -m scripts.smoke_graph   # direct LangGraph execution
python -m scripts.smoke_http    # end-to-end HTTP workflow
```

pytest is configured with `asyncio_mode=auto` (see `pytest.ini`).

### Frontend

```bash
cd frontend
npm run build    # production build
npm run lint     # ESLint
npm run preview  # preview production build
```

## Architecture

Three independent services communicate over HTTP:

```
Frontend (5173, React + Vite)
    ↓ /api proxy
Backend API (8000, FastAPI)        ← business logic, Campaign/ContentAsset in SQLite/PG
    ↓ HTTP
AI Service (8100, FastAPI + LangGraph)  ← workflow engine, state in PG checkpointer
    ↓
PostgreSQL (LangGraph checkpoints)
```

### AI Service (`ai_service/`)

The workflow is a `StateGraph` built in `graph/builder.py` with 8 nodes:

1. `generate_topics` — 5 candidate topics via LLM; the model autonomously decides whether to call the `search_news` tool (via `WebSearchTool`) for real-time news
2. `human_select_topic` — **INTERRUPT**: pauses until human picks/creates a topic
3. `generate_article` — full article from selected topic
4. `human_review_article` — **INTERRUPT**: pauses for approve/reject decision
5. `revise_article` — rewrites based on feedback; loops back to node 4 (`revision_round` increments)
6. `extract_image_content` — extracts 3–5 image prompts from the approved article
7. `generate_images` — parallel image generation via Volcano Ark image model
8. `generate_xhs_copy` — Xiaohongshu-style copy → END

State is defined as `AgentState` TypedDict in `graph/state.py`. Checkpoints use `AsyncPostgresSaver` (PostgreSQL) when `LANGGRAPH_CHECKPOINT_DSN` is set, otherwise `InMemorySaver`.

**Windows compatibility**: `ai_service/__init__.py` sets `SelectorEventLoop` policy — this is required for psycopg async on Windows and must not be removed.

### Backend API (`backend_api/`)

Owns `Campaign` and `ContentAsset` ORM models (SQLAlchemy 2 async). Campaign `status` maps to LangGraph stages:

`pending_topic` → `pending_review` → `generating` → `completed` / `failed`

`campaign_service.py` orchestrates calls to the AI service. `ai_client.py` wraps those HTTP calls.

Key endpoints:
- `POST /api/v1/campaigns` — create + start workflow
- `POST /api/v1/campaigns/{id}/select-topic[/stream]` — submit topic choice
- `POST /api/v1/campaigns/{id}/review-article[/stream]` — submit approve/reject

Streaming endpoints use SSE for real-time article generation progress.

### Frontend (`frontend/`)

React 18 + TypeScript + Ant Design 5. Vite proxies `/api` to `localhost:8000`.

- `src/api/` — axios client + campaign API methods
- `src/hooks/` — TanStack Query hooks (`useCreateCampaign`, `useGetCampaign`, `useNodeRuns`)
- `src/pages/` — `CampaignListPage`, `CampaignDetailPage`
- `src/components/` — `TopicSelectStep`, `ArticleReviewStep`, `ResultPanel`, `MetricsPanel`, `NodeProgressPanel`
- `src/types.ts` — TypeScript interfaces mirroring backend Pydantic schemas

### Shared Schemas (`shared_libs/schemas/`)

Pydantic schemas shared between services:
- `campaign.py` — `CampaignStatus`, `CampaignResponse`, `CampaignCreateRequest`, `SelectTopicRequest`, `ReviewArticleRequest`
- `workflow.py` — `WorkflowStage`, `WorkflowStateResponse`, `WorkflowStartRequest`

### Node Metrics

The `@track_node` decorator in `ai_service/core/metrics.py` tracks wall-clock duration, LLM token usage (input/output), and call counts per node, accumulating in `state["node_metrics"]`. Apply it to every new node.

### Prompts

LLM prompts are stored as YAML in `ai_service/prompts/` and loaded by `prompts/__init__.py`. Add new prompts there rather than hardcoding strings in node files.

## Key Configuration (.env)

| Variable | Service | Notes |
|---|---|---|
| `ARK_API_KEY` | AI | Required — Volcano Ark API key |
| `ARK_MODEL` | AI | LLM endpoint model ID |
| `ARK_IMAGE_MODEL` | AI | Image generation model (default: doubao-seedream-4-5-251128) |
| `LANGGRAPH_CHECKPOINT_DSN` | AI | PostgreSQL DSN; empty = InMemorySaver (dev only) |
| `BRAVE_MCP_URL` | AI | Web search MCP server (default: http://localhost:8200/mcp) |
| `AI_SERVICE_BASE_URL` | Backend | Where backend calls the AI service (default: http://localhost:8100) |
| `DATABASE_URL` | Backend | SQLite default for dev; PostgreSQL for production |
