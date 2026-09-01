from __future__ import annotations

import argparse
import ast
from pathlib import Path


RETIRED_ROOTS = ("runtime", "orchestrator", "pipeline", "skillsystem", "capabilities")
RETIRED_FILES = (
    "api/endpoints/chat.py",
    "context_engine/builder.py",
    "context_engine/coding.py",
    "context_engine/retrieval.py",
    "core/skills.py",
    "services/agent.py",
    "services/chat_pipeline_service.py",
    "services/presentation_runtime.py",
    "tools/basic.py",
    "tools/commercial.py",
    "tools/finance.py",
    "tools/kb_search.py",
    "tools/office.py",
    "tools/progressive_research.py",
)
FORBIDDEN_IMPORT_PREFIXES = tuple(f"app.{name}" for name in RETIRED_ROOTS)


def production_python_files(app_root: Path):
    for path in sorted(app_root.rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield path


def imported_modules(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append((node.lineno, node.module or ""))
    return found


def violations(app_root: Path) -> list[str]:
    failures: list[str] = []
    for relative in (*RETIRED_ROOTS, *RETIRED_FILES):
        if (app_root / relative).exists():
            failures.append(f"retired path exists: app/{relative}")
    for path in production_python_files(app_root):
        for line, module in imported_modules(path):
            if module.startswith(FORBIDDEN_IMPORT_PREFIXES):
                failures.append(
                    f"{path.relative_to(app_root)}:{line}: imports retired namespace {module}"
                )
    main_source = (app_root / "main.py").read_text(encoding="utf-8")
    if "app.include_router(dsh_chat.router" not in main_source:
        failures.append("app/main.py does not register the DSH chat router")
    if "app.include_router(chat.router" in main_source:
        failures.append("app/main.py registers the retired chat router")
    return failures


def main() -> int:
    default_root = Path(__file__).resolve().parents[1] / "app"
    parser = argparse.ArgumentParser(
        description="Reject restoration or use of the retired ASKAI Agent runtime."
    )
    parser.add_argument("--app-root", type=Path, default=default_root)
    args = parser.parse_args()
    failures = violations(args.app_root.resolve())
    if failures:
        print("DSH legacy runtime boundary guard failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("DSH legacy runtime boundary guard passed: DSH is the only Agent kernel.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
