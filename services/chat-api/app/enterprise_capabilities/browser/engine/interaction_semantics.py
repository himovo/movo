"""Small, shared lexical guards for deterministic browser policies."""

from __future__ import annotations

import re
from typing import Any


_CJK_MUTATION_LABEL = re.compile(
    r"发布|发送|提交|保存|删除|移除|支付|付款|购买|下单|批准|通过|拒绝",
)
_LATIN_MUTATION_LABEL = re.compile(
    r"\b(?:publish|post|send|submit|save|delete|remove|pay|purchase|buy|approve|accept|reject)\b",
    re.I,
)


def is_mutation_label(value: Any) -> bool:
    """Whether a control label plausibly performs an externally visible write."""

    label = str(value or "").strip()
    return bool(_CJK_MUTATION_LABEL.search(label) or _LATIN_MUTATION_LABEL.search(label))


__all__ = ["is_mutation_label"]
