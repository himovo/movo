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


def disable_apt_cleanup() -> None:
    Path("/etc/apt/apt.conf.d/docker-clean").unlink(missing_ok=True)


def main() -> None:
    shutil.copytree(SOURCE, BUILD)
    offline = os.environ.get("MOVO_OFFLINE_ONLY") == "1"
    apt_file = BUILD / "apt-packages.txt"
    if apt_file.is_file():
        packages = apt_packages(apt_file)
        if packages:
            print("=== Installing system packages (apt) ===", flush=True)
            disable_apt_cleanup()
            apt = ("apt-get", "-o", "Dir::Cache::archives=/offline/apt-archives",
                   "-o", "Dir::State::lists=/offline/apt-lists",
                   "-o", "Binary::apt::APT::Keep-Downloaded-Packages=true")
            cached = subprocess.run(
                (*apt, "install", "-y", "--no-install-recommends", "--no-download", *packages),
                timeout=step_timeout(),
            ).returncode == 0
            if not cached and not offline:
                configure_apt_mirror()
                run(*apt, "update")
                run(*apt, "install", "-y", "--no-install-recommends", *packages)
            elif not cached:
                raise RuntimeError("Offline system dependencies are missing; inspect the apt output above")
    requirements = BUILD / "requirements.txt"
    if requirements.is_file():
        print("=== Installing Python dependencies (pip) ===", flush=True)
        wheelhouse = Path("/offline/pip")
        install = ("python", "-m", "pip", "install", "--no-index", "--find-links",
                   str(wheelhouse), "-r", str(requirements))
        installed = subprocess.run(install, cwd=BUILD, timeout=step_timeout()).returncode == 0
        if not installed and not offline:
            run("python", "-m", "pip", "wheel", "--wheel-dir", str(wheelhouse),
                "--timeout", "60", "--retries", "2", "-r", str(requirements), cwd=BUILD)
            run(*install, cwd=BUILD)
        elif not installed:
            raise RuntimeError("Offline Python dependencies are missing; inspect the pip output above")
    package_json = BUILD / "package.json"
    if package_json.is_file():
        print("=== Installing Node dependencies (npm) ===", flush=True)
        if not (BUILD / "package-lock.json").is_file():
            raise ValueError("A Skill with package.json must include package-lock.json")
        run("npm", "ci", "--omit=dev", "--fetch-retries=1", "--fetch-timeout=30000",
            "--cache", "/offline/npm", "--offline" if offline else "--prefer-offline",
            "--prefix", str(BUILD))
        target = Path("/opt/movo-skill-node-modules")
        if (BUILD / "node_modules").is_dir():
            shutil.move(str(BUILD / "node_modules"), target)
    shutil.rmtree(BUILD)


if __name__ == "__main__":
    main()
