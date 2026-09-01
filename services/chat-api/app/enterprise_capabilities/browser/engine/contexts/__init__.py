"""Browser task contexts — one per task category.

Public API:
    BrowserTaskContext  — the ABC every context subclasses
    NullContext         — no-op for tasks that don't need special handling
    FormContext         — single-shot form submit
    ScrapeContext       — paginated extraction
    GeneralBrowserContext — stateful fallback for ordinary browser tasks
    factory.maybe_init  — dispatcher used by the executor
"""
from .base import BrowserTaskContext
from .null import NullContext
from .form import FormContext
from .general import GeneralBrowserContext
from .scrape import ScrapeContext
from . import factory

__all__ = [
    "BrowserTaskContext",
    "NullContext",
    "FormContext",
    "GeneralBrowserContext",
    "ScrapeContext",
    "factory",
]
