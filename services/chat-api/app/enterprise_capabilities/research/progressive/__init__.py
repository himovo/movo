__all__ = ["ProgressiveResearchAgent"]


def __getattr__(name: str):
    # Keep the stable capability import surface while DSH reuses the tested
    # provider router without importing or constructing the old research loop.
    if name == "ProgressiveResearchAgent":
        from app.enterprise_capabilities.research.progressive.agent import ProgressiveResearchAgent

        return ProgressiveResearchAgent
    raise AttributeError(name)
