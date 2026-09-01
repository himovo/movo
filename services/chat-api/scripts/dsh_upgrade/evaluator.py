from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .checks import cross_version_session, inventory, verify_artifact, verify_installed_release_train
from .diffing import capability_delta, dependency_delta, public_api_delta
from .models import CommandResult, EvaluationReport
from .process import run_command
from .registry import NpmRegistry
from .workspace import CandidateWorkspace


CORE_API_PACKAGES = (
    "@deepseek-ai/dsh-agent",
    "@deepseek-ai/dsh-agent-loop",
    "@deepseek-ai/dsh-llm",
    "@deepseek-ai/dsh-scope",
    "@deepseek-ai/dsh-session",
    "@deepseek-ai/dsh-session-persistence-jsonl",
    "@deepseek-ai/dsh-tools",
    "@deepseek-ai/dsh-user-approval",
)


class DshCandidateEvaluator:
    def __init__(
        self,
        *,
        chat_api_root: Path,
        node: str,
        pnpm: str,
        npm: str = "npm",
        registry: NpmRegistry | None = None,
    ) -> None:
        self.chat_api_root = chat_api_root.resolve()
        self.host_root = self.chat_api_root / "dsh" / "runtime-host"
        self.node = node
        self.pnpm = pnpm
        self.npm = npm
        self.registry = registry or NpmRegistry(npm=npm)

    def evaluate(self, selector: str) -> EvaluationReport:
        host_package = json.loads((self.host_root / "package.json").read_text(encoding="utf-8"))
        baseline_version = str(host_package["dependencies"]["@deepseek-ai/dsh"])
        baseline_package = self.registry.resolve("@deepseek-ai/dsh", baseline_version)
        candidate_package = self.registry.resolve("@deepseek-ai/dsh", selector)
        checks: list[CommandResult] = []

        with CandidateWorkspace(self.host_root, candidate_package.version) as candidate_root:
            artifact_check, artifact_evidence = verify_artifact(candidate_root, candidate_package, self.npm)
            checks.append(artifact_check)
            checks.append(run_command(
                "candidate_install",
                [self.pnpm, "install", "--lockfile=false", "--ignore-scripts", "--registry=https://registry.npmjs.org"],
                cwd=candidate_root,
                timeout=300,
            ))
            if not checks[-1].passed:
                return self._failed_report(baseline_package, candidate_package, checks, "candidate install failed")
            release_train_check, installed_train = verify_installed_release_train(
                candidate_root, candidate_package.version,
            )
            checks.append(release_train_check)

            checks.extend([
                self._host_contract("baseline_host_contract", self.host_root),
                self._host_contract("candidate_host_contract", candidate_root),
            ])
            baseline_inventory_result, baseline_inventory = inventory("baseline_inventory", self.host_root, self.node)
            candidate_inventory_result, candidate_inventory = inventory("candidate_inventory", candidate_root, self.node)
            checks.extend([baseline_inventory_result, candidate_inventory_result])

            session_result = cross_version_session(self.host_root, candidate_root, self.node)
            checks.extend(session_result["checks"])
            api_delta = public_api_delta(self.host_root, candidate_root, list(CORE_API_PACKAGES))
            capabilities = (
                capability_delta(baseline_inventory, candidate_inventory)
                if baseline_inventory and candidate_inventory else {}
            )
            removed_api = any(item.get("removed") or item.get("missing") for item in api_delta.values())
            removed_capabilities = any(
                item.get("removed") for item in capabilities.values() if isinstance(item, dict)
            )
            changed_tool_contracts = any(
                value for key, value in capabilities.items() if key.endswith("_tool_contract_changes")
            )
            contract_ready = (
                all(check.passed for check in checks)
                and bool(capabilities)
                and session_result["created"]
                and session_result["resumed"]
                and not removed_api
                and not removed_capabilities
                and not changed_tool_contracts
            )
            return EvaluationReport(
                baseline_version=baseline_version,
                candidate_version=candidate_package.version,
                generated_at_utc=datetime.now(timezone.utc).isoformat(),
                package={
                    **self._package_evidence(candidate_package),
                    "artifact_verification": artifact_evidence,
                    "installed_release_train": installed_train,
                },
                dependency_delta=dependency_delta(
                    baseline_package.dependencies, candidate_package.dependencies,
                ),
                public_api_delta=api_delta,
                capability_delta=capabilities,
                checks=[check.to_dict() for check in checks],
                old_session_resume={
                    "created": session_result["created"],
                    "resumed": session_result["resumed"],
                    "baseline_session": session_result.get("baseline_session"),
                    "candidate_session": session_result.get("candidate_session"),
                },
                decision=self._decision(contract_ready),
            )

    def _host_contract(self, name: str, root: Path) -> CommandResult:
        tests = [str(path) for path in sorted((root / "tests").glob("*.test.mjs"))]
        return run_command(name, [self.node, "--test", *tests], cwd=root, timeout=180)

    @staticmethod
    def _package_evidence(package) -> dict[str, Any]:
        return {
            "name": package.name,
            "version": package.version,
            "tarball": package.dist.get("tarball"),
            "integrity": package.dist.get("integrity"),
            "shasum": package.dist.get("shasum"),
            "signatures": package.dist.get("signatures", []),
        }

    @staticmethod
    def _decision(contract_ready: bool, blocker: str | None = None) -> dict[str, Any]:
        requirements = [
            "在升级分支更新 versions.lock、兼容矩阵、完整性哈希、SBOM 和所有精确依赖",
            "运行 Backend 全量回归、桌面端/Web/管理后台测试",
            "生成桌面安装包并执行 packaged Runtime smoke",
            "人工验证聊天、工具/MCP、Skill、审批、Browser、Code 与 Artifact 核心路径",
            "保留上一稳定发布物，按整版本执行回滚演练",
        ]
        return {
            "contract_ready": contract_ready,
            "release_ready": False,
            "blocker": blocker,
            "release_requirements": requirements,
        }

    def _failed_report(self, baseline, candidate, checks, blocker: str) -> EvaluationReport:
        return EvaluationReport(
            baseline_version=baseline.version,
            candidate_version=candidate.version,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            package=self._package_evidence(candidate),
            dependency_delta=dependency_delta(baseline.dependencies, candidate.dependencies),
            checks=[check.to_dict() for check in checks],
            decision=self._decision(False, blocker),
        )
