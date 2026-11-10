from app.dsh_runtime.plugin_management.source_policy import is_safe_personal_source, is_supported_plugin_source


def test_personal_plugins_accept_portable_public_specs():
    for spec in (
        "@example/my-dsh-plugin@1.2.3",
        "movo-plugin@1.0.0-alpha.1",
        "https://registry.npmjs.org/example/-/example-1.2.3.tgz",
        "https://example.com/releases/plugin-1.2.3.tar.gz",
    ):
        assert is_safe_personal_source(spec), spec


def test_personal_plugins_reject_local_and_private_sources():
    for spec in (
        "/tmp/plugin.tgz", "../plugin", r"C:\\plugin.tgz", "file:/tmp/plugin.tgz",
        "link:../plugin", "git@github.com:example/plugin.git", "http://127.0.0.1/plugin.tgz",
        "plugin", "plugin@latest", "folder/plugin", "plugin@^1.0.0",
        "https://localhost/plugin.tgz", "https://10.0.0.4/plugin.tgz",
        "https://registry.npmjs.org/plugin?token=secret", "git+ssh://github.com/example/plugin",
        "https://github.com/example/dsh-plugin.git#v1.2.3",
        "git+https://github.com/example/dsh-plugin.git#main",
        "github:example/dsh-plugin#v1.2.3",
        "https://github.com/example/dsh-plugin/archive/refs/tags/v1.2.3.tar.gz?download=1",
    ):
        assert not is_safe_personal_source(spec), spec


def test_organization_sources_allow_internal_archives_but_reject_source_repositories():
    assert is_supported_plugin_source("https://packages.internal/plugin-1.2.3.tgz")
    assert not is_safe_personal_source("https://packages.internal/plugin-1.2.3.tgz")
    assert not is_supported_plugin_source("https://github.com/example/plugin.git#v1.2.3")
    assert not is_supported_plugin_source("https://github.com/example/plugin/archive/v1.2.3.tar.gz#source")
