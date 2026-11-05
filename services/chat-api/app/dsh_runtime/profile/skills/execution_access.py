"""Check declared Skill workflow requirements against execution policy."""

from typing import Any

from app.enterprise_capabilities.runtime.workflow_mapping import workflow_capability_for_node
from app.product.execution_access import execution_is_allowed
from app.services.skill_packages.execution_requirements import package_uses_execution

from .workflow import workflow_nodes


def _package_uses_execution(row: dict[str, Any]) -> bool:
    if "package_requires_execution" in row:
        return bool(row["package_requires_execution"])
    return package_uses_execution(
        files=(item for item in row.get("package_files") or [] if isinstance(item, dict)),
        tools=(*(row.get("package_declared_tools") or []), *(row.get("package_referenced_tools") or [])),
        requires_environment=bool(row.get("package_requires_environment")),
    )


async def skill_execution_is_allowed(*, row: dict[str, Any], tenant_id: str, user_id: str) -> bool:
    if _package_uses_execution(row) and not await execution_is_allowed(
        main_id=tenant_id, user_id=user_id, capability="data.run_script@v1",
    ):
        return False
    for node in workflow_nodes(row):
        try:
            capability = workflow_capability_for_node(node).capability_ref
        except LookupError:
            continue
        if not await execution_is_allowed(main_id=tenant_id, user_id=user_id, capability=capability):
            return False
    return True
