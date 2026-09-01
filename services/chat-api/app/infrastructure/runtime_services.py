"""Process-wide infrastructure used by both the DSH gateway and HTTP APIs.

This module deliberately contains no Planner, Graph, Agent, Skill runtime, or
legacy fallback.  It is the composition root for cross-cutting infrastructure
that remains owned by ASKAI after the old execution engine is retired.
"""

from app.core.config import get_settings
from app.enterprise_capabilities.browser.engine.env_manager import EnvManager
from app.governance.action_receipt_store import ActionReceiptStore
from app.infrastructure.observability.kpi_store import RuntimeKPIStore
from app.token_usage import TokenUsageDispatcher


action_receipt_store = ActionReceiptStore()
env_manager = EnvManager()
runtime_kpi_store = RuntimeKPIStore()
token_usage_dispatcher = TokenUsageDispatcher(
    queue_size=int(get_settings().TOKEN_USAGE_QUEUE_SIZE or 512)
)
