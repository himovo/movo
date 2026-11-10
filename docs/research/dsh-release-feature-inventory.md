# DSH 逐版本功能与体验优化清单

核对日期：2026-11-06。来源为官方 GitHub Release；无 Release 的 tag 使用 tag 差异。只逐条收录“新增功能”“体验优化”，不把同一系列 RC 汇总重复条目误算成全新能力。

状态：**E** 有同类界面；**P** 有相关能力，但公布的细节尚未逐项等同；**G** 已检索的 movo 前端中未见对应入口；**V** 需要运行或视觉验收。状态基于静态代码核对，不能代替线上验收。

## [dsh-v0.1.0-rc.7](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.0-rc.7)

- **V** 各插件可自行注册设置卡片  需运行或界面验收
- **P** Codex 与 Claude Code 子代理任务接入 Job Panel  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **V** MCP/ACP 支持持久化图片附件，PTC Mode 可转发嵌套图片  需运行或界面验收
- **V** 优化 Cordis 动态插件面板  需运行或界面验收
- **V** DeepSeek 模型新增 `low` 推理强度，默认仍为 `high`  需运行或界面验收
- **V** 英文内置预设 `Code mode` 更名为 `PTC mode`  需运行或界面验收
- **P** 提问卡片支持折叠并保留草稿  [movo 代码](../../apps/user-web/src/components/chat/AnsweredQuestionMessage.vue)

## [dsh-v0.1.0-rc.8](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.0-rc.8)

- **V** 增强多模态支持度，DeepSeek 模型适配器支持配置启用原生图片请求，`/goal`、`/plan` 等命令可接收图文输入，`@` 菜单支持引用文件和会话  需运行或界面验收
- **P** Claude Code 与 Codex 子代理均可作为 Profile Bundle 按需安装，同时支持非交互权限模式和多个命名实例  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **P** Windows PTY 终端支持持久 PowerShell 会话， 并在极简模式预设中默认支持  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)
- **P** 优化布局和信息呈现，涉及HOME 目录以 `~` 缩写表示、输入框窄屏布局、反馈界面等  [movo 代码](../../apps/user-web/src/components/chat/ChatComposer.vue)
- **P** 优化界面操作，涉及侧栏搜索焦点响应、工作流面板操作、模型选择器选中操作、打开本地文件失败支持重试等  [movo 代码](../../apps/user-web/src/components/chat/ComposerModelPicker.vue)
- **P** 优化工具调用，`web_search` 支持并发查询、子代理 `reportDelivery` 会及时反馈并唤醒父任务  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **V** 优化安装与启动，改善下载依赖体积、本地运行 `dsh web` 时会自动打开浏览器  需运行或界面验收
- **V** 改善大历史会话执行分叉操作上的性能耗时  需运行或界面验收

## [dsh-v0.1.1-rc.1](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.1-rc.1)

- **V** DeepSeek 适配器新增多模态视觉理解模型 `DeepSeek-V4-Flash-Vision-Exp`  需运行或界面验收
- **P** 优化会话 Markdown 表格自适应表现、缓存命中率在 99.x% 时的精度显示、子代理会话标题切换交互  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **V** `ask_user_question` 回答内容支持多行输入、自动换行、`Shift+Enter` 换行  需运行或界面验收

## [dsh-v0.1.1-rc.2](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.1-rc.2)

- **P** DeepSeek 适配器支持优先通过 Files API 上传图像，并可复用已上传文件  [movo 代码](../../apps/user-web/src/components/chat/ChatComposer.vue)
- **V** 优化图像预处理流程：根据模型要求自动缩放并转换为合适格式  需运行或界面验收

## [dsh-v0.1.2-alpha.1](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.2-alpha.1)

- **V** 会话流默认在每个已完成回答前折叠过程内容，并默认折叠的「System prompt」  需运行或界面验收
- **V** 会话流正文宽度可自适应或拖拽调整  需运行或界面验收
- **P** 会话流每个已完成回答后可展开查看精确 token 用量  [movo 代码](../../apps/user-web/src/components/TokenUsagePage.vue)
- **V** 会话视图提供紧凑的回合导航  需运行或界面验收
- **V** 统一界面次级文字层级，会话流支持字号调节，Markdown 表格随正文字号缩放  需运行或界面验收
- **V** 插件支持在模型设置页添加提供方登录配置  需运行或界面验收
- **P** 支持注册第三方语言，并补全多语言文本  [movo 代码](../../apps/user-web/src/components/SettingsPanel.vue)
- **P** 开启子代理模型选择后，Agent 可在授权范围内选择提供方、模型和推理力度  [movo 代码](../../apps/user-web/src/components/chat/ComposerModelPicker.vue)
- **P** 启动子代理时可指定提供方、模型、推理力度和最大输出长度  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **P** Claude Code、Codex 子代理支持配置模型  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **V** Python SDK runtime 新增 Windows x64 发行包  需运行或界面验收
- **V** ACP 补齐标准会话控制、模型设置、MCP、权限和取消能力  需运行或界面验收
- **V** DeepSeek 官方适配器默认随请求提供已启用插件的包名和版本，可在配置中关闭  需运行或界面验收
- **V** DeepSeek 官方适配器新增可选的 Session 日志增量上传，默认关闭  需运行或界面验收
- **V** 改善页面启动流程，减少代码加载次数和数据量开销  需运行或界面验收
- **V** 改善会话初始化流程，减少数据传输解析开销，统一会话自有状态加载  需运行或界面验收
- **V** 改善会话记录占用的磁盘空间  需运行或界面验收
- **V** 优化输入交互中的 `/` 与 `@` 菜单图标、目录加载、文件搜索  需运行或界面验收
- **V** 会话运行中存在草稿时主按钮切换为「发送」，消息排队发送  需运行或界面验收
- **V** 输入框中的文件和会话引用在相邻文字编辑后仍保持有效  需运行或界面验收
- **P** 切换会话后仍保留未提交的提问卡片草稿  [movo 代码](../../apps/user-web/src/components/chat/AnsweredQuestionMessage.vue)
- **V** 会话流中的流式回复代码块在生成期间持续显示语法高亮  需运行或界面验收
- **P** 会话流中的提问历史显示为可读的问答卡片，并标明取消或中断后的未提交状态  [movo 代码](../../apps/user-web/src/components/chat/AnsweredQuestionMessage.vue)
- **P** 图片发送后立即显示，压缩和上传在后台继续  [movo 代码](../../apps/user-web/src/components/chat/ChatComposer.vue)
- **P** 上下文压缩会计入图片占用  [movo 代码](../../services/chat-api/app/services/session_persistence_service.py)
- **V** 轨迹视图支持展示用户、助手和工具结果中的图片  需运行或界面验收
- **V** 在本地文件系统模式下，模型可直接找到已上传图片的可读取位置  需运行或界面验收
- **P** 调整图片压缩策略，压缩更快、上传体积更小，并改善超长截图的清晰度  [movo 代码](../../apps/user-web/src/components/chat/ChatComposer.vue)
- **V** 会话日志截断尾部自动修复时输出警告并注明受影响会话  需运行或界面验收

## [dsh-v0.1.2-alpha.2](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.2-alpha.2)

- **V** 界面新增显示连接异常状态，支持自动重试和立即重连  需运行或界面验收
- **V** 会话标题区域支持查看活动的定时计划  需运行或界面验收
- **P** 插件列表按会话插件和全局插件分组，可切换 Agent Preset 查看组合、搜索其他预设  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **V** 改善会话与输入界面的菜单显示、滚动条、工具文件链接与 diff 统计  需运行或界面验收
- **V** 减少 macOS 和 Linux 加载会话时不必要的文件系统检查  需运行或界面验收
- **V** 提升长会话历史和密集实时消息的处理效率  需运行或界面验收
- **P** 回答末尾显示 token 用量和耗时，点击可查看详细统计  [movo 代码](../../apps/user-web/src/components/TokenUsagePage.vue)
- **V** `web_search` 失败时报告实际端点和错误明细  需运行或界面验收
- **P** 权限分类使用本地化内容显示  [movo 代码](../../apps/user-web/src/components/SettingsPanel.vue)
- **V** 调整首页标志的动画效果  需运行或界面验收

## [dsh-v0.1.2-alpha.3](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.2-alpha.3)

- **V** 长会话右侧导航支持预览和跳转尚未载入的全部分页轮次  需运行或界面验收
- **V** 改善长会话渲染的内存开销和代码高亮流畅度  需运行或界面验收
- **P** 优化权限标签多语言表达  [movo 代码](../../apps/user-web/src/components/SettingsPanel.vue)

## [dsh-v0.1.2-alpha.4](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.2-alpha.4)

- **V** 父 Agent 与可持续子 Agent 可通过 `send_message` 双向传递后续消息，取代单向 `report` 工具  需运行或界面验收
- **P** 自定义模型发现复用 Profile 请求头；模型目录支持搜索和筛选  [movo 代码](../../apps/user-web/src/components/chat/ComposerModelPicker.vue)
- **V** 界面优化圆角、描边、轮次导航、投影效果  需运行或界面验收
- **V** 改善超长会话在流式回复、界面布局、导航预览场景的渲染开销  需运行或界面验收

## [dsh-v0.1.2-alpha.5](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.2-alpha.5)

- 本次官方说明没有“新增功能”或“体验优化”条目。

## [dsh-v0.1.2-rc.1](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.2-rc.1)

- **V** 会话流默认在每个已完成回答前折叠过程内容，并默认折叠的「System prompt」  需运行或界面验收
- **V** 会话流正文宽度可自适应或拖拽调整  需运行或界面验收
- **P** 回答末尾显示 token 用量和耗时，可展开查看精确用量与详细统计  [movo 代码](../../apps/user-web/src/components/TokenUsagePage.vue)
- **V** 会话视图提供覆盖完整历史的回合导航，可预览并跳转尚未载入的轮次  需运行或界面验收
- **V** 统一界面次级文字层级，会话流支持字号调节，Markdown 表格随正文字号缩放  需运行或界面验收
- **V** 插件支持在模型设置页添加提供方登录配置  需运行或界面验收
- **P** 界面支持第三方语言，并统一权限分类和标签的本地化表达  [movo 代码](../../apps/user-web/src/components/SettingsPanel.vue)
- **P** 子代理模型选择支持 Agent 在授权范围内自主选择，也支持调用方指定提供方、模型、推理力度和最大输出长度，以及为 Claude Code、Codex 配置模型  [movo 代码](../../apps/user-web/src/components/chat/ComposerModelPicker.vue)
- **V** Python SDK runtime 新增 Windows x64 发行包  需运行或界面验收
- **V** ACP 补齐标准会话控制、模型设置、MCP、权限和取消能力  需运行或界面验收
- **V** DeepSeek 官方适配器默认随请求提供已启用插件的包名和版本，可在配置中关闭  需运行或界面验收
- **V** DeepSeek 官方适配器新增可选的 Session 日志增量上传，默认关闭  需运行或界面验收
- **V** 新增实验性 Inspector 工具  需运行或界面验收
- **V** 新增实验性 Web Preview  需运行或界面验收
- **V** 界面显示连接状态，容忍短暂服务端卡顿，并支持连接中断后的自动重试或立即重连  需运行或界面验收
- **V** 会话标题区域支持在不同视口宽度下查看活动的定时计划  需运行或界面验收
- **V** 父 Agent 与可持续子 Agent 可通过 `send_message` 双向传递后续消息，取代单向 `report` 工具  需运行或界面验收
- **V** 减少页面启动和会话初始化中的代码加载、数据传输与解析开销  需运行或界面验收
- **V** 改善会话记录占用的磁盘空间  需运行或界面验收
- **V** 优化 `/` 与 `@` 菜单的图标、目录加载和文件搜索，支持通过鼠标在目录层级间导航  需运行或界面验收
- **V** 会话运行中存在草稿时主按钮切换为「发送」，消息排队发送  需运行或界面验收
- **V** 输入框中的文件和会话引用在相邻文字编辑后仍保持有效  需运行或界面验收
- **P** 切换会话后仍保留未提交的提问卡片草稿  [movo 代码](../../apps/user-web/src/components/chat/AnsweredQuestionMessage.vue)
- **V** 会话流中的流式回复代码块在生成期间持续显示语法高亮  需运行或界面验收
- **P** 会话流中的提问历史显示为可读的问答卡片，并标明取消或中断后的未提交状态  [movo 代码](../../apps/user-web/src/components/chat/AnsweredQuestionMessage.vue)
- **P** 图片发送后立即显示，压缩和上传在后台继续  [movo 代码](../../apps/user-web/src/components/chat/ChatComposer.vue)
- **P** 上下文压缩会计入图片占用  [movo 代码](../../services/chat-api/app/services/session_persistence_service.py)
- **V** 轨迹视图支持展示用户、助手和工具结果中的图片  需运行或界面验收
- **V** 在本地文件系统模式下，模型可定位上传图片，并通过 `read_image` 读取没有扩展名的附件路径  需运行或界面验收
- **P** 调整图片压缩策略，压缩更快、上传体积更小，并改善超长截图的清晰度  [movo 代码](../../apps/user-web/src/components/chat/ChatComposer.vue)
- **V** 会话日志截断尾部自动修复时输出警告并注明受影响会话  需运行或界面验收
- **P** 插件列表按会话插件和全局插件分组，可切换 Agent Preset 查看组合、搜索其他预设  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **V** 改善会话与输入界面的菜单显示、滚动条、工具文件链接与 diff 统计  需运行或界面验收
- **V** 减少 macOS 和 Linux 加载会话时不必要的文件系统检查  需运行或界面验收
- **V** 提升长会话和密集实时消息的处理效率，降低内存占用以及流式回复、代码高亮、布局和导航预览的渲染开销  需运行或界面验收
- **V** `web_search` 失败时报告实际端点和错误明细  需运行或界面验收
- **V** 调整首页标志的动画效果  需运行或界面验收
- **P** 自定义模型发现复用 Profile 请求头；模型目录支持搜索和筛选  [movo 代码](../../apps/user-web/src/components/chat/ComposerModelPicker.vue)

## [dsh-v0.1.3-alpha.1](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.3-alpha.1)

- **P** Web 支持上传任意类型的通用文件：文件与图片可在同一预览区混排，后台上传支持进度、取消与会话切换续显，模型可通过已保存路径使用现有文件工具按需读取。  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)
- **V** 所有出站网络请求都会遵循启动环境中的 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 与 `NO_PROXY` 配置。  需运行或界面验收
- **V** Python SDK 新增 macOS x64 runtime wheel，可在 Intel 架构的 Mac 上安装并运行随包 runtime。  需运行或界面验收
- **V** `read_image` 的顶层与 PTC 嵌套工具调用会在 Web 工具卡中直接渲染图片，不再展示原始附件对象。  需运行或界面验收
- **P** 模型探测新增对自定义模型提供商 `models` 对象和 Anthropic 原生模型列表的支持，并支持回填模型名称、上下文窗口及最大输出 token 的回填。  [movo 代码](../../apps/user-web/src/components/chat/ComposerModelPicker.vue)
- **V** Skill 选择器支持模糊搜索；优化聊天气泡中的的 Skill 和命令引用。  需运行或界面验收
- **V** 统一会话内可点击链接的颜色、hover/focus 样式和分类图标，优化 Markdown 链接、文件引用、网页来源、产物链接与 Workflow 成员链接的辨识度。  需运行或界面验收
- **V** 统一未观察文件写入与编辑失败的 `FS_NOT_OBSERVED` 诊断，保留文件路径、结构化错误码和原始原因。  需运行或界面验收
- **P** Windows 上的本地非终端子进程不再弹出控制台窗口。  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)
- **P** Agent Team 的 `send_message` 统一采用 steer 语义，并在跨 Agent 和冷恢复投递中保留发送者归属与顺序。  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)

## [dsh-v0.1.3-alpha.2](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.3-alpha.2)

- **V** 升级 pi-ai 到 0.85.1，支持新模型。 —  需运行或界面验收
- **P** Web 顶栏新增“在应用中打开”，可用已安装的编辑器、IDE、终端或文件管理器等打开 Workspace。 —  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)
- **P** 可继续对话的子代理支持消息排队、编辑、删除、单条或全部 Steer，以及停止操作。 —  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **V** PTC 模式下支持展开查看命令及其输出。 —  需运行或界面验收
- **V** 改善长会话打开、恢复和持续对话时的卡顿，降低内存占用。 —  需运行或界面验收
- **V** 引用较长会话时，模型可按需读取预览中未展示的内容。 —  需运行或界面验收
- **V** 排队消息新增“发送中”提示，发送完成前暂不可编辑、删除或 Steer。 —  需运行或界面验收
- **V** 统一设置面板中标签、开关和插件状态的样式，改善浅色和深色主题下的显示效果。 —  需运行或界面验收
- **P** 反馈可独立提交，无需继续对话；提交时会附带相关会话内容，普通聊天不会触发这类上报。 —  [movo 代码](../../apps/user-web/src/components/chat/ChatComposer.vue)

## [dsh-v0.1.5-alpha.1](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.5-alpha.1)

- **V** 支持动态修改系统提示词且不破坏 KV Cache，模型需显式声明支持  需运行或界面验收
- **V** 新增实验性右侧 Sidebar，支持多标签、分栏与全屏；聊天文件链接和产出文件支持 Sidebar 打开，并移除原 Detail 面板  需运行或界面验收
- **P** 改善 Web 输入框的菜单层级、提示文字和间距；会话统计改为两个可展开的摘要，分别查看轮次与速度、精确 Token 用量与缓存命中。  [movo 代码](../../apps/user-web/src/components/TokenUsagePage.vue)
- **P** 内置斜杠命令说明支持中文，并随界面语言即时更新；切换语言时保留已打开菜单和查询内容。  [movo 代码](../../apps/user-web/src/components/SettingsPanel.vue)
- **P** 可选子代理插件的内置运行时升级至 Codex 0.153.4 和 Claude Code 2.1.263；显式模型配置保持不变，未配置模型时 Codex 使用上游默认值。  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)

## [dsh-v0.1.5-alpha.2](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.5-alpha.2)

- **V** 右侧 Sidebar 新增常见文档类型预览，支持 Markdown、代码高亮、HTML、PDF 、图片  需运行或界面验收
- **P** 支持模型显式在会话中交付文件，并支持在右侧 Sidebar 预览、用默认应用打开、在文件管理器中定位  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)
- **P** `/feedback` 命令新增支持提交明细反馈内容  [movo 代码](../../apps/user-web/src/components/chat/ChatComposer.vue)
- **P** 改善设置界面的本地化与可访问性：设置入口补充本地化无障碍名称，中文显示对话模式与内置模型说明  [movo 代码](../../apps/user-web/src/components/SettingsPanel.vue)

## [dsh-v0.1.5-rc.1](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.5-rc.1)

- **V** DeepSeek 模型适配器新增 `DeepSeek-V41-Flash`（`deepseek-flash`）支持文本、图片及会话历史中的系统提示词更新。新会话默认使用该模型，配置文件显式指定模型时以配置值为准。  需运行或界面验收
- **P** Web 支持上传任意类型的通用文件：文件与图片可在同一预览区混排，后台上传支持进度、取消与会话切换续显，模型可通过已保存路径使用现有文件工具按需读取。  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)
- **P** 可继续对话的子代理支持消息排队、编辑、删除、单条或全部 Steer 与停止操作；排队消息发送期间显示“发送中”，并暂不可编辑、删除或 Steer。  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **V** 支持动态修改系统提示词且不破坏 KV Cache，模型需显式声明支持。  需运行或界面验收
- **P** Web 右侧 Sidebar 支持多标签、分栏、全屏以及 Markdown、代码、HTML、PDF 和图片预览，包括子代理和未激活会话的文件；模型可显式交付文件，并可在 Sidebar 中预览、用默认应用打开或在文件管理器中定位。原 Detail 面板已移除。  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)
- **P** 模型探测新增对自定义模型提供商 `models` 对象和 Anthropic 原生模型列表的支持，并支持回填模型名称、上下文窗口及最大输出 token 的回填。  [movo 代码](../../apps/user-web/src/components/chat/ComposerModelPicker.vue)
- **V** 所有出站网络请求都会遵循启动环境中的 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 与 `NO_PROXY` 配置。  需运行或界面验收
- **P** Web 顶栏新增“在应用中打开”，可用已安装的编辑器、IDE、终端或文件管理器等打开 Workspace。  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)
- **P** 反馈可独立提交，无需继续对话；`/feedback` 命令支持提交明细反馈内容，提交时附带相关会话内容。  [movo 代码](../../apps/user-web/src/components/chat/ChatComposer.vue)
- **V** Web 可直接显示顶层及 PTC 嵌套 `read_image` 的图片结果，以及模型回复中引用的 POSIX 绝对路径本地图片，包括工作区外截图；加载失败时显示替代文字或原路径。  需运行或界面验收
- **V** Skill 选择器支持模糊搜索；优化聊天气泡中的的 Skill 和命令引用。  需运行或界面验收
- **V** 调整会话内可点击链接的颜色、hover/focus 样式和分类图标，优化 Markdown 链接、文件引用、网页来源、产物链接与 Workflow 成员链接的辨识度。  需运行或界面验收
- **P** Windows 上的本地非终端子进程不再弹出控制台窗口。  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)
- **P** Agent Team 的 `send_message` 统一采用 steer 语义，并在跨 Agent 和冷恢复投递中保留发送者归属与顺序。  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **V** 改善长会话打开、恢复和持续对话时的卡顿，降低内存占用。  需运行或界面验收
- **V** 引用较长会话时，模型可按需读取预览中未展示的内容。  需运行或界面验收
- **P** 改善设置面板的标签、开关状态样式，改善浅色和深色主题下的显示效果，改善本地化与可访问性  [movo 代码](../../apps/user-web/src/components/SettingsPanel.vue)
- **V** PTC 模式下支持展开查看命令及其输出。  需运行或界面验收
- **P** 改善 Web 输入框的菜单层级、提示文字和间距；会话统计改为两个可展开的摘要，分别查看轮次与速度、精确 Token 用量与缓存命中。  [movo 代码](../../apps/user-web/src/components/TokenUsagePage.vue)
- **P** 内置斜杠命令说明支持中文，并随界面语言即时更新；切换语言时保留已打开菜单和查询内容。  [movo 代码](../../apps/user-web/src/components/SettingsPanel.vue)

## [dsh-v0.1.5-rc.2](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.5-rc.2)

- **P** 优化反馈提交体验：点赞和点踩均通过弹窗确认后提交，提交失败时保留已填写内容并给出提示。  [movo 代码](../../apps/user-web/src/components/chat/ChatComposer.vue)
- **P** 优化交付文件卡片的排版和对话间距，更新代码文件图标，让文件更易辨认、界面更紧凑。  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)

## [dsh-v0.1.5-rc.3](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.5-rc.3)

- 此 tag 没有独立 Release 文案。与前一 tag 对比仅见依赖锁定及发布元数据，未见用户功能或体验优化。[差异](https://github.com/deepseek-ai/deepseek-harness/compare/dsh-v0.1.5-rc.2...dsh-v0.1.5-rc.3).

## [dsh-v0.1.6-alpha.1](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.6-alpha.1)

- **P** Web 侧边栏新增终端，支持多标签、Shell 选择和刷新后恢复。  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)
- **V** 设置中新增已归档会话列表，支持查看和恢复会话。  需运行或界面验收
- **V** MCP 支持发现和读取资源、使用 URI 模板。内置 Profile 配置 MCP 服务器后可使用共享资源工具。  需运行或界面验收
- **V** Headless 支持从标准输入接收任务，用 `--session-id` 继续已有会话，用 `--json` 逐行输出 JSON 运行事件。  需运行或界面验收
- **V** 扩展文件、命令及 PTC 工具，支持 DSH 在本地运行，通过 SSH 使用远端工作区。  需运行或界面验收
- **V** 新增实验性 Browser Use 支持，包含 Playwright MCP、Chrome DevTools MCP 和 Stagehand 浏览器后端。  需运行或界面验收
- **V** 新增实验性 Computer Use 支持，可通过 Cua Driver MCP 或原生驱动操作本机、获取截图。  需运行或界面验收
- **V** 新增实验性 Auto review 模式。  需运行或界面验收
- **P** 文件、Skill 引用及交付文件链接默认由侧边栏预览。  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)
- **V** 支持在 Agent Presets 设置中关闭模式切换 UI。  需运行或界面验收
- **P** 优化文件预览，保留文件树滚动位置，图片和 PDF 随面板适配，并简化预览器选择及加载、格式提示。  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)
- **V** Trajectory 支持展开和复制 JSON 字符串、查看 PTC 代码及调用结果，推理默认展开，并恢复记录中的运行耗时。  需运行或界面验收
- **V** 调整输入框加号菜单的分组，将文件添加入口移入菜单，移除独立附件按钮，并统一斜杠菜单的中英文命令展示。  需运行或界面验收
- **V** 连接提示区分自动与手动重连，支持点击重试，并减少提示闪烁。  需运行或界面验收
- **V** 轮次运行超过一小时后，耗时按小时、分钟和秒显示。  需运行或界面验收
- **P** 为适配 DeepSeek V4.1，调整图片缩放和 Token 估算，提高默认请求图片尺寸和编码质量。  [movo 代码](../../apps/user-web/src/components/TokenUsagePage.vue)
- **V** 提升持久 Bash 处理大量历史输出时的效率。  需运行或界面验收
- **V** 文档站的 Mermaid 图表支持全屏查看、缩放和平移。  需运行或界面验收
- **V** Node PTC 的 `run_code` 支持按次设置超时时间，默认 120 秒、最多 600 秒。  需运行或界面验收
- **V** MCP 升级至官方 SDK v2，支持协议协商、工具分页，以及未提供工具的服务器。  需运行或界面验收
- **V** 推理和压缩摘要展开后，标题随滚动吸顶，方便折叠，且不遮挡摘要中的代码复制按钮。  需运行或界面验收
- **P** 改善 Web 终端文字和光标对比度，切换主题时保留应用配色；刷新后的新视图暂不恢复该配色。  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)

## [dsh-v0.1.6-alpha.2](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.6-alpha.2)

- **P** 新增插件管理页，支持插件安装和修改配置，支持实时开启禁用插件。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **P** 会话新增回合结束时文件改动卡片，并支持在侧边栏逐文件对比审阅。  [movo 代码](../../apps/user-web/src/components/code/WorkspaceChanges.vue)
- **P** 支持在侧边栏预览 Office 文件，目前支持 Word、Excel 和 PowerPoint 类型。  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)
- **V** 支持在侧边栏以浏览器模式访问指定 URL。  需运行或界面验收
- **P** 支持在侧边栏打开 Subagent 会话。  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **V** 支持在侧边栏预览提交计划。  需运行或界面验收
- **V** 工作区列表支持按目录层级分组。  需运行或界面验收
- **P** 侧边栏布局支持持久化，刷新前后侧边栏终端维持连接。  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)
- **P** 改善文件引用与侧边栏操作，支持直接打开已有文件，并在首次发送消息前使用文件预览和终端。  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)
- **V** 统一输入框菜单的键盘操作，支持方向键选择、Enter 或 Tab 确认、Escape 关闭。  需运行或界面验收
- **V** Trajectory 统一展示文本、图片和文件附件，预览支持附件缩略图。  需运行或界面验收
- **V** 思考内容支持紧凑的 Markdown 排版。  需运行或界面验收
- **P** 上下文用量移至输入框底部，点击可查看明细。  [movo 代码](../../apps/user-web/src/components/TokenUsagePage.vue)
- **V** 改善 CLI 及 Web 启动等候时间。  需运行或界面验收

## [dsh-v0.1.7-alpha.1](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.7-alpha.1)

- **P** 侧边栏会话支持置顶、归档管理、筛选、撤销归档及从搜索结果恢复。  [movo 代码](../../apps/user-web/src/components/SessionHistorySidebar.vue)
- **P** 对运行中会话归档，会列出受影响的回合、子代理、任务和提醒，新增「停止并归档」确认。  [movo 代码](../../apps/user-web/src/components/scheduled-tasks/ScheduledTaskPage.vue)
- **P** 新增「工作过程展示」「性能与用量」「开发者工具」设置；连续思考与工具调用合并为可折叠过程组，支持简洁、详细及运行中完全展开。开发者工具默认开启，关闭时仍显示第三方会话标签页。  [movo 代码](../../apps/user-web/src/components/TokenUsagePage.vue)
- **V** 可在任务列表中确认停止运行中的任务；长时间运行的命令可按配置在等待超时后转入后台继续执行，工作流也支持后台运行。  需运行或界面验收
- **V** 全新安装首次启动时自动创建默认工作区和空白会话，无需先选择文件夹。  需运行或界面验收
- **P** 会话右上角菜单新增反馈入口，可直接提交当前会话的反馈。  [movo 代码](../../apps/user-web/src/components/chat/ChatComposer.vue)
- **P** 文件预览在回合结束后自动更新，并支持响应本地文件变化  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)
- **P** 文件预览、交付卡片和改动审阅支持使用系统默认或其他关联应用打开文件、显示文件位置，不支持预览的文件也可直接打开。  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)
- **P** 文件改动审阅默认使用左右分栏，支持代码高亮和左右同步滚动。  [movo 代码](../../apps/user-web/src/components/code/WorkspaceChanges.vue)
- **P** 文件改动卡片支持悬停查看单栏差异，无需先打开侧边栏；侧边栏仍默认左右分栏。  [movo 代码](../../apps/user-web/src/components/code/WorkspaceChanges.vue)
- **P** 调整文件交付指引，优先在回复中展示结果，减少交付卡片与正文的重复展示。  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)
- **V** 统一界面图标、状态标记、菜单和滚动条的视觉样式，保留失败与中断状态的清晰提示。  需运行或界面验收
- **P** 优化会话中设置，目标、待办、定时任务及多种工具的历史结果展示，由 JSON 调整为，更紧凑的卡片展示  [movo 代码](../../apps/user-web/src/components/scheduled-tasks/ScheduledTaskPage.vue)
- **V** 改善长对话的初始化加载、轮次导航跳转、加载历史开销  需运行或界面验收
- **P** Team 工具统一以成员名称作为操作目标；子代理和 Team 统一空闲/就绪状态显示。  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **V** Team 任务看板改为只读，任务创建和更新由 Agent 通过工具完成。  需运行或界面验收
- **V** 后台任务列表支持展开查看实时输出。  需运行或界面验收
- **V** 内置 Agent 模式提供用途说明、使用指南和示例任务，帮助选择适合的模式。  需运行或界面验收
- **V** 模型页统一为「添加模型提供商」入口，可在第三方提供商和自定义 API 之间切换并保留草稿。  需运行或界面验收
- **P** 工作区会话列表分批展开，运行中会话及有运行中子代理的父会话保持可见。  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **V** 输入栏空间不足时自动将模型名称收为图标，空间恢复后重新显示，减少控件换行。  需运行或界面验收
- **V** 侧边栏 Excel 预览支持只读预览 XLSX、XLS、CSV 和 TSV，可切换工作表、选择和复制单元格、查看公式；部分不支持内容会提示。  需运行或界面验收
- **V** PDF、Office 和图片预览统一缩放控件，默认适应宽度，支持百分比缩放和手势缩放，并保留当前标签页的缩放比例。  需运行或界面验收

## [dsh-v0.1.7-alpha.2](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.7-alpha.2)

- **V** 稳定会话与工作过程组的滚动跟随；改善历史分页与轮次跳转，并减少发送消息的瞬间跳动或重复显示。  需运行或界面验收
- **P** 统一会话区域各代码块样式，支持复制/换行，并改善差异内容和行号展示。  [movo 代码](../../apps/user-web/src/components/code/WorkspaceChanges.vue)
- **V** 重新编辑排队消息时保留换行，避免多行内容发送给模型时合并成一行。  需运行或界面验收
- **P** Agent Team 成员的初始任务增加查找队友和联系 Lead 的指引，明确按成员名称发送消息。  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **V** 首次安装插件且未配置源时，优先寻找最优可访问 npm 源；保留手动选择和私有源配置。  需运行或界面验收

## [dsh-v0.1.7-rc.1](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.7-rc.1)

- **P** Web 侧边栏新增终端，支持多标签、Shell 选择和刷新后恢复。  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)
- **P** 管理会话归档：支持置顶、筛选、恢复，并在归档运行中会话时确认受影响的任务。  [movo 代码](../../apps/user-web/src/components/SessionHistorySidebar.vue)
- **V** MCP 支持发现和读取资源、使用 URI 模板。内置 Profile 配置 MCP 服务器后可使用共享资源工具。  需运行或界面验收
- **V** Headless 支持从标准输入接收任务，用 `--session-id` 继续已有会话，用 `--json` 逐行输出 JSON 运行事件。  需运行或界面验收
- **V** 扩展文件、命令及 PTC 工具，支持 DSH 在本地运行，通过 SSH 使用远端工作区。  需运行或界面验收
- **V** 新增实验性 Playwright MCP、Chrome DevTools MCP 和 Stagehand 浏览器后端。  需运行或界面验收
- **V** 新增实验性 Computer Use 支持，可通过 Cua Driver MCP 或原生驱动操作本机、获取截图。  需运行或界面验收
- **V** 新增实验性 Auto review 模式。  需运行或界面验收
- **P** 会话文件改动可在卡片和侧边栏审阅；差异支持逐行、左右分栏、高亮、同步滚动与悬停预览，并改善明暗主题配色。  [movo 代码](../../apps/user-web/src/components/code/WorkspaceChanges.vue)
- **P** 插件管理页支持安装、配置、启停和运行时卸载。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **V** 侧边栏可预览 Word、Excel、PowerPoint、CSV 和 TSV；Excel 支持工作表、单元格、公式与复制，并改善窄面板中的控件和触控板滚动。  需运行或界面验收
- **V** 支持在侧边栏以浏览器模式访问指定 URL。  需运行或界面验收
- **P** 支持在侧边栏打开 Subagent 会话。  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **V** 侧边栏可预览提交计划；计划审阅在其他面板打开期间到达后仍可查看全文。  需运行或界面验收
- **P** 插件安装可选择官方源、国内镜像或自定义源；首次安装自动选择可访问的源，GitHub 网络失败后可改用镜像重新输入包名。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **P** 实验性语音转写首次使用时准备本地模型；支持自动或手动选择 Hugging Face 与 HF-Mirror 下载源，并在自动模式下尝试其他可用源。  [movo 代码](../../apps/user-web/src/components/chat/ComposerModelPicker.vue)
- **P** Agent Team 面板实时展示成员与任务，并可从会话页头查看或切换成员。  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **V** 聊天中的本地图片可直接查看和放大；图片链接在悬停或键盘聚焦时提供预览。  需运行或界面验收
- **V** 图片、PDF 和 Office 预览使用统一缩放控件，保留每个标签页的缩放比例；捏合缩放后重新绘制页面以保持文字清晰。  需运行或界面验收
- **P** 为适配 DeepSeek V4.1，调整图片缩放和 Token 估算，提高默认请求图片尺寸和编码质量。  [movo 代码](../../apps/user-web/src/components/TokenUsagePage.vue)
- **V** MCP 升级至官方 SDK v2，支持协议协商、工具分页，以及未提供工具的服务器。  需运行或界面验收
- **P** 改善文件引用与侧边栏操作，支持直接打开已有文件，并在首次发送消息前使用文件预览和终端。  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)
- **V** 长时间命令和工作流可转入后台；任务面板显示实时输出，后台任务完成后会继续唤醒所属会话。  需运行或界面验收
- **V** 全新安装首次启动时自动创建默认工作区和空白会话，无需先选择文件夹。  需运行或界面验收
- **P** 文件预览在回合结束后自动更新，并支持响应本地文件变化  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)
- **P** 文件预览、交付卡片和改动审阅支持使用系统默认或其他关联应用打开文件、显示文件位置，不支持预览的文件也可直接打开。  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)
- **V** 改善长对话的初始化加载、轮次导航跳转、加载历史开销  需运行或界面验收
- **V** Team 工具按成员名称操作，并在成员初始任务中提供查找队友和联系 Lead 的指引。  需运行或界面验收
- **V** Team 任务看板改为只读，任务创建和更新由 Agent 通过工具完成。  需运行或界面验收
- **V** 模型页统一为「添加模型提供商」入口，可在第三方提供商和自定义 API 之间切换并保留草稿。  需运行或界面验收
- **V** 稳定会话与工作过程组的滚动跟随；改善历史分页与轮次跳转，并减少发送消息的瞬间跳动或重复显示。  需运行或界面验收
- **P** 统一会话区域各代码块样式，支持复制/换行，并改善差异内容和行号展示。  [movo 代码](../../apps/user-web/src/components/code/WorkspaceChanges.vue)
- **V** 模型发现列表显示原始模型 ID，悬停可见名称，仍可按名称或 ID 搜索。  需运行或界面验收
- **V** 「工作过程展示」设置可在简洁、标准、详细和运行中完全展开模式间切换；连续思考与工具调用归为可折叠过程组。  需运行或界面验收
- **V** 工具调用在生成参数时显示准备状态；写入或编辑文件时显示内容准备进度。  需运行或界面验收
- **P** 「性能与用量」设置可控制聊天中性能和用量信息的显示详略。  [movo 代码](../../apps/user-web/src/components/TokenUsagePage.vue)
- **V** 「开发者工具」设置控制诊断入口；插件提供的标签页保持可见。  需运行或界面验收
- **V** Windows 可通过系统关联应用打开配置文件和其他本地文件。  需运行或界面验收
- **V** Office 任务默认使用随应用安装的 LibreOffice 运行环境。  需运行或界面验收

## [dsh-v0.1.7-rc.2](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.7-rc.2)

- **P** 启用定时任务后，可创建和管理提醒、查看运行记录；重启后任务仍会保留，并支持最短每分钟重复一次。  [movo 代码](../../apps/user-web/src/components/scheduled-tasks/ScheduledTaskPage.vue)
- **V** 桌面端新增首次使用引导，介绍可用额度，并帮助选择用途和工作过程的展示方式；中途退出后可继续。  需运行或界面验收
- **E** Web 和桌面端支持查看、搜索、自定义及恢复快捷键，侧边栏同步显示当前键位。  [movo 代码](../../apps/user-web/src/components/settings/ShortcutPreferencesPanel.vue)
- **V** 支持动态增加工具且不破坏 KV Cache，模型需显式声明支持。  需运行或界面验收
- **V** 自动审阅拒绝操作后，允许人工审批的会话可由用户决定是否继续；审阅失败会单独提示。  需运行或界面验收
- **V** 关闭桌面窗口后，任务继续在后台运行；退出应用前会提示对任务的影响。  需运行或界面验收
- **V** 归档筛选支持“隐藏已归档／全部对话／仅显示已归档”；仅查看归档时隐藏没有归档对话的工作区。  需运行或界面验收
- **P** 工具卡片、文件预览和代码差异的语法高亮更一致，并支持更多文件类型。  [movo 代码](../../apps/user-web/src/components/code/WorkspaceChanges.vue)
- **V** 文档预览的加载提示更清晰，页面间距和浅色主题背景更易阅读。  需运行或界面验收
- **P** 界面圆角、菜单和悬停样式更统一，单文件改动及纯新增或纯删除的差异展示更紧凑。  [movo 代码](../../apps/user-web/src/components/code/WorkspaceChanges.vue)
- **V** 键盘操作时的焦点提示更一致，鼠标操作后不再误显示焦点框。  需运行或界面验收
- **V** 切换模型时显示等待提示，并减少切换后的等待时间。  需运行或界面验收
- **V** 不兼容插件的跳过提示每次启动只显示一次，避免重复打扰。  需运行或界面验收
- **P** 插件安装时可清楚辨认当前使用的官方源或镜像，重复选项合并显示。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **P** 审批卡片支持跟随界面语言显示说明，并引导 Agent 使用用户提问的语言解释审批理由。  [movo 代码](../../apps/user-web/src/components/SettingsPanel.vue)
- **P** 中文插件管理与设置页统一使用「子智能体」名称。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **V** 折叠的网页抓取卡片可直接点击网址打开网页，无需先展开卡片。  需运行或界面验收

## [dsh-v0.2.0-rc.1](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.0-rc.1)

- **V** 优化对话进行中和完成状态的实时动画、用时信息、过程信息间距。  需运行或界面验收
- **V** 改善会话在图片失效后自动重传并继续请求的可靠性。  需运行或界面验收
- **V** 桌面更新提示补全版本、下载和重试说明。  需运行或界面验收
- **V** 无标题的历史会话统一显示「未命名」，重命名时提供空白输入。  需运行或界面验收
- **P** 改善插件管理界面、内置插件界面布局及交互，改善安装引导。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **V** 改善深色主题下的开关色彩区分度。  需运行或界面验收
- **V** 改善 Office 与 PDF 预览的文字选区在浅色、深色主题下的清晰度。  需运行或界面验收
- **V** 改善插件配置保存操作的等待时间。  需运行或界面验收
- **V** 创造模式完善插件开发指引，并提供体验技能。  需运行或界面验收
- **P** 使用 DeepSeek 账号模型的会话无需配置额外 API Key 即可进行网页搜索。  [movo 代码](../../apps/user-web/src/components/SessionSearchOverlay.vue)

## [dsh-v0.2.0-rc.2](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.0-rc.2)

- **P** 模型选择器在模型较多时提供搜索，支持模糊匹配和键盘选择。  [movo 代码](../../apps/user-web/src/components/chat/ComposerModelPicker.vue)
- **V** 侧栏文件页可直接用本地应用打开当前文件夹，并记住应用选择。  需运行或界面验收
- **V** 优化聊天耗时、过程信息、字号和深色主题样式，优化动画运行开销。  需运行或界面验收
- **P** 精简插件安装引导，并区分已安装、不兼容和内置插件的升级提示。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **P** 自动化任务投递的提醒改为明确标注的用户定时消息，不再要求 Agent 仅将其作为不可信提醒内容转述。  [movo 代码](../../apps/user-web/src/components/scheduled-tasks/ScheduledTaskPage.vue)
- **P** 加强 Bash 与 PowerShell 的工具提示，提醒 Agent 在删除或移动前核对实际目标路径，以避免路径误判。  [movo 代码](../../apps/user-web/src/components/scheduled-tasks/ScheduledTaskPage.vue)

## [dsh-v0.2.1-alpha.1](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.1-alpha.1)

- **P** 改善自动化任务详情在窄窗口中的布局，关联会话入口会按可用空间收起为图标。  [movo 代码](../../apps/user-web/src/components/scheduled-tasks/ScheduledTaskPage.vue)
- **V** 组合包详情页显示代码来源和当前版本，便于查看安装来源及重装所需的信息。  需运行或界面验收
- **V** 工具调用在准备阶段即可显示已到达的命令说明、文件路径和内容生成进度。  需运行或界面验收
- **V** 加快大量会话的列表读取，同时继续为其他操作提供执行机会。  需运行或界面验收
- **P** 插件安装结果显示实际安装版本；因新版本冷却策略安装较旧版本时，提供说明和精确版本安装方式。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)

## [dsh-v0.2.1-alpha.2](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.1-alpha.2)

- **G** 新增实验性思考过程机器翻译插件，可在插件页启用，选择 Bing、Google 或付费 DeepSeek Flash。  [movo 代码](../../apps/user-web/src/components)
- **P** 新增实验性 Git Worktrees 插件，可在插件页启用，由 Agent 创建并进入独立的 Git checkout。  [movo 代码](../../apps/user-web/src/components/code/WorkspaceChanges.vue)
- **V** 新增实验性插件的 Session 状态记录接口，供插件写入和读取自己的会话记录。  需运行或界面验收
- **V** 全局指令支持读取共享 agents 目录中的 AGENTS.md，可通过 DSH_AGENTS_HOME 指定目录。  需运行或界面验收
- **V** 新增 working_directory 工具，并为 TypeScript/Python SDK 提供会话工作目录的读取和切换接口。  需运行或界面验收
- **P** Official 插件列表新增 Claude Code 和 Codex 组合包的按需安装入口，发布版安装对应版本的包。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **V** 新增工作步骤收起时机设置，可选择回答结束后收起，或在下一条普通消息到来时收起。  需运行或界面验收
- **V** pi-ai 路由支持按模型能力处理会话中的系统提示词更新，以及工具的动态新增和移除。  需运行或界面验收
- **P** SSH 新增独立可执行的 helper 运行时，支持远端文件操作、进程、终端、沙箱和 Node PTC。  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)
- **P** 通用设置新增字体选项，可分别调整界面正文、代码与工具输出、侧栏终端的字体和字号。  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)
- **V** 语音输入新增麦克风选择，可在插件详情页选择输入设备，并查看所选设备的实时输入电平。  需运行或界面验收
- **V** Web 支持绑定指定的 IPv4/IPv6 地址，并通过 --tls-cert 和 --tls-key 配置原生 HTTPS 监听。  需运行或界面验收
- **P** Shell 和插件安装详情支持横向查看及复制完整命令；后台 Bash 调用可展开输入和启动回执。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **P** 优化含超长源码行的文件预览性能，超长行使用无高亮文本展示，普通行继续进行语法高亮。  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)
- **V** 优化自动会话标题生成，对同主题的追问、补充和继续请求保留已有合适标题。  需运行或界面验收
- **V** 允许远程主机访问的 Web 配置使用页面内目录选择器，不再在服务器上弹出原生目录对话框。  需运行或界面验收
- **P** 侧栏 Fork 和子代理目录浏览新增迁移提示，遇到需要迁移的会话时引导用户先打开原会话。  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)

## [dsh-v0.2.1-alpha.3](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.1-alpha.3)

- **V** Web 版支持在本机 HTTP 访问时登录 DeepSeek 账号。  需运行或界面验收
- **V** 支持识别已发送消息中的密钥和令牌，并默认脱敏按需查看。  需运行或界面验收
- **P** 极简模式支持读取图片和自动压缩长对话，Web 与桌面端可通过 /compact 指令手动压缩上下文。  [movo 代码](../../services/chat-api/app/services/session_persistence_service.py)
- **P** 改善会话列表加载和 @ 会话搜索体验  [movo 代码](../../apps/user-web/src/components/SessionSearchOverlay.vue)
- **V** 子智能体可通过配置选用独立 Agent Preset 预设，统一设置角色和工具；  需运行或界面验收
- **V** 优化侧栏展开规则，让运行中和等待回应的会话更容易找到；会话菜单支持复制会话 ID。  需运行或界面验收
- **V** DeepSeek 账号的模型列表随账号可用模型更新，并隐藏当前客户端版本不支持的模型。  需运行或界面验收
- **V** 模型设置更清楚地提示凭据来源和检测状态，支持按需显示输入的 API Key。  需运行或界面验收
- **V** Office 文档任务按需加载编辑、渲染和导出指引，减少简单内容修改中不必要的检查与预览。  需运行或界面验收
- **V** 改进子智能体的委派与等待指引：达到委派层数上限时提前提示，等待子任务期间不再消耗新的目标执行轮次。  需运行或界面验收
- **P** Web 终端更可靠地处理连续输入、粘贴和尺寸调整，并保留进程退出前的最后输出。  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)
- **P** 桌面端可用 Cmd/Ctrl + 加号或减号统一调整正文、代码和终端字号。  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)
- **P** 优化会话和工作区的悬停操作，统一卡片与菜单样式，并改善页头排列及插件页、自动化任务页的窄窗口布局。  [movo 代码](../../apps/user-web/src/components/scheduled-tasks/ScheduledTaskPage.vue)
- **V** PTC Mode 的 Node 执行环境新增可选的 in-memory 模式，多次运行代码可复用变量、函数和已导入模块。  需运行或界面验收

## [dsh-v0.2.1-alpha.4](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.1-alpha.4)

- **P** 自定义模型 API 支持通过UI中配置各模型的推理等级，无需手动修改配置文件。 by  [movo 代码](../../apps/user-web/src/components/chat/ComposerModelPicker.vue)
- **P** 允许用户从“自定义插件索引源”中发现和安装插件。 by  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)

## [dsh-v0.2.1-alpha.5](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.1-alpha.5)

- 本次官方说明没有“新增功能”或“体验优化”条目。

## [dsh-v0.2.1-rc.1](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.1-rc.1)

- **P** 允许用户从“自定义插件索引源”中发现和安装插件。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **P** 插件管理页新增「让 Agent 创建插件」入口，可保留草稿进入创造模式；发送需求后才开始执行。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **P** 支持插件启用、停用、卸载及更新后的依赖同步；启用热重载时，更新或重新安装的可替换插件直接生效，无法热重载时提示重启。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **P** 可选插件支持极简模式，Official 插件列表支持按需安装与当前发布版对应的 Claude Code 和 Codex 组合包，并可用于 headless、SDK 和 ACP profile。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **V** 新增实验性插件的 Session 状态记录接口，供插件写入和读取自己的会话记录。  需运行或界面验收
- **V** 新增实验性 Claude Code Mods 兼容层。目前阶段的主要目的是验证 Claude Code Mods API 功能大致为 DeepSeek Harness 插件的一个子集，而非为用户提供实际的完整兼容性。  需运行或界面验收
- **V** 新增实验性开发者工具组合包，提供会话原始日志、聊天分组与正文的双向定位，以及内嵌 NodeJS 调试工具；内嵌 DevTools 目前使用英文界面。  需运行或界面验收
- **G** 新增实验性思考过程机器翻译插件，可在插件页启用，选择 Bing、Google 或付费 DeepSeek Flash。  [movo 代码](../../apps/user-web/src/components)
- **P** 新增实验性 Git Worktrees 插件，可在插件页启用，由 Agent 创建并进入独立的 Git checkout。  [movo 代码](../../apps/user-web/src/components/code/WorkspaceChanges.vue)
- **P** 自定义模型 API 支持通过UI中配置各模型的推理等级，无需手动修改配置文件。  [movo 代码](../../apps/user-web/src/components/chat/ComposerModelPicker.vue)
- **V** pi-ai 路由支持按模型能力处理会话中的系统提示词更新，以及工具的动态新增和移除。  需运行或界面验收
- **P** 极简模式支持读取图片和自动压缩长对话，Web 与桌面端可通过 /compact 指令手动压缩上下文。  [movo 代码](../../services/chat-api/app/services/session_persistence_service.py)
- **V** 全局指令支持读取共享 agents 目录中的 AGENTS.md，可通过 DSH_AGENTS_HOME 指定目录。  需运行或界面验收
- **V** 新增 working_directory 工具，并为 TypeScript/Python SDK 提供会话工作目录的读取和切换接口。  需运行或界面验收
- **P** SSH 新增独立可执行的 helper 运行时，支持远端文件操作、进程、终端、沙箱和 Node PTC。  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)
- **V** Web 版支持在本机 HTTP 访问时登录 DeepSeek 账号。  需运行或界面验收
- **V** 支持识别已发送消息中的密钥和令牌，并默认脱敏按需查看。  需运行或界面验收
- **V** 新会话支持预填未发送的提示；恢复草稿或切换工作区时保留文件、目录和会话引用。  需运行或界面验收
- **V** 新增工作步骤收起时机设置，可选择回答结束后收起，或在下一条普通消息到来时收起。  需运行或界面验收
- **P** Markdown 文件预览将 YAML 头部元数据显示为清晰的字段列表。  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)
- **P** 改善自动化任务详情在窄窗口中的布局，关联会话入口会按可用空间收起为图标。  [movo 代码](../../apps/user-web/src/components/scheduled-tasks/ScheduledTaskPage.vue)
- **V** 子智能体可通过配置选用独立 Agent Preset 预设，统一设置角色和工具；  需运行或界面验收
- **V** 改进子智能体的委派与等待指引：达到委派层数上限时提前提示，等待子任务期间不再消耗新的目标执行轮次。  需运行或界面验收
- **V** 组合包详情页显示代码来源和当前版本，便于查看安装来源及重装所需的信息。  需运行或界面验收
- **P** 插件安装结果显示实际安装版本；因新版本冷却策略安装较旧版本时，提供说明和精确版本安装方式。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **V** 工具调用在准备阶段即可显示已到达的命令说明、文件路径和内容生成进度。  需运行或界面验收
- **P** Shell 和插件安装详情支持横向查看及复制完整命令；后台 Bash 调用可展开输入和启动回执。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **P** Web 终端更可靠地处理连续输入、粘贴和尺寸调整，并保留进程退出前的最后输出。  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)
- **V** PTC Mode 的 Node 执行环境新增可选的 in-memory 模式，多次运行代码可复用变量、函数和已导入模块。  需运行或界面验收
- **P** 改善大量会话的列表加载与 @ 会话搜索体验。  [movo 代码](../../apps/user-web/src/components/SessionSearchOverlay.vue)
- **V** 优化自动会话标题生成，对同主题的追问、补充和继续请求保留已有合适标题。  需运行或界面验收
- **P** 侧栏 Fork 和子代理目录浏览新增迁移提示，遇到需要迁移的会话时引导用户先打开原会话。  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **V** 优化侧栏展开规则，让运行中和等待回应的会话更容易找到；会话菜单支持复制会话 ID。  需运行或界面验收
- **P** 支持分别设置界面正文、代码与工具输出、侧栏终端的字体和字号；桌面端可通过 Cmd/Ctrl + 加号或减号统一调整字号。  [movo 代码](../../apps/user-web/src/components/code/ProjectTerminal.vue)
- **P** 优化会话和工作区的悬停操作，统一卡片与菜单样式，并改善页头排列及插件页、自动化任务页的窄窗口布局。  [movo 代码](../../apps/user-web/src/components/scheduled-tasks/ScheduledTaskPage.vue)
- **V** 语音输入新增麦克风选择，可在插件详情页选择输入设备，并查看所选设备的实时输入电平。  需运行或界面验收
- **V** 允许远程主机访问的 Web 配置使用页面内目录选择器，不再在服务器上弹出原生目录对话框。  需运行或界面验收
- **P** 优化含超长源码行的文件预览性能，超长行使用无高亮文本展示，普通行继续进行语法高亮。  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)
- **V** Office 文档任务按需加载编辑、渲染和导出指引，减少简单修改及 PDF 导出后的无关检查与预览，并避免在回复中引用已删除的预览图。  需运行或界面验收
- **V** DeepSeek 账号的模型列表随账号可用模型更新，并隐藏当前客户端版本不支持的模型。  需运行或界面验收
- **V** 模型设置更清楚地提示凭据来源和检测状态，支持按需显示输入的 API Key。  需运行或界面验收

## [dsh-v0.2.1-rc.2](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.1-rc.2)

- **V** 适配 DeepSeek-V4.1-Flash-1017 上线  需运行或界面验收
- **V** 适配 DeepSeek Search 与 Fetch API，可在网页搜索设置中开启  需运行或界面验收

## [dsh-v0.2.1-rc.3](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.1-rc.3)

- **V** 新增左侧栏、会话视图和右侧栏的「更多」菜单，方便浏览和创建插件。  需运行或界面验收
- **V** 修复切换会话后，点击「新会话」找不回未发送草稿的问题。  需运行或界面验收

## [dsh-v0.2.1-rc.4](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.1-rc.4)

- 本次官方说明没有“新增功能”或“体验优化”条目。

## [dsh-v0.2.1-rc.5](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.1-rc.5)

- **V** 优化对话中思考内容的展示效果。  需运行或界面验收

## [dsh-v0.2.2-alpha.2](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.2-alpha.2)

- **P** 插件管理页支持展示富文本详情，并改善页面布局和导航行为。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **P** 插件管理支持更新第三方插件包；热更新失败时会尝试恢复旧版本。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **G** 支持将聊天文本作为引用插入输入框，并在发送后显示紧凑预览。  [movo 代码](../../apps/user-web/src/components)
- **G** 支持将完整历史交会话复制为 Markdown，包含可用的原始日志路径。  [movo 代码](../../apps/user-web/src/components)
- **V** 工作步骤收起后保留全部助手文字回复，可切换为仅最终回答。  需运行或界面验收
- **G** 新增日语、西班牙语、法语、德语、俄语和巴西葡萄牙语文案与界面配置。  [movo 代码](../../apps/user-web/src/components)
- **P** 自动化任务页支持确认后一次清除全部已结束任务，保留进行中的任务。  [movo 代码](../../apps/user-web/src/components/scheduled-tasks/ScheduledTaskPage.vue)
- **V** 新增实验性「`subagent_oar`工具」插件，可将独立任务交给本机 Codex 或 Claude CLI  需运行或界面验收
- **P** 新增实验性「个性化推荐」插件，按需在回答下方提供官方插件启用卡片或个性化页面创建卡片。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **G** 新增实验性「开发者工具 - 统计」插件，按轮次和步骤查看上下文、缓存、模型与工具耗时等统计。  [movo 代码](../../apps/user-web/src/components)
- **P** 新增实验性「变更请求与工作树」：可在独立 Git 工作树中运行会话，查看关联 PR 的状态和代码差异。  [movo 代码](../../apps/user-web/src/components/code/WorkspaceChanges.vue)
- **V** 改善手机和平板输入：减少自动弹出软键盘，发送后收起键盘，修正键盘平移页面时的光标滚动。  需运行或界面验收
- **V** 窄屏浏览器设置页采用全屏与横向导航，聚焦项自动完整滚入可见区；触屏任务文本输入使用 16px 字号。  需运行或界面验收
- **V** 触屏动作不再被悬停提示阻挡，工作区与归档结果操作直接可达；宽 Markdown 表格在局部容器中滚动。  需运行或界面验收
- **V** 窄会话栏中，溢出的头部状态入口会渐隐，避免遮挡“在应用中打开”等工具按钮。  需运行或界面验收
- **P** 恢复窄窗口下输入框模型选择器自动折叠为图标的行为，完整模型名仍可在菜单中查看。  [movo 代码](../../apps/user-web/src/components/chat/ComposerModelPicker.vue)
- **V** 修复手机及窄窗口下字体设置输入框挤压标题和说明的问题，字体输入行改为纵向排列，字号控件保留右对齐。  需运行或界面验收
- **V** 同名工作区在选择器中显示最短区分路径后缀，窄屏优先保留后缀。  需运行或界面验收
- **V** 共享描边按钮使用按 DPR 调整的内描边，改善 Safari 分数尺寸下的细线显示且不改变布局。  需运行或界面验收
- **V** 运行状态位于当前工作轮次尾部、待处理插话之前，方便区分运行中和排队中的消息，并改善界面布局抖动问题  需运行或界面验收
- **V** 会话列表支持插件图标，并改善键盘与触屏操作。  需运行或界面验收
- **V** 侧栏会话悬浮卡显示工作目录，便于区分未分组或同名会话。  需运行或界面验收
- **V** 优化侧栏空间布局，改善响应区域，平滑搜索框展开与收起。  需运行或界面验收
- **P** 侧栏搜索支持不区分大小写的会话 ID 子串匹配。  [movo 代码](../../apps/user-web/src/components/SessionSearchOverlay.vue)
- **V** 消息在宿主确认接收后才显示并清空草稿；发送期间输入框只读，发送失败时保留草稿、引用和附件。  需运行或界面验收
- **P** 图片上传方式调整为进入输入框后立即上传，发送消息时复用已上传的图片。默认单张图片上限提高到 50 MiB。  [movo 代码](../../apps/user-web/src/components/chat/ChatComposer.vue)
- **V** 已回答的问题批次以消息气泡显示，原生与 PTC 调用的回答在过程折叠后仍可回看。  需运行或界面验收
- **V** 悬浮侧栏面板拖过屏幕边缘时有阻力，松手后弹回可见区域；窗口缩小时保持控件可达。  需运行或界面验收
- **V** 支持中键关闭右侧栏标签，关闭后台标签不改变当前选中项，并保留不可关闭的起始页。  需运行或界面验收
- **V** 修复工作步骤展开和收起时的正文跳动、滚动回跳与空白间隙，保持运行状态可见。  需运行或界面验收
- **V** 点击聊天中的文件行号链接后，代码和文本预览以短暂高亮标出目标行并淡出。  需运行或界面验收
- **V** Trajectory 结果页新增实时工具返回值的原始 JSON 查看，并与渲染结果上下展示  需运行或界面验收
- **V** Search 功能优先向模型提供 Search API 长摘要，默认每来源最多 800 字符；搜索卡片仍展示短摘录。  需运行或界面验收
- **P** 模型选择器默认勾选已配置模型，可一次添加或移除候选并保留自定义值；筛选后的全选只作用于可见候选。  [movo 代码](../../apps/user-web/src/components/chat/ComposerModelPicker.vue)
- **P** 对通过 pi-ai 接入且不支持在对话中追加系统消息的模型，后续系统消息会在原位置作为提醒提供，不会移到最初的提示词中。  [movo 代码](../../apps/user-web/src/components/scheduled-tasks/ScheduledTaskPage.vue)
- **V** 支持在 DeepSeek 与 pi-ai 提供商内拖动或用方向键排序模型，保存后保留顺序及完整模型参数。  需运行或界面验收
- **V** 输入框统计读数被截断时，可通过提示气泡查看完整数值；会话统计也显示轮次与步骤数。  需运行或界面验收
- **V** Auto 自动审核支持在连续工具调用之间更好地复用历史上下文缓存，减少重复处理。  需运行或界面验收
- **P** 后台任务完成通知直接携带小体积输出，并减少已读取结果和子代理收尾消息的重复通知。  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **P** 子代理等待指引减少 sleep 和重复轮询：只有结果尚未返回时，结束当前轮次等待完成通知。  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **V** 远程连接默认启用 WebSocket 压缩，减少大量历史消息的传输量；可通过 `websocketCompression` 关闭。  需运行或界面验收
- **V** Web 静态资源支持 ETag 条件请求，未变化的资源返回 304，减少重复下载。  需运行或界面验收
- **V** Word 常规编辑在保存并核对内容与格式后即可交付，减少不必要的 ZIP、XML 与元数据检查。  需运行或界面验收
- **V** 加快 Web 预览中源码编辑器等懒加载组件的首次打开。  需运行或界面验收
- **V** 加快带固定目录前缀的文件查找，跳过无关目录，同时保持结果与排序规则不变。  需运行或界面验收
- **V** 支持拖动平移超出视口的图片，并通过应用内拖放或桌面原生拖放交付原始文件。  需运行或界面验收
- **V** 手机和平板打开宿主文件后会提示操作已在其它设备执行；各端失败时显示错误提示，电脑端成功保持静默。  需运行或界面验收

## [dsh-v0.2.2-alpha.3](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.2-alpha.3)

- **G** 支持统一右键与键盘菜单，覆盖会话、工作区和侧边栏，并支持开发者扩展  [movo 代码](../../apps/user-web/src/components)
- **P** 文件预览支持常驻目录树和文件定位功能。  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)
- **P** 实验性「变更请求与工作树」统一代码审查与工作树入口，支持通过可搜索文件树和逐文件导航查看本地及 PR 差异，将选中代码和评论交给 Agent，并跟踪检查与评审状态。  [movo 代码](../../apps/user-web/src/components/code/WorkspaceChanges.vue)
- **P** 改善手机端侧栏导航与窄屏布局，保持会话标题稳定，并让模型目录输入和插件发现页操作完整可见。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **V** 菜单和浮窗优先保持在可见区域内，跟随浏览器缩放、平移和软键盘变化。  需运行或界面验收
- **V** Trajectory 支持独立折叠子调用，保留父调用和摘要；搜索或跨视图定位时可展开对应子调用。  需运行或界面验收
- **V** 优化对话中思考内容的展示，摘要、展开正文和翻译不再显示模型输出开头的签名前缀。  需运行或界面验收
- **V** 减少会话状态更新时的重复发布和目录处理开销，并降低长回复流式组装的运行时成本。  需运行或界面验收
- **V** 改善底部输入框的布局稳定性，减少输入、菜单展开和统计更新时的跳动。  需运行或界面验收

## [dsh-v0.2.2-rc.1](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.2-rc.1)

- **V** 完善手机和平板适配，优化软键盘交互、导航与窄屏布局，保持菜单和操作入口可用。  需运行或界面验收
- **G** 支持将聊天文本作为引用插入输入框，并在发送后显示紧凑预览。  [movo 代码](../../apps/user-web/src/components)
- **G** 支持将完整历史会话复制为 Markdown，包含可用的原始日志路径。  [movo 代码](../../apps/user-web/src/components)
- **V** 工作步骤收起后保留全部助手文字回复，可切换为仅最终回答。  需运行或界面验收
- **G** 支持统一右键与键盘菜单，覆盖会话、工作区和侧边栏，并支持开发者扩展。  [movo 代码](../../apps/user-web/src/components)
- **P** 文件预览支持常驻目录树和文件定位功能。  [movo 代码](../../apps/user-web/src/components/chat/AssistantMessageBody.vue)
- **G** 新增日语、西班牙语、法语、德语、俄语和巴西葡萄牙语文案与界面配置。  [movo 代码](../../apps/user-web/src/components)
- **P** 插件管理页支持展示富文本详情，并改善页面布局和导航行为。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **P** 插件管理支持更新第三方插件包；热更新失败时会尝试恢复旧版本。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **V** 新增实验性「`subagent_oar`工具」插件，可将独立任务交给本机 Codex 或 Claude CLI。  需运行或界面验收
- **P** 新增实验性「个性化推荐」插件，按需在回答下方提供官方插件启用卡片或个性化页面创建卡片。  [movo 代码](../../apps/user-web/src/components/MyPluginsPage.vue)
- **G** 新增实验性「开发者工具 - 统计」插件，按轮次和步骤查看上下文、缓存、模型与工具耗时等统计。  [movo 代码](../../apps/user-web/src/components)
- **P** 新增实验性「变更请求与工作树」：在独立 Git 工作树中运行会话，通过可搜索文件树和逐文件导航查看本地及 PR 差异，将选中代码和评论交给 Agent，并跟踪检查与评审状态。  [movo 代码](../../apps/user-web/src/components/code/WorkspaceChanges.vue)
- **V** 同名工作区在选择器中显示最短区分路径后缀，窄屏优先保留后缀。  需运行或界面验收
- **V** 会话列表支持插件图标，并改善键盘与触屏操作。  需运行或界面验收
- **V** 侧栏会话悬浮卡显示工作目录，便于区分未分组或同名会话。  需运行或界面验收
- **V** 优化侧栏空间布局，改善响应区域，平滑搜索框展开与收起。  需运行或界面验收
- **P** 侧栏搜索支持不区分大小写的会话 ID 子串匹配。  [movo 代码](../../apps/user-web/src/components/SessionSearchOverlay.vue)
- **V** 悬浮侧栏面板拖过屏幕边缘时有阻力，松手后弹回可见区域；窗口缩小时保持控件可达。  需运行或界面验收
- **V** 支持中键关闭右侧栏标签，关闭后台标签不改变当前选中项，并保留不可关闭的起始页。  需运行或界面验收
- **V** 消息在宿主确认接收后才显示并清空草稿；发送期间输入框只读，发送失败时保留草稿、引用和附件。  需运行或界面验收
- **P** 图片上传方式调整为进入输入框后立即上传，发送消息时复用已上传的图片。默认单张图片上限提高到 50 MiB。  [movo 代码](../../apps/user-web/src/components/chat/ChatComposer.vue)
- **V** 已回答的问题批次以消息气泡显示，原生与 PTC 调用的回答在过程折叠后仍可回看。  需运行或界面验收
- **V** 运行状态位于当前工作轮次尾部、待处理插话之前，方便区分运行中和排队中的消息，并改善界面布局抖动问题。  需运行或界面验收
- **V** 改善工作步骤展开／收起和底部输入框的布局稳定性，减少正文、滚动与输入交互时的跳动，并保持运行状态可见。  需运行或界面验收
- **V** 输入框统计读数被截断时，可通过提示气泡查看完整数值；会话统计也显示轮次与步骤数。  需运行或界面验收
- **V** 点击聊天中的文件行号链接后，代码和文本预览以短暂高亮标出目标行并淡出。  需运行或界面验收
- **V** 支持拖动平移超出视口的图片，并通过应用内拖放或桌面原生拖放交付原始文件。  需运行或界面验收
- **V** Trajectory 结果页新增实时工具返回值的原始 JSON 查看，并与渲染结果上下展示。  需运行或界面验收
- **V** Trajectory 支持独立折叠子调用，保留父调用和摘要；搜索或跨视图定位时可展开对应子调用。  需运行或界面验收
- **P** 模型选择器默认勾选已配置模型，可一次添加或移除候选并保留自定义值；筛选后的全选只作用于可见候选。  [movo 代码](../../apps/user-web/src/components/chat/ComposerModelPicker.vue)
- **P** 对通过 pi-ai 接入且不支持在对话中追加系统消息的模型，后续系统消息会在原位置作为提醒提供，不会移到最初的提示词中。  [movo 代码](../../apps/user-web/src/components/scheduled-tasks/ScheduledTaskPage.vue)
- **V** 支持在 DeepSeek 与 pi-ai 提供商内拖动或用方向键排序模型，保存后保留顺序及完整模型参数。  需运行或界面验收
- **P** 自动化任务页支持确认后一次清除全部已结束任务，保留进行中的任务。  [movo 代码](../../apps/user-web/src/components/scheduled-tasks/ScheduledTaskPage.vue)
- **V** Search 功能优先向模型提供 Search API 长摘要，默认每来源最多 800 字符；搜索卡片仍展示短摘录。  需运行或界面验收
- **V** Auto 自动审核支持在连续工具调用之间更好地复用历史上下文缓存，减少重复处理。  需运行或界面验收
- **P** 后台任务完成通知直接携带小体积输出，并减少已读取结果和子代理收尾消息的重复通知。  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **P** 子代理等待指引减少 sleep 和重复轮询：只有结果尚未返回时，结束当前轮次等待完成通知。  [movo 代码](../../services/chat-api/dsh/compatibility-matrix.yaml)
- **V** 加快带固定目录前缀的文件查找，跳过无关目录，同时保持结果与排序规则不变。  需运行或界面验收
- **V** Word 常规编辑在保存并核对内容与格式后即可交付，减少不必要的 ZIP、XML 与元数据检查。  需运行或界面验收
- **V** 远程连接默认启用 WebSocket 压缩，减少大量历史消息的传输量；可通过 `websocketCompression` 关闭。  需运行或界面验收
- **V** Web 静态资源支持 ETag 条件请求，未变化的资源返回 304，减少重复下载。  需运行或界面验收
- **V** 减少会话状态更新时的重复发布和目录处理开销，并降低长回复流式组装的运行时成本。  需运行或界面验收
- **V** 改善 macOS Computer Use 的系统与应用权限引导，通过独立应用申请系统权限，提供系统设置与应用拖入引导并在返回后刷新状态；支持长按、改善应用启动，应用授权可跨重启保留。  需运行或界面验收
