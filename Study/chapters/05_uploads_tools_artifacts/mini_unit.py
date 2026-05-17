from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SUPPORTED_UPLOADS = {".md", ".json", ".txt", ".docx", ".xlsx", ".xlsm"}


def is_supported_upload(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_UPLOADS


def resolve_task_upload_path(workspace_root: Path, task_id: str, filename: str) -> Path:
    root = workspace_root.resolve()
    upload_dir = (root / task_id / "uploads").resolve()
    target = (upload_dir / filename).resolve()
    if upload_dir != target.parent:
        raise ValueError("上传资源不能越过当前任务 uploads 目录")
    if root not in target.parents:
        raise ValueError("上传资源不能越过 workspace root")
    return target


def normalize_artifact_name(name: str) -> str:
    candidate = Path(name)
    if candidate.name != name or name in {"", ".", ".."}:
        raise ValueError("产物名不能包含路径")
    return name


def assert_source_contracts() -> None:
    storage = (REPO_ROOT / "backend/app/storage.py").read_text(encoding="utf-8")
    resources = (REPO_ROOT / "backend/app/execution/resources.py").read_text(encoding="utf-8")
    files_api = (REPO_ROOT / "backend/app/api/files.py").read_text(encoding="utf-8")
    artifacts_api = (REPO_ROOT / "backend/app/api/artifacts.py").read_text(encoding="utf-8")
    frontend_upload = (REPO_ROOT / "frontend/app/file-upload.ts").read_text(encoding="utf-8")
    task_state = (REPO_ROOT / "frontend/app/task-state.ts").read_text(encoding="utf-8")

    for extension in SUPPORTED_UPLOADS:
        assert f'"{extension}"' in frontend_upload or f'"{extension}"' in storage
    for tool_name in [
        "list_uploaded_resources",
        "inspect_resource",
        "read_resource_text",
        "read_resource_table",
    ]:
        assert tool_name in resources
    assert "storage.save_uploads" in files_api
    assert "runner.is_running" in files_api
    assert '@router.get("/{task_id}/artifacts/{artifact_name}")' in artifacts_api
    assert '@router.get("/{task_id}/runs/{run_id}/artifacts/{artifact_name}")' in artifacts_api
    assert "assertTrustedArtifactUrl" in task_state
    assert "parseTrustedArtifactPath" in task_state


if __name__ == "__main__":
    root = Path("/tmp/myagent-study")
    assert is_supported_upload("需求文档.docx")
    assert is_supported_upload("报价.xlsx")
    assert not is_supported_upload("secret.exe")

    safe = resolve_task_upload_path(root, "task-1", "a.md")
    assert str(safe).endswith("/task-1/uploads/a.md")

    try:
        resolve_task_upload_path(root, "task-1", "../other-task/secret.md")
    except ValueError:
        pass
    else:
        raise AssertionError("路径穿越必须被拒绝")

    assert normalize_artifact_name("report.html") == "report.html"
    assert_source_contracts()
    print("OK: 你已经理解上传资源和产物名称的安全边界。")
