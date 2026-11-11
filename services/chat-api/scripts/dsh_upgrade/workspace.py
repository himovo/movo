from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import tarfile
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
        if replacements == 0 and not (
            re.search(r"export const ASKAI_DSH_KERNEL_VERSION\s*=\s*installedDshVersion\b", source)
            and re.search(
                r"const installedDshVersion\s*=\s*require\(['\"]@deepseek-ai/dsh/package\.json['\"]\)\.version",
                source,
            )
        ):
            raise ValueError("candidate staging could not update ASKAI_DSH_KERNEL_VERSION")
        if replacements:
            protocol_path.write_text(updated, encoding="utf-8")


class ReleasedWorkspace:
    """Materialize an immutable Runtime Host exactly as shipped by a release ref."""

    def __init__(self, repository_root: Path, source_ref: str, relative_path: Path) -> None:
        self.repository_root = repository_root
        self.source_ref = source_ref
        self.relative_path = relative_path
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self.path: Path | None = None

    def __enter__(self) -> Path:
        archive = subprocess.run(
            ["git", "archive", "--format=tar", self.source_ref, str(self.relative_path)],
            cwd=self.repository_root,
            check=False,
            capture_output=True,
        )
        if archive.returncode != 0:
            message = archive.stderr.decode("utf-8", errors="replace").strip()
            raise ValueError(f"cannot materialize rollback source {self.source_ref}: {message}")
        self._temporary = tempfile.TemporaryDirectory(prefix="movo-dsh-release-")
        root = Path(self._temporary.name)
        with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as bundle:
            for member in bundle.getmembers():
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ValueError(f"unsafe path in rollback source archive: {member.name}")
            bundle.extractall(root)
        self.path = root / self.relative_path
        if not self.path.is_dir():
            raise ValueError(
                f"rollback source {self.source_ref} does not contain {self.relative_path}"
            )
        return self.path

    def __exit__(self, *_args) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()
