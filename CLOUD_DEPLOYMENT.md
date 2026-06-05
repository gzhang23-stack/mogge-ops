# 云部署说明

目标：让监控、选题生成和钉钉推送 365 天持续运行。前端可以放在 Vercel，后端必须放在常驻服务器或容器环境中。

## 推荐架构

```text
GitHub
  -> Vercel：Next.js 前端后台
  -> 云服务器：FastAPI 后端 + APScheduler 监控任务
  -> PostgreSQL：Supabase 或腾讯云 PostgreSQL
```

Vercel 函数有执行时长限制，不适合承担全年持续监控；它更适合放前端。后端需要常驻进程，负责定时抓取监控源、生成选题、同步微信数据、推送钉钉。

本项目现在提供两种 Docker 部署方式：

- `docker-compose.yml`：只跑 FastAPI 后端，适合前端放 Vercel。
- `docker-compose.all-in-one.yml`：前端和后端打进一个容器，FastAPI 直接托管静态前端，适合腾讯云 CVM 单机部署。

## 方案 A：GitHub + Vercel + Supabase + 云服务器

适合你之前熟悉的工具链。

### 1. Supabase

1. 新建 Supabase 项目。
2. 在 Database 里启用 `vector` 扩展。
3. 复制连接串，建议使用 Transaction Pooler，拼成：

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:6543/postgres?sslmode=require
```

当前项目暂时用 JSON 存储向量，启用 pgvector 是为了后续平滑升级真正的向量列和索引。

### 2. 云服务器后端

服务器建议：

- 2C4G 起步，Ubuntu 22.04/24.04。
- 开放 `8000` 端口，或用 Nginx/宝塔/腾讯云负载均衡反代到 `8000`。
- 关闭系统睡眠，Docker 设置 `restart: unless-stopped`。

部署：

```bash
git clone <your-repo-url> mogge-ops
cd mogge-ops
cp deploy/.env.production.example deploy/.env.production
nano deploy/.env.production
docker compose up -d --build backend
```

检查：

```bash
curl http://127.0.0.1:8000/system/status
docker compose logs -f backend
```

### 3. Vercel 前端

1. 在 Vercel 导入 GitHub 仓库。
2. Root Directory 选择 `frontend`。
3. 配置环境变量：

```env
NEXT_PUBLIC_API_BASE=https://你的后端域名
```

4. 部署后，把后端 `FRONTEND_ORIGIN` 改成 Vercel 域名并重启后端。

## 方案 B：腾讯云备选

适合更偏国内网络和统一云资源管理。

### 推荐组合

- 腾讯云 CVM：运行 Docker 后端。
- 腾讯云 PostgreSQL：存储业务数据。
- Vercel 或腾讯云静态网站托管：放前端。
- 腾讯云 DNS/SSL/Nginx：绑定域名和 HTTPS。

腾讯云 PostgreSQL 已有 pgvector 相关能力，适合后续把历史文章知识库升级为数据库原生向量检索。

### 腾讯云部署步骤：前后端一体版

1. 购买 CVM，Ubuntu 22.04/24.04，2C4G 起步。
2. 安装 Docker 和 Docker Compose。
3. 购买腾讯云 PostgreSQL，创建数据库和账号；也可以首期先用容器内 SQLite。
4. 在数据库安全组中允许 CVM 内网 IP 访问。
5. 在 CVM 上部署完整系统：

```bash
git clone <your-repo-url> mogge-ops
cd mogge-ops
cp deploy/.env.production.example deploy/.env.production
nano deploy/.env.production
docker compose -f docker-compose.all-in-one.yml up -d --build
```

腾讯云 PostgreSQL 连接示例：

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
```

如果先用单机 SQLite，填：

```env
DATABASE_URL=sqlite:////app/data/mogge_ops.db
FRONTEND_ORIGIN=http://你的服务器IP:8000
```

访问：

```text
http://你的服务器IP:8000
```

这条路线最省事：一个容器同时提供网页、API、监控调度器和钉钉推送。

### Nginx 反代示例

```nginx
server {
    listen 80;
    server_name api.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

配置 HTTPS 后，把前端环境变量设为：

```env
NEXT_PUBLIC_API_BASE=https://api.your-domain.com
```

如果使用前后端一体版，前端和 API 同域，不需要设置 `NEXT_PUBLIC_API_BASE`；构建时留空即可。

## 生产环境变量

复制模板：

```bash
cp deploy/.env.production.example deploy/.env.production
```

必填项：

```env
DATABASE_URL=
FRONTEND_ORIGIN=
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=
LLM_MODEL=deepseek-v4-pro
WECHAT_ACADEMIC_APP_ID=
WECHAT_ACADEMIC_APP_SECRET=
WECHAT_RECRUIT_APP_ID=
WECHAT_RECRUIT_APP_SECRET=
DINGTALK_WEBHOOK=
DINGTALK_SECRET=
MONITOR_AUTO_RUN_ENABLED=true
```

## 运维检查

常用命令：

```bash
docker compose ps
docker compose logs -f backend
docker compose restart backend
curl https://api.your-domain.com/system/status
```

前后端一体版命令：

```bash
docker compose -f docker-compose.all-in-one.yml ps
docker compose -f docker-compose.all-in-one.yml logs -f app
docker compose -f docker-compose.all-in-one.yml restart app
curl http://127.0.0.1:8000/system/status
```

系统自检重点：

- `ready_score` 应接近或等于 `1.0`。
- `monitor_sources` 应大于 `0`，当前内置优质源约 70 个。
- `dingtalk`、`llm`、`wechat` 应显示已配置。
- 后台“热点与前沿监控”页面的调度器应显示运行中。

## 数据迁移

当前 exe 单机版默认数据在：

```text
%LOCALAPPDATA%\MoggeOps\mogge_ops.db
```

云端 PostgreSQL 首次部署会自动建表和初始化基础数据。若要迁移单机历史数据，建议另做一次 SQLite -> PostgreSQL 导入脚本，避免把测试数据、个人本地数据和生产数据混在一起。

## 选择建议

- 已熟悉 Vercel/Supabase：用方案 A，最快上线。
- 更重视国内访问、统一账单和后续备案域名：用方案 B。
- 不管哪条路线，后端都要常驻在服务器上，不能只靠 Vercel 定时函数承担全年监控。
