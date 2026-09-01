from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from bson import ObjectId

from app.dsh_runtime.chat_service import DshChatService, PreparedTurn
from app.dsh_runtime.turn_admission import TurnSkillSelection
from app.scheduled_tasks.dsh_execution import ScheduledDshExecution
from app.scheduled_tasks.runner import ScheduledChatRunner


CHAT_API_ROOT = Path(__file__).parents[2]
REPOSITORY_ROOT = CHAT_API_ROOT.parents[1]


def test_every_formal_frontend_chat_turn_uses_the_dsh_endpoint() -> None:
    source = (
        REPOSITORY_ROOT / "apps" / "user-web" / "src" / "composables" / "useChatStream.ts"
    ).read_text(encoding="utf-8")
    assert "'/askai-api/api/chat/completions'" in source
    assert "/legacy" not in source
    assert "/execution-v3/run" not in source


def test_production_router_and_scheduler_do_not_register_legacy_agent_execution() -> None:
    main = (CHAT_API_ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "app.include_router(dsh_chat.router" in main
    assert "app.include_router(chat.router" not in main

    scheduled_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (CHAT_API_ROOT / "app" / "scheduled_tasks").glob("*.py")
    )
    forbidden = (
        "chat_pipeline_service",
        "TaskGraphRuntimeOrchestrator",
        "run_knowledge_qa_runtime_stream",
        "app.runtime.graph",
        "app.pipeline.planner",
        "app.skillsystem",
    )
    assert not any(item in scheduled_sources for item in forbidden)
    assert "dsh_runtime_application" in scheduled_sources

    task_routes = (CHAT_API_ROOT / "app" / "api" / "endpoints" / "tasks.py").read_text(
        encoding="utf-8"
    )
    assert "app.runtime.contracts.task_graph" not in task_routes
    assert "app.runtime.runtime_services" not in task_routes
    assert '@router.post("/action/resume")' not in task_routes
    assert '@router.get("/tasks/{run_id}/execution-view")' not in task_routes
    assert "_start_chat_completions" in task_routes


def test_workflow_skill_is_adaptive_and_never_compiles_a_task_graph() -> None:
    source = (
        CHAT_API_ROOT / "app" / "dsh_runtime" / "profile" / "skills" / "workflow.py"
    ).read_text(encoding="utf-8")
    assert "供 DSH Agent Loop 使用的自适应 Skill" in source
    assert "不是固定图执行计划" in source
    assert "TaskGraph(" not in source


class _Collection:
    def __init__(self) -> None:
        self.updates: list[tuple[dict, dict]] = []

    async def update_one(self, query, update):
        self.updates.append((query, update))
        return SimpleNamespace(modified_count=1)


class _Database:
    def __init__(self) -> None:
        self.chat_sessions = _Collection()
        self.chat_messages = _Collection()
        self.collections: dict[str, _Collection] = {}

    def __getitem__(self, name: str) -> _Collection:
        return self.collections.setdefault(name, _Collection())


class _ScheduledChat:
    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.calls: list[dict] = []

    async def prepare_turn(self, **kwargs):
        self.calls.append(kwargs)
        return PreparedTurn(
            conversation_id=self.conversation_id,
            message_id="msg-scheduled",
            binding_id="binding-scheduled",
        )

    async def wait_turn(self, message_id: str) -> str:
        assert message_id == "msg-scheduled"
        await asyncio.sleep(0)
        return "completed"


def test_scheduled_turn_reuses_dsh_chat_profile_skill_and_projection(monkeypatch) -> None:
    async def run() -> None:
        from app.scheduled_tasks import dsh_execution as module

        database = _Database()
        conversation_id = str(ObjectId())
        chat = _ScheduledChat(conversation_id)

        async def admit(**kwargs):
            assert kwargs == {
                "tenant_id": "tenant-a",
                "user_id": "user-a",
                "selected_skill_id": "workflow-a",
            }
            return TurnSkillSelection(selected_skill_id="workflow-a")

        monkeypatch.setattr(module, "get_db", lambda: database)
        monkeypatch.setattr(module, "admit_skill_selection", admit)
        executor = ScheduledDshExecution(lambda: chat)  # type: ignore[arg-type]
        job = {
            "_id": ObjectId(),
            "timezone": "Asia/Shanghai",
            "prompt": "生成日报",
            "output_spec": {
                "model_id": "model-a",
                "selected_skill_id": "workflow-a",
                "knowledgeQaEnabled": True,
                "knowledgeBaseIds": ["kb-a"],
            },
        }
        run_row = {"run_id": "run-a"}
        turn = await executor.start(
            job=job,
            run=run_row,
            conversation_id=None,
            conversation_title="日报 · 2026-08-25",
            tenant_id="tenant-a",
            user_id="user-a",
        )
        observers = list(executor._observers)
        await asyncio.gather(*observers)

        assert turn.conversation_id == conversation_id
        assert len(chat.calls) == 1
        call = chat.calls[0]
        assert call["conversation_id"] is None
        assert call["timezone_name"] == "Asia/Shanghai"
        assert call["selected_skill_id"] == "workflow-a"
        assert call["knowledge_qa_enabled"] is True
        assert call["knowledge_base_ids"] == ["kb-a"]
        run_updates = database.collections["scheduled_job_runs"].updates
        assert [update[1]["$set"]["status"] for update in run_updates] == ["running", "completed"]
        assert database.chat_sessions.updates[-1][1]["$set"]["scheduled_unread"] is True

    asyncio.run(run())


def test_new_per_run_schedule_defers_conversation_creation_to_dsh() -> None:
    async def run() -> None:
        runner = ScheduledChatRunner()
        conversation_id, title = await runner._resolve_target(
            {
                "session_mode": "new_per_run",
                "timezone": "Asia/Shanghai",
                "name": "日报",
                "session_title_template": "{name} · {date}",
            },
            {"scheduled_for": __import__("datetime").datetime(2026, 8, 25, 1, 0)},
            tenant_id="tenant-a",
            user_id="user-a",
        )
        assert conversation_id is None
        assert title == "日报 · 2026-08-25"

    asyncio.run(run())


def test_existing_pre_dsh_conversation_creates_a_kernel_binding_instead_of_falling_back() -> None:
    async def run() -> None:
        class Conversations:
            async def owned(self, *_args, **_kwargs):
                return {"_id": "conversation-a"}

            async def append_message(self, **_kwargs):
                return None

            async def mark_active_run(self, **_kwargs):
                return None

        class Bindings:
            async def current(self, *_args, **_kwargs):
                return None

            async def claim_turn(self, _binding_id, **_kwargs):
                return binding

            async def finish_turn(self, *_args, **_kwargs):
                return None

        class Profiles:
            async def publish_model_profile(self, **_kwargs):
                return SimpleNamespace(profile_version="profile-a", model_instance_id="model-a")

            async def compile_model_profile(self, **_kwargs):
                return SimpleNamespace(profile_version="profile-a", model_instance_id="model-a")

        class Coordinator:
            def __init__(self) -> None:
                self.created = 0

            async def create_binding(self, **_kwargs):
                self.created += 1
                return binding

            async def restore(self, current):
                return current

        binding = {
            "binding_id": "binding-a",
            "tenant_id": "tenant-a",
            "user_id": "user-a",
            "conversation_id": "conversation-a",
            "kernel_session_id": "session-a",
            "runtime_id": "runtime-a",
            "profile_version": "profile-a",
            "model_instance_id": "model-a",
            "execution_location": "server",
        }
        coordinator = Coordinator()
        service = DshChatService(
            gateway=SimpleNamespace(),
            coordinator=coordinator,  # type: ignore[arg-type]
            conversations=Conversations(),  # type: ignore[arg-type]
            bindings=Bindings(),  # type: ignore[arg-type]
            events=SimpleNamespace(),
            profiles=Profiles(),  # type: ignore[arg-type]
            kernel_version="0.1.0-rc.6",
        )

        async def finish_immediately(**_kwargs):
            return "completed"

        service._turn_runner.run = finish_immediately  # type: ignore[method-assign]
        turn = await service.prepare_turn(
            tenant_id="tenant-a",
            user_id="user-a",
            conversation_id="conversation-a",
            text="继续旧会话",
            model_instance_id="model-a",
            timezone_name="Asia/Shanghai",
            images=[],
            documents=[],
        )
        assert turn.conversation_id == "conversation-a"
        assert coordinator.created == 1
        assert await service.wait_turn(turn.message_id) == "completed"

    asyncio.run(run())
