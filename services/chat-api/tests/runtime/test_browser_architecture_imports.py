from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_native_browser_and_runtime_import_without_playwright_browser_engine() -> None:
    service_root = Path(__file__).resolve().parents[2]
    script = r'''
import builtins

real_import = builtins.__import__

def blocked(name, *args, **kwargs):
    if name == "playwright" or name.startswith("playwright."):
        raise ModuleNotFoundError("playwright browser engine is intentionally unavailable")
    return real_import(name, *args, **kwargs)

builtins.__import__ = blocked

for module_name in (
    "app.infrastructure.runtime_services",
    "app.enterprise_capabilities.browser.engine.desktop_agent_executor",
    "app.dsh_runtime.application",
    "app.main",
):
    __import__(module_name)
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=service_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_legacy_browser_backends_and_browser_qa_are_removed() -> None:
    service_root = Path(__file__).resolve().parents[2]
    removed_paths = (
        "app/runtime/browser/executor.py",
        "app/runtime/browser/interactive_agent.py",
        "app/runtime/browser/sandbox_executor.py",
        "app/runtime/browser/sandbox_interactive_agent.py",
        "app/runtime/browser/session_store.py",
        "app/runtime/browser/contexts/qa.py",
        "app/runtime/browser/test_mode.py",
        "app/runtime/sandbox",
        "app/api/endpoints/sandbox.py",
        "app/services/sandbox_provider_config.py",
    )
    leftovers = [path for path in removed_paths if (service_root / path).exists()]
    assert leftovers == []

    protected_runtime = (
        service_root
        / "app/enterprise_capabilities/browser/engine/desktop_agent_executor.py"
    ).read_text(encoding="utf-8")
    assert "qa_mark_case_done" not in protected_runtime
    assert "qa_flags" not in protected_runtime
    assert "runtime.browser.executor" not in protected_runtime
