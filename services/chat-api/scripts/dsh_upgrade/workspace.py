from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path


DSH_VERSION_PATTERN = re.compile(
    r"(export const ASKAI_DSH_KERNEL_VERSION\s*=\s*['\"])([^'\"]+)(['\"])",
)


class CandidateWorkspace:
    def __init__(self, host_root: Path, candidate_version: str) -> None:
        self.host_root = host_root
        self.candidate_version = candidate_version
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self.path: Path | None = None

    def __enter__(self) -> Path:
        self._temporary = tempfile.TemporaryDirectory(prefix="askai-dsh-candidate-")
        self.path = Path(self._temporary.name)
        for directory in ("src", "config", "tests", "scripts"):
            shutil.copytree(self.host_root / directory, self.path / directory)
        for filename in ("package.json", "pnpm-workspace.yaml"):
            source = self.host_root / filename
            if source.exists():
                shutil.copy2(source, self.path / filename)
        self._pin_candidate()
        return self.path

    def __exit__(self, *_args) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()

    def _pin_candidate(self) -> None:
        assert self.path is not None
        package_path = self.path / "package.json"
        package = json.loads(package_path.read_text(encoding="utf-8"))
        dependencies = package.get("dependencies", {})
        for name in list(dependencies):
            if name == "@deepseek-ai/dsh" or name.startswith("@deepseek-ai/dsh-"):
                dependencies[name] = self.candidate_version
        package_path.write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        protocol_path = self.path / "src" / "host-protocol.mjs"
        source = protocol_path.read_text(encoding="utf-8")
        updated, replacements = DSH_VERSION_PATTERN.subn(
            rf"\g<1>{self.candidate_version}\g<3>", source, count=1,
        )
        if replacements != 1:
            raise ValueError("candidate staging could not update ASKAI_DSH_KERNEL_VERSION")
        protocol_path.write_text(updated, encoding="utf-8")
