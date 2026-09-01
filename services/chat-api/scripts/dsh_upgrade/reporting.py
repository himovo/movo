from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import EvaluationReport


def _items(values: list[str]) -> str:
    return "、".join(f"`{value}`" for value in values) if values else "无"


def write_report(report: EvaluationReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"dsh-{report.baseline_version}-to-{report.candidate_version}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    payload = report.to_dict()
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    checks = "\n".join(
        f"| {item['name']} | {'通过' if item['passed'] else '失败'} | {item['duration_seconds']:.3f}s |"
        for item in payload["checks"]
    )
    dependencies = payload["dependency_delta"]
    capabilities = payload.get("capability_delta") or {}
    enabled_modules = capabilities.get("enabled_modules") or {"added": [], "removed": []}
    code_capabilities = capabilities.get("code_capability_tools") or {"added": [], "removed": []}
    api_removed = {
        name: delta["removed"] for name, delta in payload["public_api_delta"].items()
        if delta.get("removed")
    }
    markdown = f"""# DSH 候选升级评估

- 基线版本：`{report.baseline_version}`
- 候选版本：`{report.candidate_version}`
- 生成时间：`{report.generated_at_utc}`
- 候选结论：**{'通过契约评估' if payload['decision']['contract_ready'] else '未通过契约评估'}**
- 发布结论：**尚未接纳**（必须在升级分支完成全栈和打包验证）

## 自动检查

| 检查 | 结果 | 耗时 |
|---|---:|---:|
{checks}

## 官方包能力差异

- 新增顶层依赖：{_items(dependencies['added'])}
- 移除顶层依赖：{_items(dependencies['removed'])}
- 核心包被移除的公开 Export：{json.dumps(api_removed, ensure_ascii=False) if api_removed else '无'}
- 新增 Host 模块：{_items(enabled_modules['added'])}
- 移除 Host 模块：{_items(enabled_modules['removed'])}
- 新增 Code 工具：{_items(code_capabilities['added'])}
- 移除 Code 工具：{_items(code_capabilities['removed'])}
- 变更的普通会话模型工具契约：{_items(list(capabilities.get('ordinary_model_tool_contract_changes', {})))}
- 变更的 Code 模型工具契约：{_items(list(capabilities.get('code_model_tool_contract_changes', {})))}

## 旧会话恢复

- 基线创建：{'通过' if payload['old_session_resume'].get('created') else '失败'}
- 候选恢复：{'通过' if payload['old_session_resume'].get('resumed') else '失败'}

## 发布前仍须完成

""" + "\n".join(f"- {reason}" for reason in payload["decision"]["release_requirements"]) + "\n"
    markdown_path.write_text(markdown, encoding="utf-8")
    return json_path, markdown_path
