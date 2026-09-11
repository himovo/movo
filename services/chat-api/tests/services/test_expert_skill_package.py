from __future__ import annotations

import io
import json
import zipfile

import pytest

from app.services.skill_packages import SkillPackageError, validate_skill_package


def zip_bytes(files: dict[str, str | bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return output.getvalue()


def child(slug: str, *, declared_name: str | None = None) -> bytes:
    name = declared_name or slug
    return zip_bytes({
        "SKILL.md": f"---\nname: {name}\ndescription: {slug} capability\nversion: 1.0.0\n---\nFollow {slug} instructions.\n",
        "references/guide.md": f"{slug} guide",
    })


def expert(*, include_second: bool = True) -> bytes:
    slugs = ["child-one", "child-two"] if include_second else ["child-one"]
    manifest = {
        "type": "skillhub-expert-package",
        "slug": "expert-demo",
        "displayName": "Expert Demo",
        "summary": "Route work across internal capabilities.",
        "skillSlugs": slugs,
        "skills": [{"slug": slug, "namespace": "test"} for slug in slugs],
    }
    descriptor = """---
name: expert-demo
description: Use for expert demo tasks.
version: 1.2.0
orchestration:
  children:
    - child-one
    - child-two
---
Use child-one first and child-two only when needed.
"""
    files: dict[str, str | bytes] = {
        "manifest.json": json.dumps(manifest),
        "skillsets/expert-demo.md": descriptor,
        "skills/child-one.zip": child("child-one"),
    }
    if include_second:
        files["skills/child-two.zip"] = child("child-two", declared_name="child-two-v2")
    return zip_bytes(files)


def test_compiles_expert_package_into_one_runtime_skill_with_internal_children():
    package = validate_skill_package(expert())

    assert package.package_kind == "expert_package"
    assert package.name == "expert-demo"
    assert package.display_name == "Expert Demo"
    assert package.version == "1.2.0"
    assert [item["slug"] for item in package.children] == ["child-one", "child-two"]
    assert "Use child-one first" in package.markdown
    assert '<child_skill name="child-one"' in package.markdown
    assert '<child_skill name="child-two"' in package.markdown
    assert "Do not invoke a child name through the DSH Skill loader" in package.markdown
    assert any(item["path"] == "children/child-one/references/guide.md" for item in package.files)
    assert package.warnings[0]["code"] == "expert_child_name_mismatch"


def test_rejects_expert_package_when_declared_child_zip_is_missing():
    with pytest.raises(SkillPackageError) as raised:
        validate_skill_package(expert(include_second=False))
    assert raised.value.code == "expert_children_mismatch"


def test_keeps_standard_skill_install_path_unchanged():
    package = validate_skill_package(child("ordinary-skill"))
    assert package.package_kind == "ordinary"
    assert package.children == ()


def test_expert_shape_without_manifest_reports_expert_manifest_error():
    malformed = zip_bytes({
        "skillsets/expert-demo.md": "---\nname: expert-demo\ndescription: Demo\n---\nRoute work.\n",
        "skills/child-one.zip": child("child-one"),
    })
    with pytest.raises(SkillPackageError) as raised:
        validate_skill_package(malformed)
    assert raised.value.code == "missing_expert_manifest"


def test_invalid_child_error_identifies_its_nested_zip():
    files = {
        "manifest.json": json.dumps({
            "type": "skillhub-expert-package", "slug": "expert-demo", "displayName": "Demo",
            "summary": "Demo", "skillSlugs": ["child-one"], "skills": [{"slug": "child-one"}],
        }),
        "skillsets/expert-demo.md": (
            "---\nname: expert-demo\ndescription: Demo\n"
            "orchestration:\n  children:\n    - child-one\n---\nRoute work.\n"
        ),
        "skills/child-one.zip": zip_bytes({"README.md": "missing SKILL.md"}),
    }
    with pytest.raises(SkillPackageError) as raised:
        validate_skill_package(zip_bytes(files))
    assert raised.value.code == "missing_skill_md"
    assert raised.value.file == "skills/child-one.zip"
