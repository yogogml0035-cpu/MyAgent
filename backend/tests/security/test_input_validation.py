"""Tests for input validation hardening in storage and tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.permissions import PermissionPolicy
from app.storage import TaskStorage
from app.tools import WorkspaceTools


class TestTaskDirValidation:
    """Verify task_dir rejects empty and relative-path task IDs."""

    def _make_storage(self, tmp_path: Path) -> TaskStorage:
        return TaskStorage(tmp_path / "tasks")

    def test_empty_string_rejected(self, tmp_path: Path) -> None:
        storage = self._make_storage(tmp_path)
        with pytest.raises(ValueError, match="任务 ID 不能为空"):
            storage.task_dir("")

    def test_dot_rejected(self, tmp_path: Path) -> None:
        storage = self._make_storage(tmp_path)
        with pytest.raises(ValueError, match="任务 ID 不能为空或相对路径"):
            storage.task_dir(".")

    def test_dotdot_rejected(self, tmp_path: Path) -> None:
        storage = self._make_storage(tmp_path)
        with pytest.raises(ValueError, match="任务 ID 不能为空或相对路径"):
            storage.task_dir("..")

    def test_valid_task_id_accepted(self, tmp_path: Path) -> None:
        storage = self._make_storage(tmp_path)
        result = storage.task_dir("abc-123")
        assert result.name == "abc-123"


class TestFullTextSearchSuffixValidation:
    """Verify full_text_search rejects disallowed suffixes."""

    def _make_tools(self, tmp_path: Path) -> WorkspaceTools:
        policy = PermissionPolicy(workspace_root=tmp_path)
        return WorkspaceTools(
            workspace_root=tmp_path,
            policy=policy,
            tavily_api_key=None,
        )

    def test_disallowed_suffix_rejected(self, tmp_path: Path) -> None:
        tools = self._make_tools(tmp_path)
        with pytest.raises(ValueError, match="不支持的搜索后缀"):
            tools.full_text_search("test", suffix=".py")

    def test_disallowed_suffix_exe(self, tmp_path: Path) -> None:
        tools = self._make_tools(tmp_path)
        with pytest.raises(ValueError, match="不支持的搜索后缀"):
            tools.full_text_search("test", suffix=".exe")

    def test_md_suffix_allowed(self, tmp_path: Path) -> None:
        tools = self._make_tools(tmp_path)
        # No files, but should not raise
        results = tools.full_text_search("test", suffix=".md")
        assert isinstance(results, list)

    def test_json_suffix_allowed(self, tmp_path: Path) -> None:
        tools = self._make_tools(tmp_path)
        results = tools.full_text_search("test", suffix=".json")
        assert isinstance(results, list)

    def test_txt_suffix_allowed(self, tmp_path: Path) -> None:
        tools = self._make_tools(tmp_path)
        results = tools.full_text_search("test", suffix=".txt")
        assert isinstance(results, list)
