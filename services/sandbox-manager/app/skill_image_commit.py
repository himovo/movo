"""Save prepared dependencies without rerunning installation on lease failures."""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from .skill_build_records import _safe_log


class SkillImageCommitError(RuntimeError):
    pass


def _detail(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        try:
            message = response.json().get("message", response.text)
        except (ValueError, AttributeError):
            message = response.text
        return _safe_log(f"Docker HTTP {response.status_code}: {message}")[:2000]
    return _safe_log(f"{type(exc).__name__}: {exc}")[:2000]


def _missing_lease(exc: Exception) -> bool:
    if not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code != 404:
        return False
    message = _detail(exc).lower()
    return "lease" in message and ("not found" in message or "does not exist" in message)


def save_skill_image(engine, container: str, image: str, *, deadline: float,
                     report: Callable[[str], None]) -> str:
    repository, tag = image.rsplit(":", 1)
    for attempt in range(1, 4):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SkillImageCommitError("Dependencies installed; image save exceeded the preparation time limit")
        try:
            return engine.commit(container, repository, tag, timeout=min(300, remaining))
        except Exception as exc:
            detail = _detail(exc)
            if not _missing_lease(exc):
                raise SkillImageCommitError(f"Dependencies installed; image save failed: {detail}") from exc
            # A daemon may publish the image before reporting a cleanup failure.
            try:
                existing = engine.image_id(image)
                if existing:
                    report(f"Image save reported a lease error; verified prepared image {existing}")
                    return existing
                engine.inspect(container)
            except Exception as inspect_error:
                raise SkillImageCommitError(
                    f"Dependencies installed; image save failed: {detail}; recovery check failed: {_detail(inspect_error)}"
                ) from exc
            delay = attempt * 2
            if attempt == 3 or deadline - time.monotonic() <= delay:
                raise SkillImageCommitError(
                    f"Dependencies installed; image save failed after {attempt} attempt(s): {detail}"
                ) from exc
            report(f"Image save attempt {attempt} failed: {detail}; retrying the same prepared container in {delay}s")
            time.sleep(delay)
    raise AssertionError("Unreachable image save state")
