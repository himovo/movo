import asyncio

from app.dsh_runtime.plugin_management import current_assessment


def test_reassessment_rejects_package_that_changed_behind_fixed_record(monkeypatch):
    class Installer:
        async def inspect_and_install(self, spec, **kwargs):
            return {
                "name": "plugin", "version": "2.0.0", "tool_names": ["new_tool"],
                "availability": {"status": "session_exposed", "dsh_version": "0.2.2"},
            }

    class Repository:
        def __init__(self):
            self.assessment = None

        async def update_assessment(self, **kwargs):
            self.assessment = kwargs
            return kwargs

    repository = Repository()
    monkeypatch.setattr(current_assessment, "DshPluginInstaller", lambda: Installer())
    asyncio.run(current_assessment.assess_existing_installation(
        {"_id": "a" * 24, "main_id": "tenant", "owner_user_id": "",
         "name": "plugin", "version": "1.0.0", "spec": "plugin@1.0.0"},
        repository=repository, dsh_version="0.2.2",
    ))
    assert repository.assessment["availability"]["status"] == "failed"
    assert repository.assessment["availability"]["reason"] == "plugin_package_changed"
    assert repository.assessment["tool_names"] == []
