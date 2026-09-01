"""Token vocabularies — one file per concern.

Importing from the package root gives you every symbol; importing
from a submodule (``rules.tokens.crud``) narrows the surface.
"""
from .common import CONFIRM, CANCEL, LOADING
from .crud import ADD, EDIT, DELETE, VIEW
from .nav import NEXT, PREV, LOAD_MORE, SEARCH
from .form import REQUIRED_MARKERS, VALIDATION_ERROR, SUCCESS_TOAST

__all__ = [
    "CONFIRM", "CANCEL", "LOADING",
    "ADD", "EDIT", "DELETE", "VIEW",
    "NEXT", "PREV", "LOAD_MORE", "SEARCH",
    "REQUIRED_MARKERS", "VALIDATION_ERROR", "SUCCESS_TOAST",
]
