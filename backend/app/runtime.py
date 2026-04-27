from __future__ import annotations

import os
import signal
import subprocess
import time
from concurrent.futures import Future
from subprocess import Popen
from threading import Event, RLock


class CancellationController:
    def __init__(self) -> None:
        self.event = Event()
        self._lock = RLock()
        self._futures: set[Future] = set()
        self._processes: set[Popen] = set()

    def is_cancelled(self) -> bool:
        return self.event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise RuntimeError("Task was cancelled")

    def register_future(self, future: Future) -> None:
        with self._lock:
            self._futures.add(future)
            if self.is_cancelled():
                future.cancel()

    def unregister_future(self, future: Future) -> None:
        with self._lock:
            self._futures.discard(future)

    def register_process(self, process: Popen) -> None:
        with self._lock:
            self._processes.add(process)
            if self.is_cancelled():
                self._terminate_process(process)

    def unregister_process(self, process: Popen) -> None:
        with self._lock:
            self._processes.discard(process)

    def cancel(self) -> None:
        with self._lock:
            self.event.set()
            futures = list(self._futures)
            processes = list(self._processes)
        for future in futures:
            future.cancel()
        for process in processes:
            self._terminate_process(process)

    def _terminate_process(self, process: Popen) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "nt":
                process.terminate()
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            _wait_short(process, timeout=2.0)
        except Exception:
            pass
        if process.poll() is None:
            try:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except Exception:
                process.kill()


def _wait_short(process: Popen, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)


def run_cancellable_command(
    command: list[str],
    *,
    cwd: str,
    timeout: float,
    controller: CancellationController,
) -> subprocess.CompletedProcess[str]:
    controller.raise_if_cancelled()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=os.name != "nt",
    )
    controller.register_process(process)
    try:
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            if controller.is_cancelled():
                controller.cancel()
                raise RuntimeError("Command cancelled")
            if time.monotonic() > deadline:
                controller.cancel()
                raise TimeoutError(f"Command timed out after {timeout} seconds")
            time.sleep(0.05)
        stdout, stderr = process.communicate()
        if controller.is_cancelled():
            raise RuntimeError("Command cancelled")
        return subprocess.CompletedProcess(command, process.returncode or 0, stdout, stderr)
    finally:
        controller.unregister_process(process)
