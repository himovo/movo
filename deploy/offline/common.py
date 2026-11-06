"""Shared offline deployment contracts. Uses Python's standard library only."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

SCHEMA = 1


def run(args, *, cwd=None, capture=False):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("MOVO_", "COMPOSE_", "DOCKER_DEFAULT_PLATFORM"))}
    return subprocess.run(args, cwd=cwd, env=env, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def compose():
    for command in (["docker", "compose"], ["docker-compose"]):
        try:
            value = run(command + ["version"], capture=True)
        except (OSError, subprocess.CalledProcessError):
            continue
        match = re.search(r"(?:Docker Compose|docker-compose) version v?(\d+)\.", value)
        if match and int(match[1]) >= 2:
            return command
    raise ValueError("Docker Compose v2 or newer is required")


def config(root, *, env_file=None, override=None):
    selected_env = env_file or root / ".env"
    if not selected_env.exists():
        selected_env = Path("/dev/null")
    args = compose() + ["--env-file", str(selected_env), "--profile", "sandbox",
                        "--profile", "sandbox-image", "-f", str(root / "docker-compose.yml")]
    if override:
        args += ["-f", str(override)]
    return json.loads(run(args + ["config", "--format", "json"], cwd=root, capture=True))


def inspect(ref):
    return json.loads(run(["docker", "image", "inspect", ref], capture=True))[0]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def read_env(path):
    result = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\s*([A-Z][A-Z0-9_]*)=(.*)$", line)
            if match:
                result[match[1]] = match[2].strip().strip("\"'")
    return result


def merge_env(text, updates):
    lines = []
    seen = set()
    for line in text.splitlines():
        match = re.match(r"^\s*([A-Z][A-Z0-9_]*)=", line)
        if match and match[1] in updates:
            key = match[1]
            if key not in seen:
                lines.append(f"{key}={updates[key]}")
                seen.add(key)
        else:
            lines.append(line)
    lines.extend(f"{key}={value}" for key, value in updates.items() if key not in seen)
    return "\n".join(lines) + "\n"


def safe_path(root, name):
    path = root / name
    if Path(name).is_absolute() or ".." in Path(name).parts or path.is_symlink():
        raise ValueError(f"Invalid bundle path: {name}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Bundle path escapes deployment directory")
    return path
