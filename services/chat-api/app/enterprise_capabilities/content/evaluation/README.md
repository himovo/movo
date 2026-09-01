# content_evaluation —— 动态标准评估与修复闭环

> **唯一**的内容评估管道。旧的 `TaskSatisfactionEvaluator` + `TaskRepairPlanner` 已删除，无 feature flag。

## 为什么有这个模块

旧 `task_satisfaction` 的评估器有几个根本问题：

- 7 个子分（goal_fit / audience_fit / schema_fit ...）大半是启发式常数（看长度、看段落数、看标题字符串匹配），不依赖实际内容质量
- `acceptance_score` 有硬上限 cap=0.69，修复永远突破不了
- `_stabilize_repaired_report` 在重评分数低时虚增分数，让"修复后分数提升"成了表演
- 旧的上下文盲修复器完全脱离写作时的上下文（publish channel / profile preset / user skills / compose policy），等于让一个不知情的"二次编辑"重写本来已经按规范生成的内容

新模块只做三件事，故意保持简单：

1. **生成评判标准**（`StandardsGenerator`）—— 只看用户请求，不看产物，避免按产物造标准
2. **找问题**（`IssueFinder`）—— 用标准当 rubric 检查产物，列具体问题
3. **触发修复**（不在本模块内做修复）—— 把 issue 列表交给上游 writer engine 重写，writer 保留所有原始上下文

**修复在 writer engine 内部做**，不在本模块。

## 核心数据结构（contracts.py）

```python
Standard:    id, severity (critical/major/minor), description, anti_example
Issue:       standard_id, severity, location, finding, fix_suggestion
EvaluationResult: standards, issues, verdict, repaired_content, metadata

Verdict 推导规则（derive_verdict）:
  has critical → "needs_rewrite"
  has major    → "needs_repair"
  其他        → "pass"
```

**没有数字分数**。verdict 直接由 issue 严重度决定，不算加权和、不算 acceptance_score。

## 模块文件

| 文件 | 职责 | 行数 |
|------|------|------|
| `contracts.py` | Pydantic 数据结构 + verdict 推导 | ~60 |
| `standards_generator.py` | LLM 调用 1：用户请求 → 5-8 条可验证标准 | ~140 |
| `issue_finder.py` | LLM 调用 2：内容 + 标准 → 问题列表 | ~150 |
| `pipeline.py` | 串联 standards + issue 查找的入口 | ~90 |
| `legacy_adapter.py` | 把 EvaluationResult 适配成旧 `TaskSatisfactionReport` / `TaskRepairPlan`，给下游兼容 | ~150 |
| `__init__.py` | 公共 export | ~50 |

每个文件单一职责、不超过 150 行。修复由 writer engine 在原始上下文中重写完成。

## 评估闭环覆盖表

| 用户输入 | execution_kind | writer 入口 | 章节级 eval+regen | 文档级 dynamic eval | 文档级 retry | 整体闭环 |
|---------|----------------|------------|------------------|---------------------|------------|---------|
| **长报告 / 长分析** | content / mixed | `generate` (sectional) | ✓ 每章 1 次 regen | ✓ | ❌ gate 拦截 | 章节级修，跨章节按设计跳过 |
| **长文章一次性** | content / mixed | `generate_direct` | ❌ 单次写 | ✓ | ✓ verdict≠pass 触发整篇 retry | 整篇 1 次 retry |
| 中等文章 | content / mixed | `generate_direct` 或 `generate` | 走 generate 时 ✓，走 direct 时 ❌ | ✓ | ✓（仅 direct）/ ❌（sectional） | 看 mode |
| 短内容 | chat | DSH 直接生成 | ❌ | ❌ | ❌ | 不进入 MOVO 写作引擎 |
| 翻译 | content | — | `generate_translation` | ❌ | ❌ | ❌ | 不评估，原样输出 |
| 演示文稿（PPT） | presentation | — | — | ❌ | ❌ 早期短路 | ❌ | 不评估 |
| 浏览器自动化 | browser | — | — | ❌ | ❌ 早期短路 | ❌ | 不评估，仅 execution_retry 失败重试 |
| 代码任务 | coding | — | — | ❌ | ❌ | ❌ | 不评估，仅失败重试 |
| 文件转换/导出 | file_transform | — | — | ❌ | ✓ 简化版 `_build_file_transform_report` | ❌ | 仅检查导出成功 |
| 聊天对话 | chat | — | — | ❌ | ❌ | ❌ | 不评估 |

## 决定走或不走的 5 个关键点

1. **execution_kind 早期 gate**（`task_satisfaction_eval.process()` 第 41-77 行）：`presentation / browser / pptx output requested` → 直接 short-circuit 整个 task_satisfaction_eval

2. **writer_path gate**：direct 属于 `single_shot`，因此仍会进文档级 dynamic eval；sectional 在 writer 内做章节级修复，文档级 eval 只评估不整篇 retry。

3. **dynamic eval 触发条件**（`task_satisfaction_eval.py` 第 290-325 行）：
   - `kind ∈ {content, mixed}` 或 `intent == "generation"`

4. **章节级 eval 触发条件**（`writer_engine/pipeline.py` 的 `generate()` 方法 sectional loop 内）：
   - 进入 sectional 路径（mode = `sectional_compose`）
   - 每章写完后调一次 `IssueFinder.find(scope="section")`
   - 命中 critical/major 则**重写一次**该章节
   - 重写时 `objective` 字段 prepend `[修订指引]` + 该章 issue 列表

5. **文档级 retry gate**（`task_satisfaction_eval.py` 中 `_writer_path` 检查）：
   - 仅在 `output_spec["__writer_path"] == "single_shot"` 时放行
   - sectional 路径已经在写作时 in-loop 修过，不再 retry
   - retry 走现有 `_retry_after_finalize`，把 issue 反馈写到 `output_spec["__doc_level_eval_feedback"]`，writer 重新跑时 `_amend_with_doc_feedback()` 帮手把它 prepend 到 user_query
   - `task_repair_retry_round` 计数器防止死循环（最多 1 次 retry）

## 设计哲学

- **短内容** → DSH 直接生成，不进入写作引擎
- **direct 单次长文** → 没有 in-loop repair 机制 → doc-level retry 是唯一闭环
- **sectional 超长文** → in-loop per-section repair 已经处理 80% → doc-level retry 重复劳动且贵 → 跳过
- **PPT/浏览器/代码** → 评估器是为内容写作设计的，对这些类型不适用 → 各自有 execution_retry
- **翻译** → 翻译质量评估有专门方法（不属于 standards-driven 范畴）→ 跳过

## 实际三种典型场景

| 用户场景 | 实际行为 |
|---------|---------|
| "写份简历" | DSH 直接生成，不调用 MOVO 写作引擎 |
| "写一篇 800 字小红书种草文" | DSH 直接生成，不调用 MOVO 写作引擎 |
| "写一份 3000 字市场分析报告" | direct → 文档级 dynamic eval → 必要时整篇重写 |

## 关键约束（避免重蹈旧评估器覆辙）

1. **standards 必须可验证**：prompt 里强制要求"一句话能 pass/fail 判定"，禁止生成"内容应清晰"这种主观标准
2. **standards 不能基于 trace/tool output 造事实**：prompt 里明确反例（`Completed research_collection_skill...` 这种内部状态字符串不能作为事实标准）
3. **issue_finder 区分 scope**：
   - `scope="document"`：评全文，所有标准都用
   - `scope="section"`：评单章，**跳过**只有全文才能验证的标准（总字数 / 全文必须包含 X / 开头结尾结构 / 跨章节连贯）
4. **修复必须保留写作上下文**：不脱离 publish_channel / profile_preset / formatting_rules / user_skills 重写。修复 = "writer 再写一次，看着上次的 issue 写"，不是"独立编辑器擦屁股"
5. **失败默认放行**：LLM 调用失败时 `verdict = "pass"`、跳过修复，**不卡死流程**。旧评估器的"挂掉默认要修"是循环灾难的根源
6. **没有数字分数算计**：verdict 由 severity 直接推，没有加权、没有 cap、没有 stabilize 虚增

## 涉及修改的文件清单

新增：
- `backend/app/runtime/content_evaluation/`（本目录全部 6 个文件）

修改：
- `backend/app/orchestration/stages/task_satisfaction_eval.py`：加 dynamic eval 分支 + 文档级 retry trigger + writer_path gate
- `backend/app/skillsystem/skills/writer_engine/pipeline.py`：加 `_amend_with_doc_feedback()` + 4 个 generate 方法入口注入 + sectional 章节级 eval+regen
- `backend/app/skillsystem/skills/tool_writer_engine_compose.py`：把 `output_spec["__doc_level_eval_feedback"]` 镜像到 `strategy["doc_level_feedback"]`；记录 `output_spec["__writer_path"]` 用于 gate 判断

删除：
- `backend/app/runtime/task_satisfaction/evaluator.py`（旧 `TaskSatisfactionEvaluator`，1210 行启发式打分）
- `backend/app/runtime/task_repair/planner.py`（旧 `TaskRepairPlanner`，已废弃）

保留（仅数据契约 + 工具用途）：
- `backend/app/runtime/task_satisfaction/contracts.py`（`TaskSatisfactionReport` 数据形状，仍是下游 `output_spec["task_satisfaction_report"]` 的契约 — `legacy_adapter.py` 把新评估结果套成这个 shape 给前端用）
- `backend/app/runtime/task_satisfaction/validation_patterns.py`（保留通用验证模式）
- `backend/app/runtime/task_repair/contracts.py`（`TaskRepairPlan` / `RepairStepSpec` 同上理由）

## 关键日志标识

定位评估闭环执行情况，搜以下字符串：

```
[content_evaluation][standards] generated count=N           # 标准生成
[content_evaluation][standards]   std_001 [critical] ...   # 标准内容
[content_evaluation][issues] found count=M                 # 找到的问题
[content_evaluation][issues]   std_xxx [major] @ ... — ... # 单条问题
[writer_engine][per_section_eval] standards ready count=N  # 章节级 eval 开始
[writer_engine][per_section_eval] section X/Y ... — regenerating once  # 单章触发 regen
[writer_engine][doc_feedback] applied len=N                # 文档级 feedback 进 prompt
[trace][...] dynamic_standards_evaluation | verdict=...    # 文档级评估完成
[trace][...] dynamic_eval_retry_applied | issues_addressed=N  # 文档级 retry 完成
```

## 后续可演进方向（按优先级）

1. **standards 缓存**：同一 user_id + 类似 user_request → 复用上次生成的 standards，节省一次 LLM 调用
2. **standards 用户编辑**：把生成的 standards 暴露给前端，让用户勾选/编辑后再评
3. **企业级标准库**：累积常用类型（简历/报告/邮件）的高质量 standards 模板，新请求优先匹配
4. **章节级 retry 上限调整**：当前每章最多重写 1 次；高质量场景可放到 2 次
5. **文档级 retry 也带 per-section 反馈回灌**：retry 时把章节级 issue 也注入，避免 retry 时章节级 eval 重新发现一遍

但**先观察真实流量 1-2 周再决定**——架构演进要靠数据，不是靠"觉得应该"。
