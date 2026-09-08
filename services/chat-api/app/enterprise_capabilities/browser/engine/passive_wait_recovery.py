"""Bound condition-free waiting using the existing execution history."""
from .agent_loop.protocol import Decision, Observation


def recover_passive_wait(decision: Decision, observation: Observation, history: list) -> Decision:
    if decision.tool != "browser_wait_for" or (decision.args or {}).get("text"):
        return decision
    count = 0
    for record in reversed(history):
        if record.observation.url != observation.url:
            break
        tool = record.decision.tool
        if tool == "browser_wait_for":
            count += 1
        elif tool not in {"browser_observe", "browser_read_text", "browser_screenshot"}:
            break
    if count < 2:
        return decision
    return Decision(
        "browser_observe", {"with_screenshot": True},
        "连续等待未推进任务，改为读取当前状态。局部加载提示不等于整页不可用；"
        "请使用已经可操作的控件、滚动到目标区域或处理已观察到的覆盖层，"
        "不要再次无条件等待。若确实无法推进，说明具体阻碍。",
    )
