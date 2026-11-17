import pytest

from app import offline_image_compatibility as compatibility


class Engine:
    def image_id(self, image):
        return {"source": "source", "target": "target"}.get(image)


def test_legacy_archive_accepts_matching_environments(monkeypatch):
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "target")
    monkeypatch.setattr(compatibility, "fingerprint", lambda engine, image, kind: {
        "python": [3, 10], "libc": ["glibc", "2.36"], "arch": "x86_64",
    })
    compatibility.verify(Engine(), {"baseImageId": "source"}, script=True, runtime=False, apt=False)


def test_archive_rejects_incompatible_python(monkeypatch):
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "target")
    monkeypatch.setattr(compatibility, "fingerprint", lambda engine, image, kind: {
        "python": [3, 10 if image == "source" else 11],
    })
    with pytest.raises(ValueError, match="incompatible"):
        compatibility.verify(Engine(), {"baseImageId": "source"}, script=True, runtime=False, apt=False)


def test_apt_cache_requires_identical_base_image(monkeypatch):
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "target")
    with pytest.raises(ValueError, match="same sandbox base image"):
        compatibility.verify(Engine(), {"baseImageId": "source"}, script=True, runtime=False, apt=True)


def test_archive_requires_source_identity(monkeypatch):
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "target")
    with pytest.raises(ValueError, match="identity is missing"):
        compatibility.verify(Engine(), {}, script=True, runtime=False, apt=False)


def test_new_archive_uses_embedded_environment_without_source_image(monkeypatch):
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "target")
    expected = {"python": [3, 10], "arch": "x86_64"}
    monkeypatch.setattr(compatibility, "fingerprint", lambda engine, image, kind: expected)
    compatibility.verify(Engine(), {
        "baseImageId": "unavailable-source",
        "baseImageEnvironment": expected,
    }, script=True, runtime=False, apt=False)
