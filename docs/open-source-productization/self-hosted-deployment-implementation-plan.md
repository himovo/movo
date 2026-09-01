# MOVO 私有化一键部署与桌面端连接实施基线

> 状态：第一阶段已实现，并已通过真实 Docker 构建与整套容器联调
> 范围：开源服务端与 Web 端；不包含 `apps/desktop-electron` 和 `apps/local-browser-agent` 的源码发布

## 1. 目标

企业管理员执行：

```bash
./movo up
```

启动器会显示 MOVO 标识，内部执行 `docker compose up -d`，等待部署状态全部就绪后输出浏览器初始化地址。原生 Compose 命令仍然支持。

随后访问首次初始化页面，依次完成部署检测、企业与账号、基础对话模型及可选模型配置。系统最终展示：

- 员工 Web 地址
- 管理后台地址
- 桌面端应填写的企业服务地址

初始化页复用管理后台“模型中心”的供应商、模型实例和连接测试能力，不另建模型配置体系。基础对话模型必须测试成功；向量、视觉和文生图模型按企业需要选配。

文档向量化目前只接入代码中已有的 Azure Embedding，重排使用 DashScope；Weaviate 能随 Compose 一键启动，但真正执行文档问答前仍需配置相应外部模型凭据。这是现有代码能力边界，不把“容器已启动”误写为“文档问答无需模型即可使用”。

员工安装官方桌面端后，使用企业服务地址和自己的企业账号登录。桌面端内置的 Browser Agent 主动连接该企业部署的 WebSocket 服务。

这里的“一键启动全部服务”不包括：

- `apps/desktop-electron`：员工电脑上的闭源客户端
- `apps/local-browser-agent`：随桌面端分发并在员工电脑运行
- 桌面端本地 Code Runtime：随闭源桌面端运行，不是服务端 Compose 容器

## 2. 已核实的当前事实

### 2.1 当前生产 Compose 不完整

现有 `docker-compose.prod.yml` 只启动：

- `services/chat-api`
- `apps/user-web`

它尚未启动 MongoDB、Redis、Admin Web、Admin API、文档处理 API、文档处理 Worker和统一网关，因此目前不能作为完整私有化部署交付。

### 2.2 初始化能力已经存在，但未形成完整向导

已有实现：

- 页面：`apps/admin-web/src/views/auth/SetupPage.vue`
- 前端 API：`apps/admin-web/src/api/setup.ts`
- 服务端 API：`services/admin-api/app/api/routes/setup.py`
- 状态存储：MongoDB `system_bootstrap` 集合中的 `_id=singleton` 文档
- 员工端登录会检查 `system_bootstrap.completed`

当前 Setup 创建：

- 企业名称与随机 `main_id`
- 管理员账号
- 首个员工账号
- 根部门
- 员工的全能力岗位角色

本阶段已补充：

- Compose 服务健康检查和初始化页部署状态
- 对外访问地址与桌面端服务地址生成
- 存储目录可写检查
- 未初始化系统自动进入 Setup

当前 Setup 还会保存企业总 Token、员工默认 Token、额度周期和企业时区；初始化失败会按本次生成的租户 ID 清理已写入数据。

### 2.3 模型配置能力已经存在

已有管理页面和 API：

- `apps/admin-web/src/views/models/ModelsPage.vue`
- `services/admin-api/app/api/routes/models.py`
- `services/admin-api/app/repositories/model_repository.py`

模型配置保存在 MongoDB 的 `admin_model_providers` 和 `admin_model_instances` 中，`chat-api` 会读取这些集合。因此初始化向导应复用现有模型仓储与测试能力，不再创建另一套模型配置。

### 2.4 文档处理是独立服务

本地开发脚本 `dev.sh` 实际启动：

- Chat API
- User Web
- Admin API
- Admin Web
- Document Processing API
- Document Processing Celery Worker
- Redis

文档处理 API 和 Worker 共用 `services/document-parser` 镜像，并依赖 MongoDB、Redis和共享文档存储目录。

### 2.5 当前剩余的产品化事项

- 镜像首次构建需要从公网下载 Python、Node、系统包、Playwright、LibreOffice、Docling/PyTorch 等依赖，因此第一次启动耗时较长；后续启动复用本地镜像和缓存。
- `docker-compose.prod.yml` 仍是旧的双服务文件；默认交付入口已经切换到根目录 `docker-compose.yml`。
- Setup 的多请求并发原子锁仍需进一步加固；单次失败补偿清理已经实现。
- Browser Agent WebSocket 当前信任客户端传入的 `user_id`，尚未真正用登录 Token 派生员工身份。
- Browser Agent 注册表当前是单进程内存字典，不支持多 Chat API 实例。

## 3. 第一版部署范围

### 3.0 Compose 纳入结论

执行以下命令时：

```bash
docker compose up -d
```

默认必须进入 Compose 的服务共 12 个：

1. `bootstrap`：首次生成内部密钥并准备目录，执行成功后正常退出。
2. `gateway`：唯一公开入口，负责 Web、API 和 WebSocket 反向代理。
3. `user-web`：员工 Web 端。
4. `admin-web`：初始化页面和管理后台。
5. `chat-api`：员工登录、对话、任务、文件和 Browser Agent WebSocket Gateway。
6. `dsh-runtime-host`：服务端对话与 Agent Kernel 的 Node Runtime Host。
7. `admin-api`：初始化、企业、员工、模型、技能和工具管理。
8. `document-api`：文档解析、预览、切片和检索 API。
9. `document-worker`：文档解析、转换、Embedding 和向量索引异步任务。
10. `mongo`：业务数据、租户、用户、会话及系统配置。
11. `redis`：Celery 消息队列，后续同时承载多实例 Agent 路由。
12. `weaviate`：知识文档向量索引和语义检索。

> 实际是 12 个 Compose 服务；其中 `document-api` 和 `document-worker` 使用同一个 `services/document-parser` 镜像，以不同启动命令运行。

默认不进入 Compose 的项目：

- `apps/desktop-electron`：员工本机安装的闭源桌面端。
- `apps/local-browser-agent`：随桌面端分发，在员工本机运行。
- `apps/official-website`：产品官网，不属于企业运行时。
- `services/crm-service`：示例 CRM/MCP 服务，不是当前平台核心依赖；后续可作为 Compose profile。

因此，第一阶段目标拓扑为：

```text
gateway
├── user-web
├── admin-web
├── chat-api ─────────── dsh-runtime-host
│       ├─────────────── mongo
│       └─────────────── redis（后续 Agent 路由）
├── admin-api ────────── mongo
└── document-api
        ├─────────────── mongo
        ├─────────────── redis ── document-worker
        ├─────────────── weaviate
        └─────────────── knowledge-storage

bootstrap ── deployment-secrets ── chat-api/dsh-runtime-host/admin-api/document-api/document-worker
```

### 3.1 必需容器

| Compose 服务 | 代码来源 | 作用 |
|---|---|---|
| `bootstrap` | 新增部署脚本/镜像 | 首次启动生成共享密钥和初始化必要目录，成功后退出 |
| `gateway` | 新增部署配置 | 唯一公开入口，代理两个 Web 和两个 API，并支持 WebSocket |
| `user-web` | `apps/user-web` | 员工使用界面 |
| `admin-web` | `apps/admin-web` | 初始化及管理后台 |
| `chat-api` | `services/chat-api` | 登录、对话、任务、文件和 Agent Gateway |
| `dsh-runtime-host` | `services/chat-api/dsh/runtime-host` | 服务端对话与 Agent Kernel；只在内部网络开放并使用部署令牌认证 |
| `admin-api` | `services/admin-api` | Setup、组织、员工、模型、技能和工具管理 |
| `document-api` | `services/document-parser` | 文档解析、预览和检索 API |
| `document-worker` | `services/document-parser` | Celery 异步文档任务 |
| `mongo` | 官方 MongoDB 镜像 | 业务与配置数据 |
| `redis` | 官方 Redis 镜像 | Celery；后续也用于 Agent 路由 |
| `weaviate` | Weaviate 官方镜像 | 知识文档向量索引与语义检索 |

### 3.2 持久化卷

- `mongo-data`
- `redis-data`
- `weaviate-data`
- `dsh-runtime-data`：服务端 DSH 会话运行状态
- `deployment-secrets`：Bootstrap 首次生成、各服务只读挂载的内部密钥
- `askai-storage`：Chat API 生成文件
- `knowledge-storage`：Admin API 与 Document Processing 共享的知识文档和预览文件

### 3.3 可选服务

- `services/crm-service`：当前不是 `dev.sh` 的核心依赖，也没有被平台硬编码调用，应作为示例 MCP/CRM profile，而不是默认必启服务。
- `apps/official-website`：产品官网，不属于企业运行时。

### 3.4 Weaviate 当前情况

当前代码已经通过 `MOVO_DOC_PROCESSING_WEAVIATE_ENDPOINT` 使用 Weaviate，默认开发地址是 `http://127.0.0.1:8080`。截图中的 `askai-weaviate` 也是单独运行的 Weaviate 容器。目标 Compose 中必须将它改成默认必启服务，并让 Document Processing 使用容器内地址：

```text
http://weaviate:8080
```

要求：

- 固定明确的 Weaviate 镜像版本，不能使用浮动 `latest`。
- 使用 `weaviate-data` volume 持久化索引。
- 增加 readiness/healthcheck，Document Worker 在 Weaviate 就绪后再开始消费索引任务。
- 默认不把 8080 暴露到公网，只允许 Compose 内部网络访问。
- 仓库原先没有该容器的 Compose 或镜像版本记录，因此通过本机 Docker 只读核对了实际运行环境。

核对结果：截图对应的运行容器为 `askai-weaviate`，镜像是 `semitechnologies/weaviate:1.25.7`。第一版 Compose 因此固定沿用 `1.25.7`，不在一键部署改造中顺便升级向量数据库；升级和索引迁移另行验证。

## 4. 统一公开入口

第一版建议一个公开 Origin：

```text
http(s)://企业域名/                 员工 Web
http(s)://企业域名/admin/          管理后台
http(s)://企业域名/askai-api/      Chat API
http(s)://企业域名/admin-api/      Admin API
```

Browser Agent WebSocket 对外地址为：

```text
ws(s)://企业域名/api/agent/connect
```

统一网关同时保留 `/askai-api/`（Web API）和 `/api/`（桌面端兼容协议）；桌面端填写企业服务根地址后，当前会连接 `/api/agent/connect`。

### 地址生成边界

Docker 无法自动生成企业 DNS 域名。可实现的是：

- 本机体验默认显示 `http://localhost:<port>`。
- 局域网部署可以根据管理员访问初始化页时的 Origin 显示候选地址。
- 正式部署通过 `PUBLIC_BASE_URL=https://movo.company.com` 明确配置。
- 最终地址以 `PUBLIC_BASE_URL` 为准；未配置时才使用请求 Origin。

## 5. 初始化流程目标

### 第一步：部署自检

只读检查：

- MongoDB 可连接
- Redis 可连接
- Weaviate 可连接
- Chat API、服务端 DSH Runtime、Admin API、Document API、Worker 就绪
- 两个持久化目录可写
- 对外地址和 WebSocket 地址可计算
- 生产密钥不是开发默认值

基础设施密钥不让用户手填。为严格满足只执行 `docker compose up -d`，一次性 `bootstrap` 容器会首次生成 `/run/askai-secrets/runtime.env` 到 `deployment-secrets` volume，其他服务的 entrypoint 只读加载。当前生成：

- `END_USER_AUTH_SECRET`
- `ASKAI_ADMIN_JWT_SECRET`
- `MODEL_CONFIG_SECRET`
- 文档处理 service/callback token

### 第二步：企业和账号

复用现有 Setup 字段：

- 企业名称
- 管理员账号、显示名、密码
- 首个员工账号、姓名、密码
- 企业总 Token、员工默认 Token
- 额度周期（月、日或小时）与企业时区

需要补强：

- 禁用生产环境 `admin/admin123` 自动创建。
- Setup 初始化必须使用原子锁，防止两个请求同时初始化。
- 初始化失败不能留下“账号已创建但 Setup 未完成”的半成品状态。

### 第三步：基础对话模型

复用现有模型 Provider、Instance 和测试接口，至少要求：

- 选择模型供应商
- 填写 Base URL、模型名、API Key
- 测试连接
- 设置一个默认 Chat 模型

基础模型连通性测试通过后，才允许最终完成初始化。

### 第四步：其他模型（可选）

- 向量模型（Embedding）：把文档与问题转换为向量，用于知识库语义检索、文档问答和 RAG。
- 视觉模型（Vision）：理解图片、截图、扫描件和图表，用于视觉问答与信息提取。
- 文生图模型（Image）：根据文字生成文章配图、海报、创意素材和视觉草图。

界面同时说明未配置时的影响；企业可以跳过，并在初始化完成后从模型中心补充。

### 第五步：完成与连接信息

展示并允许复制：

```text
员工 Web：     https://movo.company.com/
管理后台：     https://movo.company.com/admin/
桌面端服务：   https://movo.company.com
Agent WSS：    wss://movo.company.com/.../agent/connect
```

同时允许下载不包含密码和 API Key 的 `movo-connection.txt`，用于企业内部保存或分发连接地址。

当前桌面端已经支持保存 `backend_url` 并据此连接 API 与 Browser Agent，因此第一版可以让员工在桌面端首次启动时粘贴“桌面端服务”地址。

“网页一键打开桌面端”和 `movo://connect` 放在后续阶段，不阻塞第一版 Docker 私有化部署。

## 6. Setup 状态与提交策略

当前向导在浏览器中保存未提交表单，后端只持久化最终结果。模型连接测试使用一次性
加密模型记录并在测试结束后立即删除，因此无需把半完成的账号或模型长期写入数据库。

关键规则：

- 未完成前允许管理员继续 Setup，但员工端禁止登录使用。
- 组织账号和模型配置在最终提交时一并写入。
- 企业及员工默认 Token 策略在最终提交时一并写入。
- 只有默认 Chat 模型测试成功后才写入 `completed=true`。
- 已完成后，前端访问 Setup 会转到登录页，公开 Setup 配置与初始化接口返回 409；后续修改走需要管理员鉴权的普通管理 API。

## 7. 分阶段实施清单

### M1：Compose 能完整启动

- [x] 新建统一的生产 Compose，而不是继续使用当前只有两个服务的文件。
- [x] 增加一次性 Bootstrap 容器、共享密钥 volume 和 entrypoint 密钥加载。
- [x] 为 Admin Web 增加生产镜像。
- [x] 增加 MongoDB、Redis、Weaviate、服务端 DSH Runtime、Admin API、Document API、Document Worker和 Gateway。
- [x] 配置共享 volume、容器服务名和 `depends_on` 健康条件。
- [x] 默认使用本地文件存储。
- [x] 替换私有基础镜像和内部 PyPI/测试服务默认地址。
- [x] 所有依赖在镜像构建阶段安装。
- [x] `docker compose up -d` 后所有必需容器达到 healthy（一次性 `bootstrap` 正常以状态码 0 退出）。

### M2：首次初始化闭环

- [x] 首次访问自动进入初始化页面。
- [x] 增加部署自检 API 与页面。
- [ ] 加固 Setup 原子性和幂等性。
- [x] 移除生产默认管理员密码。
- [x] 将模型配置与连接测试纳入 Setup。
- [x] 增加企业总 Token、员工默认 Token、周期和时区配置。
- [x] 增加向量、视觉、文生图模型的选配与用途说明。
- [x] 完成页支持下载不含密钥的连接配置文本。
- [x] 初始化完成后展示 Web、管理后台、桌面服务和 Agent WSS 地址。
- [ ] 员工账号可以登录 User Web 并完成一次基础对话。

### M3：桌面端连接

- [ ] 固定 Desktop/API/Agent 的公共路径协议。
- [ ] 增加服务发现接口，例如 `/.well-known/movo-desktop.json`。
- [ ] 桌面端首次启动输入企业服务地址并获取发现信息。
- [ ] WebSocket 使用 Token 验证并由服务端派生 `main_id/user_id`。
- [ ] 使用 `main_id + user_id + device_id` 标识 Agent 连接。
- [ ] 验证多员工同时连接、执行和断线重连。

### M4：生产化

- [ ] Redis Agent 路由，支持多 Chat API 实例。
- [ ] HTTPS、备份恢复、日志轮转和升级文档。
- [ ] `movo://connect` 一键绑定桌面端。
- [ ] MDM 批量预置企业地址。

## 8. 第一阶段验收标准

在一台没有本项目开发环境的新机器上：

1. 只安装 Docker 与 Docker Compose。
2. 不创建 `.env` 也能使用默认端口启动；正式域名等可选项允许通过 `.env` 覆盖。
3. 执行 `docker compose up -d`，不手工安装 Node、Python、MongoDB、Redis或 LibreOffice。
4. 所有必需容器健康。
5. 打开初始化地址，完成部署检测、企业与账号、Token 配额、基础模型连接测试，并按需配置其他模型。
6. 员工使用初始化账号登录 User Web。

## 9. 已完成的真实 Docker 验证

2026-08-26 在全新 Compose 数据卷上完成了以下验证：

- 默认 `docker compose up -d` 能构建并启动上述 12 个服务。
- MongoDB、Redis、Weaviate、DSH Runtime Host、Chat API、Admin API、Document API、User Web、Admin Web 和 Gateway 均通过健康检查。
- Document Worker 正常运行，初始化状态 API 同时确认 Document API 与 Worker 就绪。
- `GET /healthz` 返回 200。
- `/setup` 正确跳转到 `/admin/setup`，不会丢失外部端口。
- `GET /admin-api/api/setup/status` 返回 `ready=true`，并生成员工 Web、管理后台、桌面端服务和 Agent WebSocket 地址。
- Setup 模型供应商接口返回预置供应商；使用本地模拟 OpenAI 兼容接口完成真实连接测试，且测试后临时模型记录数量为 0。
- Chat API 和 Document API 镜像均完成容器内 Python 导入检查。
- DSH Runtime Host 完成带认证的容器网络连接、Runtime 创建与释放冒烟测试。

验证没有代替用户执行初始化，因此没有预先创建测试企业、管理员或员工账号。
7. 完成一次模型对话和一次文件生成，并在容器重启后仍可访问数据。
8. 上传一份知识文档，文档处理任务完成并能通过 Weaviate 检索；容器重启后索引不丢失。
9. 桌面端填写初始化页给出的企业服务地址，员工登录后 Browser Agent 能建立 WSS 连接。
10. 两名不同员工同时使用时，账号、会话和 Agent 连接不串线。

## 9. 下一步实施顺序

1. 在全新 Docker 环境完成镜像构建和 12 个服务的健康检查。
2. 用初始化账号验证 Web 登录、基础对话、文档上传、Worker 处理和 Weaviate 检索。
3. 加固 Setup 的并发原子性，并验证可选模型在各业务入口中的能力路由。
4. 再处理桌面端 Token 鉴权、多员工 Agent 隔离和多 Chat API 实例路由。

在前三项通过之前，不开始 `movo://connect`、MDM 或桌面端自动更新等后续工作。

## 10. 当前使用方式

默认本机部署不要求先创建 `.env`：

```bash
docker compose up -d
docker compose ps
```

全部服务就绪后访问：

```text
http://localhost:3000/admin/setup
```

如果端口不是 3000，或已经有正式 HTTPS 域名，可在根目录创建 `.env`：

```dotenv
MOVO_PORT=8080
PUBLIC_BASE_URL=https://movo.company.com
AZURE_EMBEDDING_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_EMBEDDING_DEPLOYMENT_NAME=text-embedding-3-large
AZURE_EMBEDDING_API_VERSION=2024-02-01
AZURE_EMBEDDING_API_KEY=replace-me
DASHSCOPE_API_KEY=replace-me
```

其中 `PUBLIC_BASE_URL` 只影响初始化页显示的正式连接地址；HTTPS 证书和域名反向代理仍由企业网关负责。Embedding 和 DashScope 凭据不是容器启动的前置条件，但文档向量索引和重排需要它们。
