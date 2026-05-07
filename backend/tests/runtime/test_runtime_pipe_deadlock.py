import subprocess
import sys
from pathlib import Path
from threading import Thread

import pytest

from app.runtime import CancellationController, run_cancellable_command


class TestRunCancellableCommandPipeDeadlock:
    """Regression tests for Issue #29: subprocess pipe deadlock with large output."""

    def test_large_output_does_not_deadlock(self, tmp_path: Path) -> None:
        """A command producing 1MB of stdout should complete without hanging."""
        controller = CancellationController()
        # Produce ~1MB of output without newlines to stress the pipe buffer.
        result = run_cancellable_command(
            [
                sys.executable,
                "-c",
                "print('x' * 1_000_000)",
            ],
            cwd=str(tmp_path),
            timeout=30.0,
            controller=controller,
        )
        assert result.returncode == 0
        assert len(result.stdout) >= 1_000_000

    def test_cancel_terminates_process(self, tmp_path: Path) -> None:
        """Cancelling the controller must terminate the subprocess promptly."""
        controller = CancellationController()
        outcome: dict[str, str] = {}

        def run_command() -> None:
            try:
                run_cancellable_command(
                    [sys.executable, "-c", "import time; time.sleep(10)"],
                    cwd=str(tmp_path),
                    timeout=120,
                    controller=controller,
                )
            except RuntimeError as exc:
                outcome["error"] = str(exc)

        thread = Thread(target=run_command)
        thread.start()
        # Give the command time to start.
        import time
        time.sleep(0.2)
        controller.cancel()
        thread.join(timeout=3)

        assert not thread.is_alive()
        assert "取消" in outcome["error"]
