from app.dsh_runtime.plugin_management.capability_projection import projected_capabilities


def test_projection_attributing_native_session_capabilities_to_activated_bundle():
    baseline = {"clientModules": [{"id": "@deepseek-ai/dsh-client-connection", "rev": "base"}],
                "webRoutes": [{"kind": "prefix", "path": "/api"}],
                "remoteEndpoints": ["core/list"]}
    activated = {
        "clientModules": [*baseline["clientModules"], {"id": "paper-plugin", "rev": "v1", "conversationView": True}],
        "webRoutes": [*baseline["webRoutes"], {"kind": "prefix", "path": "/papers"}],
        "remoteEndpoints": [*baseline["remoteEndpoints"], "paper/list"],
        "bundles": [{"name": "paper-plugin", "rows": [{"rowId": "paper-host", "moduleName": "paper-plugin"}]}],
    }
    session_before = {"skills": [], "commands": [],
                      "modelProviders": [{"id": "movo", "name": "MOVO Gateway"}]}
    session_after = {
        "skills": [{"name": "paper-review", "provider": "paper-plugin", "userInvocable": True}],
        "commands": [{"name": "paper", "definitionId": "paper-plugin/paper"}],
        "modelProviders": [*session_before["modelProviders"],
                           {"id": "paper-provider", "name": "Paper Models"}],
    }
    value = projected_capabilities(
        baseline, activated, session_before, session_after, "paper-plugin",
        ["mcp__papers__search", "mcp__papers__read", "paper_tool"],
    )
    assert [item["name"] for item in value["skills"]] == ["paper-review"]
    assert [item["name"] for item in value["commands"]] == ["paper"]
    assert value["modelProviders"] == [{"id": "paper-provider", "name": "Paper Models"}]
    assert [item["id"] for item in value["clientModules"]] == ["paper-plugin"]
    assert value["clientModules"][0]["conversationView"] is True
    assert value["webRoutes"] == [{"kind": "prefix", "path": "/papers"}]
    assert value["remoteEndpoints"] == ["paper/list"]
    assert value["mcpServers"] == [{"name": "papers", "tools": ["read", "search"]}]


def test_global_skill_does_not_become_selectable_without_session_exposure():
    value = projected_capabilities(
        {"skills": []},
        {"skills": [{"name": "unavailable-skill", "userInvocable": True}],
         "bundles": [{"name": "paper-plugin", "rows": []}]},
        {"skills": []}, {"skills": []}, "paper-plugin", [],
    )
    assert value["skills"] == []


def test_existing_provider_catalog_change_is_not_misattributed_to_plugin():
    before = {"modelProviders": [{"id": "movo", "models": [{"id": "old"}]}]}
    after = {"modelProviders": [
        {"id": "movo", "models": [{"id": "new"}]},
        {"id": "plugin-provider", "catalogStatus": "available",
         "models": [{"id": "plugin-model"}]},
    ]}
    value = projected_capabilities(
        {"bundles": []}, {"bundles": [{"name": "plugin", "rows": []}]},
        before, after, "plugin", [],
    )
    assert [item["id"] for item in value["modelProviders"]] == ["plugin-provider"]
