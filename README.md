# 募格双公众号 AI 内容运营系统

一个面向“募格学术 / 募格科聘”的 AI 内容运营 Web 后台原型，覆盖历史文章知识库、热点监控、选题池、AI 写作台、风控审核、排版草稿、内容日历和数据复盘。

## 目录

- `backend/`：FastAPI 后端，默认 SQLite，可通过 `DATABASE_URL` 切换 PostgreSQL。
- `frontend/`：Next.js 后台界面。
- `募格双公众号AI内容运营系统需求方案.md`：原始需求文档。

## 快速启动

后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload --port 8000
```

前端：

```powershell
cd frontend
npm install
npm run dev -- --port 3000
```

访问：

- 前端后台：http://localhost:3000
- 后端 API：http://localhost:8000/docs

## 云端 365 天游运行

本地 exe 关闭后不会继续监控。若要全年运行，需要部署到云服务器。

部署说明见 [CLOUD_DEPLOYMENT.md](./CLOUD_DEPLOYMENT.md)，已覆盖两条路线：

- GitHub + Vercel 前端 + Supabase PostgreSQL + 云服务器后端。
- 腾讯云 CVM + 腾讯云 PostgreSQL，或腾讯云 CVM 一体化容器部署。

腾讯云一体化容器部署示例：

```bash
cp deploy/.env.production.example deploy/.env.production
docker compose -f docker-compose.all-in-one.yml up -d --build
```

## 功能验收

后端测试已经包含一条全链路 smoke test，会跑通历史文章导入、文件导入、自然语言检索、监控源、微信公众号监控导入、监控转选题、选题生成、写作台资料包/大纲/初稿/标题/风控、审核提交、内容日历、运营数据导入、数据复盘、自动化设置和公众号草稿箱前置检查。

```powershell
cd backend
pytest
```

前端构建检查：

```powershell
cd frontend
npm run build
```

建议每次改动后同时跑 `pytest` 和 `npm run build`，再打开 `http://localhost:3000` 检查主要页面。

也可以访问后端自检接口查看系统准备度：

```powershell
Invoke-WebRequest http://localhost:8000/system/status
```

首页“今日运营”会展示同一份自检结果，包括知识库、监控源、选题池、钉钉、大模型、公众号草稿箱和复盘数据状态。

## 环境变量

复制 `backend/.env.example` 为 `backend/.env` 后可配置数据库、LLM 和微信公众号参数。无 LLM Key 时系统会使用内置规则生成资料包、初稿、标题和风控结果。

DeepSeek 示例：

```powershell
cd backend
Copy-Item .env.example .env
notepad .env
```

在 `.env` 中填写：

```env
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=你的 DeepSeek Key
LLM_MODEL=deepseek-v4-pro
```

填好后重启后端服务。资料包、大纲、初稿、标题摘要会优先调用 DeepSeek；调用失败或未配置时自动回退到本地规则生成。

微信公众号凭证只填写到 `backend/.env`，不要放入 `.env.example`：

```env
WECHAT_ACADEMIC_APP_ID=募格学术 appid
WECHAT_ACADEMIC_APP_SECRET=募格学术 appsecret
WECHAT_RECRUIT_APP_ID=募格科聘 appid
WECHAT_RECRUIT_APP_SECRET=募格科聘 appsecret
```

可用 `GET /wechat/accounts` 检查配置状态，接口只返回掩码，不返回明文 `appsecret`。

监控源维护见 [MONITOR_SOURCES.md](./MONITOR_SOURCES.md)。

钉钉自动推送配置：

```env
DINGTALK_WEBHOOK=钉钉自定义机器人的 Webhook
DINGTALK_SECRET=钉钉机器人加签 Secret
MONITOR_AUTO_RUN_ENABLED=true
MONITOR_AUTO_RUN_INTERVAL_MINUTES=60
MONITOR_PUSH_TOPIC_LIMIT=8
MONITOR_PUSH_SCORE_THRESHOLD=0.68
```

开启后，后端启动时会自动注册定时任务：定时运行监控、生成候选选题、筛选非高风险且评分达标的选题，并以 Markdown 消息推送到钉钉群。也可在后台“热点与前沿监控”页面手动点击“运行并推钉钉”。
