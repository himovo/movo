from app.enterprise_capabilities.browser.engine.stagnation_budget import StagnationBudget


def test_stops_repeated_recovery_cycles_on_the_same_url() -> None:
    budget = StagnationBudget(max_notices=3)

    assert budget.record_notice("https://example.test/search") is False
    assert budget.record_notice("https://example.test/search") is False
    assert budget.record_notice("https://example.test/search") is True
    assert budget.notices == 3


def test_navigation_resets_the_recovery_budget() -> None:
    budget = StagnationBudget(max_notices=2)

    assert budget.record_notice("https://example.test/search") is False
    assert budget.record_notice("https://example.test/question/1") is False
    assert budget.notices == 1
