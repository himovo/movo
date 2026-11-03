"""A per-compilation dependency snapshot; never cache across users or turns."""
from __future__ import annotations

import asyncio
import logging
from . import checks

logger = logging.getLogger(__name__)
CHECK_TIMEOUT_SECONDS = 1.5
DEPENDENCIES: dict[str, str] = {
    "knowledge.search@v1": "knowledge",
    "skills.install_skillhub@v1": "skillhub",
    "browser.task@v1": "browser",
    "image.generate@v1": "images",
    "vision.extract_facts@v1": "vision",
    "research.search_web@v1": "search",
    "research.progressive@v1": "search",
    "presentation.create@v1": "presentation",
    "data.run_script@v1": "scripts",
}

# These have bundled implementations or input-dependent local fallbacks. They
# require no separately configured provider. Argument admission remains in each handler.
LOCAL_CAPABILITIES = frozenset({
    "knowledge.browse@v1", "knowledge.read_document@v1",
    "document.review_source@v1", "document.annotate@v1", "document.parse@v1",
    "document.extract_resources@v1", "document.pdf_retain_pages@v1",
    "research.collect_url@v1", "data.compute_metrics@v1", "artifact.table_generate@v1",
    "artifact.export@v1", "content.produce@v1", "document.transform@v1", "document.fill_form@v1",
})


class InternalToolAvailability:
    async def available(self, capability_ref: str, tenant_id: str, user_id: str) -> bool:
        dependency = DEPENDENCIES.get(capability_ref)
        if not dependency:
            return capability_ref in LOCAL_CAPABILITIES
        try:
            return bool(await asyncio.wait_for(
                getattr(checks, dependency)(tenant_id, user_id), timeout=CHECK_TIMEOUT_SECONDS,
            ))
        except Exception:
            logger.warning("internal_tool_unavailable capability=%s tenant=%s", capability_ref, tenant_id, exc_info=True)
            return False

    async def unavailable(self, refs: list[str], tenant_id: str, user_id: str) -> set[str]:
        # Search and research share one check; independent dependencies run concurrently.
        dependencies = {DEPENDENCIES[ref] for ref in refs if ref in DEPENDENCIES}
        async def resolve(name):
            ref = next(ref for ref in refs if DEPENDENCIES.get(ref) == name)
            return name, await self.available(ref, tenant_id, user_id)
        results = dict(await asyncio.gather(*(resolve(name) for name in dependencies)))
        return {ref for ref in refs if (
            ref not in LOCAL_CAPABILITIES and ref not in DEPENDENCIES
        ) or (ref in DEPENDENCIES and not results[DEPENDENCIES[ref]])}


async def capability_available(capability_ref: str, tenant_id: str, user_id: str) -> bool:
    return await InternalToolAvailability().available(capability_ref, tenant_id, user_id)
