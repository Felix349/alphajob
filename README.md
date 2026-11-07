# AlphaJob

> 掌握你全部求职数据的求职 Agent。以“投递记录”为中心，帮计算机方向的应届生管理投递进度、针对岗位备考、复盘每一场面试，并主动规划每天该做什么。

- 产品需求：[产品需求文档.md](产品需求文档.md)
- 技术设计：[技术设计文档.md](技术设计文档.md)
- 设计笔记：[docs/notes/](docs/notes/)
- 学习路线：[docs/学习路线.md](docs/学习路线.md)（按“一个请求的完整旅程”精读项目）
- 命令速查：[docs/开发命令手册.md](docs/开发命令手册.md)

## 当前进度

| 里程碑 | 状态 |
|---|---|
| W1 地基：脚手架、数据库、注册登录、CI | ✅ 完成 |
| W2 求职看板：投递管理、拖拽看板、JD 智能解析、日程与日历 | ✅ 完成 |
| W3 岗位匹配备考：简历上传、流式匹配分析、备考清单 | ✅ 完成 |
| W4 面试复盘：录音 / 文字复盘、语音转写、后台任务、个人题库 | ✅ 完成 |
| W6 求职 Agent：今日 / 本周计划、对话（工具调用 + 写操作确认） | ✅ 完成 |

## 技术栈

- **前端：** Next.js 16（App Router）· React 19 · TypeScript · Tailwind CSS 4 · shadcn/ui · TanStack Query · dnd-kit · FullCalendar 7
- **后端：** Python 3.12 · FastAPI · SQLAlchemy 2（异步）· Alembic · Pydantic v2
- **大模型：** 自研抽象层，支持 DeepSeek / 通义千问 / OpenAI（OpenAI 兼容接口）与 Claude（官方 SDK）
- **基础设施：** PostgreSQL 16 · Redis 7 · Docker Compose · GitHub Actions

## 架构概览

```
浏览器 ──> Next.js（:3000）──/api/* 反向代理──> FastAPI（:8000）──> PostgreSQL / Redis
                                                               └─ 任务 ──> Redis ──> Worker（转写、复盘分析）
```

浏览器只和 Next.js 打交道，前后端同源：登录 Cookie 自动携带，不需要配置跨域。

## 本地运行

**前置要求：** Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)、Node.js 22+ 与 pnpm、Docker Desktop。

```bash
# 1. 配置环境变量（首次）
cp .env.example .env          # 然后把 JWT_SECRET 改成随机字符串

# 2. 启动 Postgres 和 Redis
docker compose up -d

# 3. 启动后端（新终端）
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 4. 启动后台 Worker（新终端；面试复盘需要它）
cd backend
uv run arq app.worker.WorkerSettings

# 5. 启动前端（新终端）
cd frontend
# pnpm install
pnpm dev
```

打开 http://localhost:3000 注册账号即可使用。

**启用语音复盘：**在 `.env` 中填写 `DASHSCOPE_API_KEY`（阿里云百炼）。不配置也能用文字复盘。

**启用 JD 智能解析：** 在 `.env` 中填写 `DEEPSEEK_API_KEY`（默认服务商），重启后端即可。想换成 Claude，设置 `LLM_PROVIDER=anthropic` 并填写 `ANTHROPIC_API_KEY`。不配置 Key 也能使用，新建投递时手动填写即可。后端接口文档：http://127.0.0.1:8000/api/docs

## 常用命令

> 完整的命令速查（开工与收工、数据库迁移、评估脚本、Git 工作流、常见问题）见 **[docs/开发命令手册.md](docs/开发命令手册.md)**。

| 目的 | 命令 |
|---|---|
| 后端测试 | `cd backend && uv run pytest` |
| 后端检查与格式化 | `uv run ruff check . && uv run ruff format .` |
| 新建数据库迁移 | `uv run alembic revision --autogenerate -m "描述"` |
| 前端类型检查 / lint | `cd frontend && pnpm typecheck && pnpm lint` |
| 前端格式化 | `pnpm format` |
| 后端接口变化后，重新生成前端类型 | `pnpm gen:api` |

## 目录结构

```
backend/    FastAPI 服务：api 路由 → services 业务逻辑 → repositories 数据访问
frontend/   Next.js 应用：src/app 页面路由，src/components 组件，src/lib/api 接口封装
docker/     容器初始化脚本
docs/notes/ 每个模块的设计笔记
```

## 常见问题

- **数据库连接卡住不动（Windows）：** 连接地址用 `127.0.0.1` 而不是 `localhost`。Windows 会让 `localhost` 优先走 IPv6，而 Docker Desktop 的 IPv6 端口转发可能连不通。
- **`alembic.ini` 报 GBK 解码错误：** Windows 上 Alembic 用系统编码读取 ini 文件，所以 `alembic.ini` 里只能写英文。
