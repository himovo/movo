from __future__ import annotations

import asyncio
from copy import deepcopy

from app.enterprise_capabilities.browser.engine.action_history import BrowserActionHistory, target_identity
from app.enterprise_capabilities.browser.engine.effect_verification.contracts import EffectContract, EffectReceipt
from app.governance.action_receipt import ActionReceipt
from app.governance.action_receipt_store import ActionReceiptStore
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation


class FakeReceiptStore:
    def __init__(self) -> None:
        self.rows: list[ActionReceipt] = []

    async def upsert(self, receipt: ActionReceipt) -> ActionReceipt:
        self.rows = [row for row in self.rows if row.idempotency_key != receipt.idempotency_key]
        self.rows.append(deepcopy(receipt))
        return deepcopy(receipt)

    async def find_succeeded_by_business_key(self, key: str):
        rows = [row for row in self.rows if row.business_key == key and row.status == "succeeded"]
        return deepcopy(rows[-1]) if rows else None

    async def count_succeeded_by_business_key(self, key: str) -> int:
        return sum(1 for row in self.rows if row.business_key == key and row.status == "succeeded")


class FakePolicyClient:
    def __init__(self, **values) -> None:
        self.values = values

    async def ainvoke_structured(self, messages, schema):
        return schema(**self.values)


def observation(url: str = "https://example.test/posts/123?token=volatile#comments") -> Observation:
    return Observation(url=url, title="A durable target", elements=[])


def contract(operation: str = "contribute") -> EffectContract:
    return EffectContract(
        action_name="commit",
        operation_family="custom_contribution",
        entity="current object",
        side_effect="external",
        is_commit=True,
        completes_goal=True,
        intended_operation=operation,
        intended_entity="current object",
        source="model",
    )


def confirmed(effect_contract: EffectContract) -> EffectReceipt:
    return EffectReceipt(
        contract_key=effect_contract.key(),
        status="confirmed_success",
        confidence=0.95,
        action_name=effect_contract.action_name,
        operation_family=effect_contract.operation_family,
        entity=effect_contract.entity,
        completes_goal=True,
    )


def test_confirmed_target_scoped_action_blocks_a_future_run():
    asyncio.run(_confirmed_target_scoped_action_blocks_a_future_run())


async def _confirmed_target_scoped_action_blocks_a_future_run():
    store = FakeReceiptStore()
    client = FakePolicyClient(
        guard_across_runs=True,
        scope_dimensions=["actor", "system", "target", "operation"],
        max_confirmed=1,
        purpose="independent contribution",
        confidence=0.96,
        reason="the same durable target must not receive the same contribution twice",
    )
    effect_contract = contract()
    first = BrowserActionHistory(
        actor_id="user-1",
        attempt_id="run-1",
        store=store,  # type: ignore[arg-type]
        goal="Handle an unprocessed target without repeating it",
        original_request="Choose a target not handled before",
        lang="en",
        llm=client,
    )

    first_check = await first.preflight(contract=effect_contract, observation=observation())
    assert first_check.blocked is False
    assert first_check.intent.business_key
    await first.record(confirmed(effect_contract), observation())

    second = BrowserActionHistory(
        actor_id="user-1",
        attempt_id="run-2",
        store=store,  # type: ignore[arg-type]
        goal="Handle an unprocessed target without repeating it",
        original_request="Choose a target not handled before",
        lang="en",
        llm=client,
    )
    second_check = await second.preflight(contract=effect_contract, observation=observation())

    assert second_check.blocked is True
    assert second_check.prior_receipt is not None


def test_future_runs_remain_allowed_when_policy_is_attempt_only():
    asyncio.run(_future_runs_remain_allowed_when_policy_is_attempt_only())


async def _future_runs_remain_allowed_when_policy_is_attempt_only():
    store = FakeReceiptStore()
    client = FakePolicyClient(
        guard_across_runs=False,
        scope_dimensions=[],
        max_confirmed=1,
        purpose="repeatable future operation",
        confidence=0.98,
        reason="future independent runs may repeat",
    )
    effect_contract = contract()
    history = BrowserActionHistory(
        actor_id="user-1",
        attempt_id="run-1",
        store=store,  # type: ignore[arg-type]
        goal="Perform the requested operation",
        original_request="Perform it now",
        lang="en",
        llm=client,
    )

    check = await history.preflight(contract=effect_contract, observation=observation())
    await history.record(confirmed(effect_contract), observation())

    assert check.blocked is False
    assert check.intent.business_key == ""
    assert len(store.rows) == 1


def test_unknown_effect_is_not_persisted_as_success():
    asyncio.run(_unknown_effect_is_not_persisted_as_success())


async def _unknown_effect_is_not_persisted_as_success():
    store = FakeReceiptStore()
    client = FakePolicyClient(
        guard_across_runs=True,
        scope_dimensions=["actor", "system", "target", "operation"],
        purpose="durable operation",
        confidence=0.95,
    )
    effect_contract = contract()
    history = BrowserActionHistory(
        actor_id="user-1",
        attempt_id="run-1",
        store=store,  # type: ignore[arg-type]
        goal="Do not repeat the same target",
        original_request="Do not repeat the same target",
        lang="en",
        llm=client,
    )
    await history.preflight(contract=effect_contract, observation=observation())
    receipt = confirmed(effect_contract).model_copy(update={"status": "unknown"})

    assert await history.record(receipt, observation()) is None
    assert store.rows == []


def test_target_identity_is_stable_across_volatile_query_and_fragment():
    system, target = target_identity(observation())
    assert system == "example.test"
    assert target == "https://example.test/posts/123"


def test_target_identity_keeps_business_query_parameters():
    _, first = target_identity(observation("https://example.test/detail?id=123&token=one"))
    _, second = target_identity(observation("https://example.test/detail?token=two&id=456"))
    assert first == "https://example.test/detail?id=123"
    assert second == "https://example.test/detail?id=456"
    assert first != second


def test_target_identity_keeps_business_parameters_in_spa_routes():
    _, target = target_identity(
        observation("https://example.test/#/detail?token=volatile&id=123"),
    )
    assert target == "https://example.test/#/detail?id=123"


def test_target_identity_supports_root_query_business_objects_and_ports():
    system, target = target_identity(
        observation("http://example.test:8080/?token=volatile&id=123"),
    )
    assert system == "example.test:8080"
    assert target == "http://example.test:8080/?id=123"


def test_old_action_receipts_remain_valid_without_business_fields():
    row = ActionReceipt(
        action_id="a1",
        idempotency_key="i1",
        status="succeeded",
    )
    assert row.business_key == ""
    assert row.replay_policy == {}


def test_same_target_with_a_different_operation_has_a_different_business_key():
    async def scenario():
        store = FakeReceiptStore()
        client = FakePolicyClient(
            guard_across_runs=True,
            scope_dimensions=["actor", "system", "target", "operation"],
            purpose="target operation",
            confidence=0.95,
        )
        first_contract = contract("contribute")
        first = BrowserActionHistory(
            actor_id="user-1", attempt_id="run-1", store=store,  # type: ignore[arg-type]
            goal="Operate once per target", original_request="Operate once per target",
            lang="en", llm=client,
        )
        first_check = await first.preflight(contract=first_contract, observation=observation())
        await first.record(confirmed(first_contract), observation())

        second_contract = contract("transition")
        second = BrowserActionHistory(
            actor_id="user-1", attempt_id="run-2", store=store,  # type: ignore[arg-type]
            goal="Perform another operation", original_request="Perform another operation",
            lang="en", llm=client,
        )
        second_check = await second.preflight(contract=second_contract, observation=observation())
        assert first_check.intent.business_key != second_check.intent.business_key
        assert second_check.blocked is False

    asyncio.run(scenario())


def test_receipt_store_loads_latest_confirmed_business_action():
    async def scenario():
        store = ActionReceiptStore()
        expected = ActionReceipt(
            action_id="action-1",
            idempotency_key="attempt-1",
            business_key="business-1",
            status="succeeded",
        )

        async def load_latest(query):
            assert query == {"business_key": "business-1", "status": "succeeded"}
            return expected

        store._load_latest = load_latest  # type: ignore[method-assign]
        found = await store.find_succeeded_by_business_key("business-1")

        assert found == expected
        assert found is not expected
        assert store._by_action_id["action-1"] == expected

    asyncio.run(scenario())


def test_model_cannot_remove_actor_or_operation_isolation():
    async def scenario():
        store = FakeReceiptStore()
        client = FakePolicyClient(
            guard_across_runs=True,
            scope_dimensions=["target"],
            purpose="one operation per target",
            confidence=0.99,
        )
        first_contract = contract("contribute")
        first = BrowserActionHistory(
            actor_id="user-1", attempt_id="run-1", store=store,  # type: ignore[arg-type]
            goal="Operate once per target", original_request="Operate once per target",
            lang="en", llm=client,
        )
        first_check = await first.preflight(contract=first_contract, observation=observation())
        await first.record(confirmed(first_contract), observation())

        another_actor = BrowserActionHistory(
            actor_id="user-2", attempt_id="run-2", store=store,  # type: ignore[arg-type]
            goal="Operate once per target", original_request="Operate once per target",
            lang="en", llm=client,
        )
        actor_check = await another_actor.preflight(
            contract=first_contract,
            observation=observation(),
        )

        another_operation = BrowserActionHistory(
            actor_id="user-1", attempt_id="run-3", store=store,  # type: ignore[arg-type]
            goal="Perform another operation", original_request="Perform another operation",
            lang="en", llm=client,
        )
        operation_check = await another_operation.preflight(
            contract=contract("transition"),
            observation=observation(),
        )

        assert first_check.intent.policy.scope_dimensions[:4] == [
            "actor", "system", "target", "operation",
        ]
        assert actor_check.blocked is False
        assert operation_check.blocked is False

    asyncio.run(scenario())


def test_receipt_store_reads_a_just_persisted_business_action_from_memory():
    async def scenario():
        store = ActionReceiptStore()
        expected = ActionReceipt(
            action_id="action-memory",
            idempotency_key="attempt-memory",
            business_key="business-memory",
            status="succeeded",
        )

        async def no_persist(_receipt):
            return None

        async def no_database_row(_query):
            return None

        store._persist = no_persist  # type: ignore[method-assign]
        store._load_latest = no_database_row  # type: ignore[method-assign]
        await store.upsert(expected)

        found = await store.find_succeeded_by_business_key("business-memory")
        assert found == expected

    asyncio.run(scenario())


def test_receipt_store_never_treats_failed_business_action_as_success():
    async def scenario():
        store = ActionReceiptStore()

        async def no_persist(_receipt):
            return None

        async def no_database_row(_query):
            return None

        store._persist = no_persist  # type: ignore[method-assign]
        store._load_latest = no_database_row  # type: ignore[method-assign]
        await store.upsert(ActionReceipt(
            action_id="action-failed",
            idempotency_key="attempt-failed",
            business_key="business-failed",
            status="failed",
        ))

        found = await store.find_succeeded_by_business_key("business-failed")
        assert found is None

    asyncio.run(scenario())
