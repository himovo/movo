from __future__ import annotations

import subprocess
import time
from pathlib import Path

from .models import CommandResult


def run_command(name: str, command: list[str], *, cwd: Path, timeout: int) -> CommandResult:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return CommandResult(
            name=name,
            command=command,
            returncode=completed.returncode,
            duration_seconds=round(time.monotonic() - started, 3),
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    except subprocess.TimeoutExpired as error:
        return CommandResult(
            name=name,
            command=command,
            returncode=124,
            duration_seconds=round(time.monotonic() - started, 3),
            stdout=(error.stdout or "") if isinstance(error.stdout, str) else "",
            stderr=((error.stderr or "") if isinstance(error.stderr, str) else "") + "\ncommand timed out",
        )
