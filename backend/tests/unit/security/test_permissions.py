from __future__ import annotations

from pathlib import Path

from app.permissions import ActionDecision, PermissionPolicy


class TestPermissionPolicyInit:
    def test_init_resolves_workspace(self, tmp_path):
        policy = PermissionPolicy(tmp_path)
        assert policy.workspace_root == tmp_path.resolve()


class TestClassifyCommand:
    def test_allowed_command_pytest(self, tmp_path):
        policy = PermissionPolicy(tmp_path)
        decision = policy.classify_command(["pytest"])
        assert decision.status == "allow"

    def test_allowed_command_uv_run_pytest(self, tmp_path):
        policy = PermissionPolicy(tmp_path)
        decision = policy.classify_command(["uv", "run", "pytest"])
        assert decision.status == "allow"

    def test_denied_command_rm(self, tmp_path):
        policy = PermissionPolicy(tmp_path)
        decision = policy.classify_command(["rm", "-rf", "/"])
        assert decision.status == "deny"

    def test_denied_empty_command(self, tmp_path):
        policy = PermissionPolicy(tmp_path)
        decision = policy.classify_command([])
        assert decision.status == "deny"

    def test_string_command_input(self, tmp_path):
        policy = PermissionPolicy(tmp_path)
        decision = policy.classify_command("pytest -q")
        assert decision.status == "allow"


class TestClassifyPathAccess:
    def test_within_workspace_allowed(self, tmp_path):
        policy = PermissionPolicy(tmp_path)
        target = tmp_path / "some" / "file.txt"
        decision = policy.classify_path_access(target)
        assert decision.status == "allow"

    def test_outside_workspace_needs_confirm(self, tmp_path):
        policy = PermissionPolicy(tmp_path)
        decision = policy.classify_path_access(Path("/tmp/other/file.txt"))
        assert decision.status == "confirm"
