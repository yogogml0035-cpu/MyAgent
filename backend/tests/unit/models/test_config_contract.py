from app.config import load_settings


def test_load_settings_does_not_expose_unsupported_subagent_concurrency_env(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("MYAGENT_TASK_ROOT", str(tmp_path))
    monkeypatch.setenv("MYAGENT_MAX_CONCURRENT_SUBAGENTS", "9")

    settings = load_settings()

    assert not hasattr(settings, "max_concurrent_subagents")
