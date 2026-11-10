from app.dsh_runtime.plugin_management.release_compatibility import incompatible_release


def test_declared_release_train_allows_newer_build_in_same_minor_line():
    manifest = {"name": "context", "version": "0.83.0", "compatibility": {"dshReleases": {
        "0.2.0-rc.2+": "compatible", "0.2.1-rc.2+": "compatible", "0.2.2-rc.1+": "compatible",
    }}}
    assert incompatible_release(manifest, "0.2.1-alpha.1") == ""
    assert incompatible_release(manifest, "0.2.1-rc.2") == ""
    assert incompatible_release(manifest, "0.2.1") == ""
    assert "current DSH 0.1.6" in incompatible_release(manifest, "0.1.6")


def test_explicitly_excluded_release_is_rejected():
    manifest = {"name": "context", "version": "0.83.0", "compatibility": {"dshReleases": {
        "0.2.0-rc.2": "compatible", "0.2.1-alpha.1": "incompatible",
    }}}
    assert "explicitly excludes" in incompatible_release(manifest, "0.2.1-alpha.1")


def test_undeclared_release_train_defers_to_native_dsh_peer_check():
    assert incompatible_release({"name": "plugin", "version": "1.0.0"}, "0.2.1-alpha.1") == ""
