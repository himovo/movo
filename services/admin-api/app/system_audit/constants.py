SYSTEM_AUDIT_COLLECTION = "system_audit_logs"

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

MODULE_LABELS = {
    "models": "模型中心",
    "skills": "Skill 管理",
    "tools": "工具与 MCP",
    "knowledge": "知识文档",
    "organizations": "账号组与账号",
    "directory": "组织与用户",
    "position-roles": "用户岗位角色",
    "traffic-allocations": "流量分配",
    "settings": "系统设置",
    "auth": "账号与登录",
    "setup": "系统初始化",
}

METHOD_ACTIONS = {
    "POST": "create_or_execute",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
}
