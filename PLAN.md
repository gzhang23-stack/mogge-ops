# 募格双公众号 AI 内容运营系统完整 Web 后台实现计划

## Summary
建设一个一次性覆盖完整需求的 Web 后台：历史文章知识库、全网/学术前沿监控、选题池、双账号分发、AI 资料包与写作、标题摘要、风控审核、公众号排版/草稿箱对接、内容日历、数据复盘和策略反哺。实际发布仍保留人工终审，不做无人化群发。

默认技术栈：`Next.js + React + TypeScript` 前端，`FastAPI + Python` 后端，`PostgreSQL + pgvector` 数据库，`Redis + Celery` 异步任务，`S3/MinIO` 存储图片与导入文件，LLM 使用 OpenAI-compatible 网关，支持按环境变量切换 OpenAI、通义千问、DeepSeek 等模型。

## Key Changes

### 1. Core Architecture
- 建立多角色后台：运营负责人、内容编辑、审核人员、管理员，使用 RBAC 控制页面、操作和审核权限。
- 后端拆分为 8 个服务域：账号配置、历史文章知识库、热点监控、选题分发、AI 写作、审核风控、排版草稿、数据复盘。
- 所有 AI 输出必须走结构化 JSON schema 校验，保存 prompt 版本、输入上下文、模型、输出、人工修改记录，便于复盘和追责。
- 历史文章、外部来源、资料包、正文段落都绑定引用来源；无来源的事实统一标记为“待核实”。

### 2. Data Model
核心表至少包括：

- `users`, `roles`, `permissions`, `audit_logs`
- `wechat_accounts`, `account_profiles`, `content_columns`, `style_templates`
- `historical_articles`, `article_metrics`, `article_tags`, `article_embeddings`
- `source_documents`, `external_hot_events`, `academic_monitor_items`
- `topics`, `topic_scores`, `topic_distribution_rules`
- `material_packs`, `outlines`, `drafts`, `title_candidates`, `summaries`
- `risk_findings`, `review_tasks`, `review_comments`
- `calendar_items`, `publish_records`, `operation_reports`
- `wechat_draft_jobs`, `asset_uploads`

关键状态：
`topic.status = candidate / approved / writing / reviewing / scheduled / published / discarded`
`draft.status = generating / editing / risk_checked / review_pending / approved / rejected / exported`
`risk.level = low / medium / high`

### 3. Main Workflows
- 历史文章导入：支持 CSV、Markdown、HTML、公众号文章 URL 元数据导入；导入后自动抽取摘要、标签、栏目、风险等级、可复用建议，并写入向量库。
- 历史检索：支持自然语言检索、账号/栏目/标签/时间/阅读表现筛选，返回相似文章、摘要、数据表现、复用建议和风险提示。
- 热点监控：定时采集合法可访问来源；对微博、知乎等限制较多的平台优先做“人工导入/半自动导入”接口，避免违规抓取。
- 学术前沿监控：接入 Nature、Science、Cell、Retraction Watch 等 RSS/API/页面源，自动翻译、摘要、风险分级，编辑可一键转选题。
- 选题池：将热点、历史翻新、节点型内容、双账号联动内容统一入池，自动评分并推荐账号、栏目、发布时间和风险等级。
- 写作台：按“选题 → 资料包 → 大纲 → 初稿 → 标题摘要 → 风险检查 → 排版稿”流水线生成，编辑可在每一步修改并重新生成。
- 审核台：低风险由编辑复核，中风险进入审核人员复核，高风险进入运营负责人终审；审核意见、退回原因和修改记录全量留痕。
- 排版草稿：输出 Markdown、微信公众号 HTML 排版稿；通过审核后可调用公众号草稿箱接口创建草稿，不自动群发。
- 内容日历：展示两账号排期，避免同日高重复、连续同类选题，优先安排强时效内容。
- 数据复盘：支持手动录入或接口采集阅读、点赞、在看、收藏、转发、评论、新增/取消关注等数据，生成标题、选题、发布时间、栏目表现分析，并反哺后续推荐权重。

## Public Interfaces
- `POST /articles/import`：导入历史文章。
- `GET /articles/search?q=`：自然语言检索历史文章。
- `POST /monitors/run`：触发热点/学术前沿监控。
- `POST /topics/generate`：生成候选选题。
- `POST /topics/{id}/approve`：确认选题进入写作。
- `POST /workspaces/{topicId}/material-pack`：生成资料包。
- `POST /workspaces/{topicId}/outline`：生成大纲。
- `POST /workspaces/{topicId}/draft`：生成初稿。
- `POST /workspaces/{topicId}/titles`：生成不少于 10 个标题并评分。
- `POST /workspaces/{topicId}/risk-check`：生成风险报告。
- `POST /reviews/{draftId}/submit`：提交审核。
- `POST /wechat/drafts`：审核通过后创建公众号草稿。
- `POST /metrics/import`：导入发布后数据。
- `GET /reports/operation`：生成复盘报告。

## Implementation Milestones
1. 基础工程与权限：搭建前后端、数据库、登录、RBAC、审计日志、后台布局。
2. 账号与模板：录入“募格学术”“募格科聘”的定位、栏目、风格、标题禁用规则、风险规则。
3. 历史知识库：完成导入、标签抽取、向量化、检索、相似度和复用建议。
4. 选题与监控：完成外部热点、学术前沿、历史翻新、节点型选题生成与评分。
5. AI 写作链路：完成资料包、大纲、初稿、标题摘要、封面文案、转发语生成。
6. 风控审核：完成事实、引用、重复、招聘、学术规范、版权、敏感风险检测与审核流。
7. 排版与草稿：完成 Markdown/HTML 排版输出、发布前检查、公众号草稿箱创建任务。
8. 日历与复盘：完成内容排期、运营数据录入/采集、报表和策略反哺。
9. 联调验收：用真实历史文章和 10 个典型选题跑通全流程。

## Test Plan
- 单元测试：权限判断、状态流转、风险分级、标题评分、排期规则、数据指标计算。
- 集成测试：文章导入到向量检索、选题生成到写作台、审核通过到草稿箱任务、数据导入到复盘报告。
- AI 质量测试：固定 20 个选题样本，检查资料包有来源、初稿符合账号风格、标题不少于 10 个、高风险内容能被标记。
- E2E 测试：运营负责人确认选题、编辑生成并修改初稿、审核人员退回/通过、最终生成排版稿和草稿。
- 安全测试：角色越权、敏感配置泄露、外部抓取失败、模型输出 JSON 无效、来源缺失、重复导入。
- 验收场景：每日自动选题、历史爆款翻新、双账号联动、招聘文章审核、撤稿/争议类高风险审核。

## Assumptions
- 首版交付形态为 Web 后台，且按“完整一步到位”实现全部模块。
- 不做自动群发发布；公众号草稿箱只在人工终审通过后创建草稿。
- 微信公众号接口按官方开发文档实现，开发时需确认账号认证、开发者凭证、IP 白名单、素材上传和草稿箱权限。
- 对微博、知乎等平台不做绕过限制的抓取；没有稳定合法接口时使用人工导入或半自动导入。
- 历史文章原始数据由运营方提供，至少包含标题、正文、发布时间、公众号、链接；运营数据可先手动导入，再逐步自动化。
- 参考文档：本地需求文档《募格双公众号AI内容运营系统需求方案.md》；微信公众号开发文档入口：https://developers.weixin.qq.com/doc/offiaccount/Getting_Started/Overview.html
