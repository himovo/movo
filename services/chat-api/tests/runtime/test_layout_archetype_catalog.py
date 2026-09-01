from app.services.presentation.layout_archetypes import ARCHETYPE_CATALOG, archetype_by_id


def test_catalog_contains_25_unique_archetypes() -> None:
    ids = [item.archetype_id for item in ARCHETYPE_CATALOG]
    assert len(ids) == 25
    assert len(set(ids)) == 25
    assert all(item.family for item in ARCHETYPE_CATALOG)
    assert all(item.prompt_brief for item in ARCHETYPE_CATALOG)
    assert all(item.must_do for item in ARCHETYPE_CATALOG)


def test_catalog_lookup_is_strict() -> None:
    assert archetype_by_id("architecture_blueprint").family == "process_system"
