from pathlib import Path
from types import SimpleNamespace

import importlib.util


SCRIPT = Path(__file__).parents[2] / "sandbox_script" / "prepare_skill.py"
spec = importlib.util.spec_from_file_location("prepare_skill", SCRIPT)
prepare_skill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare_skill)


def test_offline_python_install_uses_local_wheelhouse(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "skill"
    source.mkdir()
    (source / "requirements.txt").write_text("example==1.0\n", encoding="utf-8")
    monkeypatch.setattr(prepare_skill, "SOURCE", source)
    monkeypatch.setattr(prepare_skill, "BUILD", tmp_path / "build")
    monkeypatch.setenv("MOVO_OFFLINE_ONLY", "1")
    calls = []

    def execute(args, **kwargs):
        calls.append(tuple(args))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(prepare_skill.subprocess, "run", execute)
    prepare_skill.main()

    assert len(calls) == 1
    assert "--no-index" in calls[0]
    assert "--find-links" in calls[0]
    assert "wheel" not in calls[0]


def test_offline_npm_install_uses_cache(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "skill"
    source.mkdir()
    (source / "package.json").write_text("{}", encoding="utf-8")
    (source / "package-lock.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(prepare_skill, "SOURCE", source)
    monkeypatch.setattr(prepare_skill, "BUILD", tmp_path / "build")
    monkeypatch.setenv("MOVO_OFFLINE_ONLY", "1")
    calls = []
    monkeypatch.setattr(prepare_skill.subprocess, "run", lambda args, **kwargs: calls.append(args) or SimpleNamespace(returncode=0))

    prepare_skill.main()

    assert any("--offline" in call and "/offline/npm" in call for call in calls)


def test_offline_apt_install_uses_cached_archives(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "skill"
    source.mkdir()
    (source / "apt-packages.txt").write_text("curl\n", encoding="utf-8")
    monkeypatch.setattr(prepare_skill, "SOURCE", source)
    monkeypatch.setattr(prepare_skill, "BUILD", tmp_path / "build")
    monkeypatch.setenv("MOVO_OFFLINE_ONLY", "1")
    monkeypatch.setattr(prepare_skill, "disable_apt_cleanup", lambda: None)
    calls = []
    monkeypatch.setattr(prepare_skill.subprocess, "run", lambda args, **kwargs: calls.append(args) or SimpleNamespace(returncode=0))

    prepare_skill.main()

    assert len(calls) == 1
    assert "--no-download" in calls[0]
    assert "update" not in calls[0]
