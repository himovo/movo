from app.governance.suspensions.resume_admission import (
    is_trusted_task_continuation,
    trusted_resume_admission,
)


def test_public_resume_flag_is_not_trusted_by_itself():
    assert not is_trusted_task_continuation({"_runtime_resume_only": True})


def test_claimed_resume_context_allows_only_runtime_continuation():
    with trusted_resume_admission():
        assert is_trusted_task_continuation({"_runtime_resume_only": True})
        assert not is_trusted_task_continuation({})
        assert not is_trusted_task_continuation({"_runtime_resume_only": False})

    assert not is_trusted_task_continuation({"_runtime_resume_only": True})
