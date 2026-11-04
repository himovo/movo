"""Install declarative Skill dependencies inside a disposable build container."""

from __future__ import annotations

import re
import shutil
import subprocess
import os
from pathlib import Path


SOURCE = Path("/skill")
BUILD = Path("/tmp/movo-skill-build")
APT_NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?(?:=[a-z0-9:~+._-]+)?$")


def step_timeout() -> int:
    try:
        value = int(os.environ.get("MOVO_SKILL_DEPENDENCY_STEP_TIMEOUT", "480"))
    except ValueError:
        value = 480
    return max(60, min(value, 1200))


def apt_packages(path: Path) -> list[str]:
    packages = [line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines()]
    packages = [name for name in packages if name]
    if len(packages) > 100 or any(not APT_NAME.fullmatch(name) for name in packages):
        raise ValueError("apt-packages.txt contains an invalid package name or too many packages")
    return packages


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True, timeout=step_timeout())


def configure_apt_mirror() -> None:
    mirror = os.environ.get("MOVO_APT_MIRROR", "").strip().rstrip("/")
    if not mirror:
        return
    if not mirror.startswith("https://") or any(char.isspace() for char in mirror):
        raise ValueError("Invalid apt mirror URL")
    sources = Path("/etc/apt/sources.list.d/debian.sources")
    content = sources.read_text(encoding="utf-8")
    content = content.replace("http://deb.debian.org/debian-security", f"{mirror}/debian-security")
    content = content.replace("http://deb.debian.org/debian", f"{mirror}/debian")
    sources.write_text(content, encoding="utf-8")


def main() -> None:
    shutil.copytree(SOURCE, BUILD)
    apt_file = BUILD / "apt-packages.txt"
    if apt_file.is_file():
        packages = apt_packages(apt_file)
        if packages:
            print("=== Installing system packages (apt) ===", flush=True)
            configure_apt_mirror()
            run("apt-get", "update")
            run("apt-get", "install", "-y", "--no-install-recommends", *packages)
            shutil.rmtree("/var/lib/apt/lists", ignore_errors=True)
    requirements = BUILD / "requirements.txt"
    if requirements.is_file():
        print("=== Installing Python dependencies (pip) ===", flush=True)
        run("python", "-m", "pip", "install", "--no-cache-dir", "--timeout", "60", "--retries", "2", "-r", str(requirements), cwd=BUILD)
    package_json = BUILD / "package.json"
    if package_json.is_file():
        print("=== Installing Node dependencies (npm) ===", flush=True)
        if not (BUILD / "package-lock.json").is_file():
            raise ValueError("A Skill with package.json must include package-lock.json")
        run("npm", "ci", "--omit=dev", "--fetch-retries=1", "--fetch-timeout=30000", "--prefix", str(BUILD))
        target = Path("/opt/movo-skill-node-modules")
        if (BUILD / "node_modules").is_dir():
            shutil.move(str(BUILD / "node_modules"), target)
    shutil.rmtree(BUILD)


if __name__ == "__main__":
    main()
