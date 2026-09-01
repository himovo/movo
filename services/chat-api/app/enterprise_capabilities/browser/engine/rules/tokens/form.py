"""Form-specific vocabularies.

REQUIRED_MARKERS — tokens in a textbox name/description that signal
the field must be filled before submit. VALIDATION_ERROR — tokens that
appear on elements announcing a client-side validation failure.
SUCCESS_TOAST — tokens that appear in a post-submit notification.
"""

REQUIRED_MARKERS = (
    "*", "required", "必填", "必选",
    "bitian", "bixuan",
)
VALIDATION_ERROR = (
    "error", "invalid", "required", "failed",
    "错误", "无效", "必填", "不能为空", "格式不对", "失败",
    "cuowu", "wuxiao",
)
SUCCESS_TOAST = (
    "success", "saved", "submitted", "done",
    "成功", "已保存", "已提交", "操作成功",
    "chenggong",
)

# Actions that commit values from an already-active form. Keep this separate
# from dialog CONFIRM: publishing, sending and replying are form commits but
# are not necessarily confirmation-dialog controls.
COMMIT_ACTION = (
    "submit", "send", "publish", "post", "reply", "comment", "save",
    "confirm", "apply", "approve", "complete", "create", "update",
    "提交", "发送", "发布", "回复", "评论", "保存", "确认", "确定",
    "应用", "批准", "完成", "创建", "新建", "更新",
)

NON_COMMIT_ACTION = (
    "cancel", "close", "back", "next", "previous", "more", "preview",
    "取消", "关闭", "返回", "下一步", "下一张", "上一张", "更多", "预览",
)
