from __future__ import annotations

import io
import zipfile

import pytest

from app.services.skill_packages import SkillPackageError, validate_skill_zip


def archive(files: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path, content in files.items():
            bundle.writestr(path, content)
    return output.getvalue()


def skill_markdown(name: str = "sample-skill") -> str:
    return f"---\nname: {name}\ndescription: Test Skill\nversion: 1.2.3\ntools:\n  - read\n---\nUse read(path).\n"


def test_accepts_flat_and_single_directory_skill_bundles():
    flat = validate_skill_zip(archive({"SKILL.md": skill_markdown(), "_meta.json": '{"version":"1.2.3"}'}))
    nested = validate_skill_zip(archive({"sample/SKILL.md": skill_markdown(), "sample/references/a.txt": "a"}))
    assert flat.name == "sample-skill"
    assert flat.version == "1.2.3"
    assert flat.root_prefix == ""
    assert flat.markdown == "Use read(path).\n"
    assert nested.root_prefix == "sample/"
    assert nested.files[1]["path"] == "references/a.txt"


@pytest.mark.parametrize(
    ("files", "code"),
    [
        ({"README.md": "missing"}, "missing_skill_md"),
        ({"SKILL.md": "no frontmatter"}, "missing_frontmatter"),
        ({"SKILL.md": skill_markdown("Bad Name")}, "invalid_skill_name"),
        ({"a/SKILL.md": skill_markdown("a"), "b/SKILL.md": skill_markdown("b")}, "multiple_skills"),
        ({"a/b/SKILL.md": skill_markdown()}, "invalid_bundle_structure"),
    ],
)
def test_rejects_invalid_packages(files, code):
    with pytest.raises(SkillPackageError) as raised:
        validate_skill_zip(archive(files))
    assert raised.value.code == code


def test_reports_tool_references_missing_from_metadata():
    package = validate_skill_zip(archive({
        "SKILL.md": "---\nname: search-skill\ndescription: Search\ntools: [read]\n---\n```js\nweb_fetch({url: 'x'})\n```\n",
    }))
    assert package.referenced_tools == ("web_fetch",)
    assert package.warnings[0]["code"] == "undeclared_tool_reference"


def test_preserves_dsh_invocation_policy():
    package = validate_skill_zip(archive({
        "SKILL.md": "---\nname: private-skill\ndescription: Private\ndisable-model-invocation: true\nuser-invocable: false\n---\nBody\n",
    }))
    assert package.model_invocable is False
    assert package.user_invocable is False


def test_rejects_conflicting_market_identity():
    with pytest.raises(SkillPackageError) as raised:
        validate_skill_zip(archive({
            "SKILL.md": skill_markdown(),
            "_meta.json": '{"slug":"different-skill","version":"1.2.3"}',
        }))
    assert raised.value.code == "metadata_mismatch"


def test_accepts_version_mismatch_as_warning_and_uses_package_version():
    package = validate_skill_zip(archive({
        "SKILL.md": skill_markdown(),
        "_meta.json": '{"slug":"sample-skill","version":"1.0.10"}',
    }))
    assert package.version == "1.0.10"
    assert package.warnings == ({
        "code": "version_metadata_mismatch",
        "message": "_meta.json version does not match SKILL.md version; using the package version",
        "packageVersion": "1.0.10",
        "skillVersion": "1.2.3",
    },)
