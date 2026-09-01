# MOVO Admin API

`admin/api` 是管理后台的独立后端，用于承载控制面能力：

- 登录与管理员身份
- 组织、用户、角色
- 模型中心
- Skill / Workflow / Tool / MCP 管理
- 配置中心
- 统计与审计

当前这版先提供最小壳子和基础示例路由，便于 `admin/web` 先接起来。

当前已支持：

- MongoDB 持久化管理员用户
- 启动时自动引导默认超级管理员
- 真实登录密码校验
- `/api/auth/me` 当前会话查询
- `/api/auth/logout` 当前会话失效

默认管理员：

```text
username: admin
password: admin123
```

模型连通性测试（OpenAI / Azure OpenAI）TLS 说明：

- 默认严格校验证书链。
- 若公司网络或私有 CA 导致 `CERTIFICATE_VERIFY_FAILED`，可配置：
  - `ASKAI_ADMIN_MODEL_TEST_CA_BUNDLE=/path/to/ca-bundle.pem`
- 仅开发环境临时兜底（不推荐生产）：
  - `ASKAI_ADMIN_MODEL_TEST_INSECURE_SKIP_VERIFY=true`

说明：

- 若未单独设置 `ASKAI_ADMIN_MONGODB_URI`，会优先尝试复用 `backend/.env` 中的 `MONGODB_URI`
- 管理后台默认使用数据库 `askai_admin`

启动示例：

```bash
cd admin/api
cp .env.example .env
../../backend/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8100
```
