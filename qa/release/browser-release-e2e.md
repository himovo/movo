# 用户端浏览器发版验收

本套件是基础对话的独立 Playwright Chromium 回归。它从真实浏览器登录用户端，创建对话并进行多轮任务，等待服务端响应及页面结果，再刷新页面，从历史列表重新打开会话，核对任务和回答。它访问目标部署的真实网关、认证、会话存储和模型；不拦截或模拟接口。完整发版门禁按[浏览器验收用例](browser-release-cases.zh-CN.md)在 Codex 会话中逐条执行。本文位于 `qa/release/`，运行命令仍从仓库的 `qa/` 目录执行。

## 前提

- 准备与候选版本一致的隔离测试部署，以及有任务权限的专用普通用户。测试会留下一个带时间戳的会话。
- 测试模型必须能按提示回复 `MOVO_E2E_OK`；若使用固定响应的模型桩，设置 `MOVO_E2E_EXPECTED_TEXT` 为其响应文本。
- 首次安装：`cd qa && npm install && npx playwright install chromium`。

## 每次发版执行

进入 `qa` 目录运行，变量值换成当前候选环境的真实信息：

```bash
cd qa
MOVO_E2E_BASE_URL=http://127.0.0.1:3000 \
MOVO_E2E_USERNAME=release-qa \
MOVO_E2E_PASSWORD='your-test-password' \
npx playwright test --config release-smoke.config.ts
```

也可以先在当前会话提供环境地址与专用测试账号，让 Codex 执行同一命令并报告结果。不要把密码提交到仓库或写进测试文件。

测试退出码为 0 且 HTML 报告显示全部通过，表示基础自动化回归通过；完整用户端浏览器门禁还须通过验收清单，其中文章 Word、PDF 和文档翻译交付是必跑项。失败时检查 `qa/evidence/release-smoke/report/index.html` 及 `results/` 中的截图、视频和 trace；修复后在**同一候选提交及部署**重新跑。在 `qa` 目录执行 `npx playwright show-report evidence/release-smoke/report` 可查看报告。

## 覆盖范围与边界

覆盖登录、新建会话、多轮任务提交、请求成功、回答内容、刷新后会话持久化及重开。现有 `qa/session-sharing-realtime.spec.ts` 是需特定 QA 种子环境的会话分享专项，不包含在本套件里。停止、运行中恢复、停止/失败后的新会话重新开始与会话隔离（U03、U13、U14、U33）、分享、工具、Skill、文件、文章 Word/PDF 下载、文档翻译及中英文界面按完整浏览器验收清单执行；下载卡片和下载文件内容必须实测，模型回答声称“已导出”不足以通过。发版流程中的跨架构部署、备份恢复和其他人工功能检查仍按原清单执行。
