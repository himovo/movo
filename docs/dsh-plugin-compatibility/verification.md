# DSH 插件兼容验证记录

## 2026-11-08 Client UI 接口复核

- MOVO 新增独立浏览器 Origin、短期签名入口和逐请求的插件授权复核；DSH Operator Cookie 只保留在 Runtime Host 内，浏览器收不到。入口只加载当前插件的 Client 模块及其依赖，Host 路由和一元 Remote 方法按安装时归属清单放行；DSH 插件管理、终端、工作区等未归属接口仍拒绝。
- 本地浏览器使用 Host+Client 测试插件完成页面打开、按钮调用插件 Host 路由并得到 `FIXTURE_UI_READY`；Runtime Host 定向测试 7 项、chat-api 授权与能力投影测试 11 项、用户端 TypeScript 检查通过。测试插件不能代替四个指定真实插件的业务验收。
- DSH 的 `/api/remote.mux` WebSocket 仍未向插件页面开放。依赖远程流或完整 DSH 会话布局的 Client UI 不能据此判为可用；当前受限页面主要覆盖自有 Host 路由和归属明确的一元 Remote 调用。
- 四个指定插件的当前 npm 版本声明的 DSH 引擎范围高于 MOVO 锁定的 `0.2.1-alpha.1`。实际安装仍须以 DSH 原生检查为准；不能因为测试插件页面成功就宣称这些版本已通过页面和业务验收。
- 用户端旧版 `dsh-media-desk` 记录可能已保存 Client 模块但没有新增的页面路由字段，导致“发现插件界面”可见而“打开插件界面”按钮隐藏。入口条件现按已激活的 Client 模块显示；点击时只对缺少页面能力字段的旧记录做一次能力复核，不会为了补界面元数据将正在运行的插件标记为不可用。页面接口仍由服务端逐次验证；缺失时返回明确错误，不开放整个 DSH Web Host。

> 2026-11-07，本地开发环境。尚未通过完整验收，不能作为发布结论。

## 已验证

| 对象 | 固定版本 | DSH 原生安装及会话发现 | 实际业务任务 |
| --- | --- | --- | --- |
| `dsh-guizang-design` | `0.1.4` | 2 个工具、5 个用户可调用 Skill、浏览器模块 | 未验证 |
| `dsh-media-desk` | `2.6.1` | 无对话工具、浏览器模块；Runtime 已激活 | 未验证 |
| `dsh-context` | `0.82.2` | 无对话工具、浏览器模块；Runtime 已激活 | 未验证 |
| `agentero-dsh` | `0.1.6` | 5 个工具、4 个浏览器模块 | 未验证 |

上述安装通过当前锁定的 DSH `0.2.1-alpha.1` 原生 `inspect`、安装、隔离 Runtime 启动和 Session 能力读取。版本与能力以运行时结果为准。检测到浏览器模块仅说明模块已注册；不代表 MOVO 已安全提供插件页面。

`dsh-guizang-design@0.1.4` 的 `humanizer-zh` 已在本地真实 DSH Runtime 中完成手动选择到模型调用的接口验证：Session 发现该 Skill 的 `provider=guizang-design`、`source=bundled` 和 `userInvocable=true`；带插件选择 ID 的提交被原生 DSH 识别为 `skill-invocation`，并产生完整 `turn/end`。模型网关使用确定性测试响应，未执行真实润色业务任务，因此上表仍记“未验证”。

独立依赖型 Skill 候选为 Anthropic `skills` 仓库的 `slack-gif-creator`，固定提交 `2c5958ecac7cee2b583967a2c4981d0f4a75c579`。其 `requirements.txt` 声明 Pillow、imageio、imageio-ffmpeg、NumPy，附带 GIF 生成脚本。尚未在 MOVO 沙箱中完成安装和执行。

本地打包产物为 `/tmp/movo-slack-gif-creator-2c5958e.zip`，SHA-256 为 `6b27a43a7cd09d38509ed12b3023342c042fe479c7e36a0cea85cddf12e007a9`。离线收集器已识别四条版本范围依赖；这项静态检查不能代替容器安装与 GIF 产物核对。

## Client UI 边界

本地启动 `dsh-media-desk` 的原生 DSH Web Host 后，未认证的页面请求返回 `401`。以 DSH 原生启动令牌换取浏览器 Cookie 后，原生首页 `/` 返回 `200`，而 `/media-desk/` 返回 `404`。这说明该插件通过 DSH Client 模块注册到原生页面，并没有独立的静态页面路由。

不能将 DSH 整个 Web UI 直接作为 MOVO 插件页面开放：它同时包含 DSH 自身的其他页面和 API。后续需要在 MOVO 用户鉴权、插件授权与同一隔离 Runtime/Session 的约束下，验证 Client 模块加载和所需 RPC 的最小边界。只有页面实际打开、执行任务、权限撤销后拒绝访问，才算完成阶段 C。

## 尚未通过的计划验收

以下为 2026-11-07 的阶段快照；命令入口等后续进展以文末的 2026-11-08 记录为准。

- 插件命令的 MOVO 对话入口及其事件持久化。
- Client UI 页面和真实媒体、上下文任务。
- 插件模型提供方名称仅在管理端作诊断展示，不进入 MOVO 模型选择器（2026-11-08 产品范围调整）。
- 企业授权、撤权、直接请求及旧会话测试。
- 异机断公网的镜像和离线包迁移，以及真实插件和独立 Skill 的业务任务。

本机没有 Docker，也没有运行 MongoDB。此前 Python 插件/Profile 扩展回归有 `96` 个通过、`2` 个在 MongoDB fixture 初始化时失败，未执行对应断言；本次定向接口测试结果见下文。下一步须在具备 Docker、MongoDB 和独立内网目标机的环境继续验证。

## 2026-11-08 接口及包源补充验证

- `/api/dsh-plugins/personal/selectable-skills` 的 HTTP 请求、范围、关键词、分页、非用户拒绝和非法查询测试通过；插件 Skill 与命令的服务端父插件权限检查测试通过。命令还没有完整的 MOVO 对话提交入口。
- 修复 pnpm 11 忽略旧 `npm_config_*` 缓存配置的问题。使用真实 `dsh-context@0.82.2` 在线安装后，指定 pnpm store 写入约 6.9 MB，缓存写入约 1.3 MB。
- 通过 MOVO `OfflinePackageStore` 导出 ZIP，再导入另一目录并开启 `offline-only`，用同一固定版本完成 DSH 原生安装和 Session 能力发现。该本地复现没有断开整个主机网络，也不是异机 Docker 环境；仍须按方案在独立离线主机复测。
- 在隔离 DSH Runtime 中，用真实注册的测试插件命令调用 `/movo-smoke hello`，得到成功结果，并从同一 Session 的原生日志读到 `command/run` 与 `command/done`。相同命令在未授权的 Runtime Profile 中被拒绝。此测试只覆盖 Runtime Host 内部接口；MOVO 普通会话入口、结果展示与持久化仍未完成。
- Runtime Host 全量 Node 测试通过 `138/138`；chat-api 插件相关 Python 定向测试通过 `18/18`，sandbox-manager 包源及插件运行环境测试通过 `6/6`；管理端和用户端 TypeScript 类型检查均通过。本项接口测试并不等于四个指定真实插件的业务任务验收。
- 新生成的插件包源记录包含来源 DSH 版本；离线端在 DSH 原生验证之后标明来源与本机版本是否不同。旧记录没有该字段时保持未知，不把它推断为兼容。对应 Python 测试通过，前端双语类型检查通过。
- AskAI 既有 `plugin.runtime` 执行范围与组织插件资源范围的单元测试通过 `5/5`；MOVO 插件 Profile 的总开关及父插件授权定向测试通过。浏览器中的实际授权、撤权和旧会话直连仍未验证。
- MOVO 用户端的插件列表现在显式标明总隔离沙箱权限被拒绝；服务端由同一 AskAI `plugin.runtime` 策略给出该状态，不把插件已安装误显示成当前用户可执行。旧会话撤权场景新增 Profile 同步测试：撤权后若新 Runtime 暂不可用，续跑会拒绝复用旧插件 Profile。此项测试通过；运行中会话与真实企业环境仍需联调。
- 产品范围调整后仅调用 DSH 原生 `llm.listProviders()`，按提供方 ID 做差量并在管理端显示诊断；不再调用 `llm.listModels(provider)`，避免为不会进入 MOVO 模型选择器的目录增加安装检查耗时。用户端不展示插件模型提供方。对应 Node/Python 定向测试及双端 TypeScript 类型检查通过。
- AskAI `plugin.runtime` 总开关和组织插件资源授权的现有策略再次核对，AskAI 策略单元测试 `5/5` 通过；MOVO 插件 Skill 列表、服务端调用授权及撤权后的旧 Profile 测试合计 `19/19` 通过。这些结果证明策略可复用，不代表所有执行入口已经完成企业版验收。

## 2026-11-08 对话命令和运行时状态复核

- MOVO 普通会话的 `/` 菜单现在合并原生 Skill、插件贡献的用户可调用 Skill 和 DSH 命令，标注来源。命令使用独立选择 ID，服务端授权后调用 DSH 原生 `commands.execute`，持久化原生事件和对话终态；进程重启后可由 `command/run` 和 `command/done` 恢复终态。DSH Runtime Host 全量测试 `138/138`、相关 Python 命令和恢复测试 `25/25`、双端类型检查通过。这是接口层验证，不是实际浏览器任务验收。
- 安装时的插件能力快照加入 DSH 模型提供方。它仅表示提供方已被 DSH 发现，不进入 MOVO 模型选择器。
- 当 DSH Runtime 激活时跳过失败插件，MOVO 将失败状态写回对应插件记录。能力列表过滤失败插件，避免继续展示安装时留下的 Skill/命令快照。状态写回和过滤的定向测试通过。
- 企业版现有 `plugin.runtime` 总范围和组织插件授权由 MOVO 的插件列表、安装/启用、Skill 和命令服务端入口复用；AskAI 不需要增加另一套插件子权限。Client UI 尚未接入；插件模型不作为 MOVO 对话入口。

## 当前阻断完整交付的接口缺口

2026-11-08 补充：运行中的 DSH 版本现由 Host 读取实际安装包，并与锁定版本核对；不一致时阻止插件安装。chat-api 会在后台扫描已启用插件；版本变化时先暂停旧能力投影，再调用 DSH 原生安装与隔离 Runtime 验证，更新能力清单。未启用的旧插件在启用前也会按当前 DSH 复检，版本不兼容时不能启用。运行时激活失败在冷却后自动复检。版本不兼容与其他安装失败分开标记，保留原始诊断；异常中断的复检会在租约过期后重试。使用 Node 24 运行 Host 全量测试 `139/139`，Python 插件相关定向测试 `31/31`，双端 TypeScript 类型检查通过。本机默认 Node 14 不满足 Host 声明的 Node 22/24 版本要求，在该版本下测试会因 DSH 使用 `Promise.withResolvers` 失败。此项仍不能替代真实容器升级、旧会话续跑和四个插件业务任务验证。

后续补充：此前曾增加 DSH 原生模型目录、超时和失败诊断；产品范围调整后已移除目录查询，仅保留提供方名称。后台复检结果增加待复检状态的条件写入，避免覆盖同时发生的手动验证。AskAI 原有插件执行范围和组织插件资源范围定向测试 `5/5`。Client UI 的授权代理仍未实现。

安装前预检现由管理端和用户端先调用 MOVO 的只读接口：核对运行中 DSH 与锁定版本，在一次性 Runtime 内运行 DSH 原生 `inspect`，读取包名、精确版本、来源和原始拒绝原因，并清理该 Runtime。界面先展示结果，用户再点击安装；安装源地址在返回前剔除凭据和查询参数。离线模式仅检查已导入的本地插件包，不回退到公网。可识别的包标为“待运行验证”；Git/tarball 等 DSH 原生预检不能给出包名和版本时标为“未验证”，仍可继续隔离安装验证。npm 源拒绝 `latest` 和版本范围，直接调用安装 API 也无法绕过。实际版本兼容与能力可用须在 Runtime 启动后判定。此预检的 Python 定向测试 `7/7` 通过，两端 TypeScript 类型检查通过；上传归档继续由安装流程内的 DSH 原生检查负责，浏览器和 Docker 联调尚未完成。

- DSH Client 模块依赖完整原生 Web Host 的模块图、浏览器 Cookie 和 Connection RPC。MOVO 的普通用户 Profile 哈希包含 `subject_user_id`，因此同一 Profile Runtime 通常已按用户区分；但同一用户的多个会话仍共享 Runtime。更关键的是，DSH `HostConnectionService` 对每个通过 Cookie 认证的浏览器请求使用同一个 `OperatorPeer`，原生 Web 组合还注册插件管理、终端、工作区文件等 API。直接代理或嵌入会让插件页面拥有超出该插件授权范围的 Host 能力。需要在 MOVO 用户、插件、会话授权下建立受限 RPC/Fetch 代理，且证实真实 Client 模块可以在该约束下运行；仅按用户拆 Runtime 不能替代逐请求授权。
- 2026-11-08 再次核对 DSH `0.2.1-alpha.1` 的源码：`@deepseek-ai/dsh-client-connection` 的 `HostConnectionService.register` 在注册 RPC 路由时就把处理器绑定到单一 `OperatorPeer`，`admit(request)` 只验证 Host/Origin 与浏览器 Cookie；它不会把 MOVO 用户、插件或会话身份传入原生 RPC。`@deepseek-ai/dsh-client-modules` 通过 `/plugins` 提供模块图和脚本，`dsh-media-desk` 没有独立的 `/media-desk/` 页面。因此安全接入不能只加 Vue 导航或普通 iframe。接下来必须在独立浏览器源和 MOVO 逐请求授权边界下接入原生模块与 RPC；若无法限定插件管理、终端及工作区操作，则阶段 C 不能判通过。
- 2026-11-08 产品范围调整：MOVO 已有模型中心，不再把插件提供的 DSH 模型作为新增模型类型接入。`KernelRuntime.#agentOptions()` 继续使用 `askai-model-gateway`；插件模型提供方名称只在管理端作诊断展示。阶段 B 和企业权限验收均不再要求插件模型选择或执行。
- 本机没有 Docker/MongoDB，无法完成隔离容器中的四个真实插件业务任务、依赖型独立 Skill 的实际执行，以及异机断公网迁移。交付前必须在部署环境完成这些验收，不应把离线 ZIP 导入或单元测试计为通过。
