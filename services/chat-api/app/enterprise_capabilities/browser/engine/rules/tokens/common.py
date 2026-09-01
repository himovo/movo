"""Cross-operation verb vocabularies.

CONFIRM / CANCEL show up in dialogs everywhere (delete confirm, save
dialog, form submit, modal close). LOADING lets us detect "the page
is busy, don't click yet". These are locale-tolerant and cover the
Chinese enterprise stacks we care about.
"""

CONFIRM = (
    "confirm", "ok", "yes", "submit", "save", "primary",
    "确认", "确定", "保存", "提交", "是",
    "queren", "baocun",
)
CANCEL = (
    "cancel", "close",
    "取消", "关闭", "否", "no",
    "quxiao", "guanbi",
)
LOADING = (
    "loading", "pending", "busy",
    "加载中", "处理中",
    "jiazaizhong",
)
