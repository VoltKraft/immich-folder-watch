"""Own the native vstest launcher and its testhost for one disposable backup exchange."""

from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import time


DRAIN_SECONDS = 2
STOP_SECONDS = 5


@contextmanager
def _cleanup(action):
    try:
        yield
    except BaseException as primary:
        try:
            action()
        except BaseException as error:
            primary.add_note(f"Test process cleanup: {error!r}")
        raise
    else:
        action()


class _SessionLeader(subprocess.Popen):
    """Keep the exited leader waitable so its session ID cannot be recycled during cleanup."""

    def _observe(self, flags):
        status = os.waitid(os.P_PID, self.pid, os.WEXITED | os.WNOWAIT | flags)
        if status:
            self.returncode = status.si_status if status.si_code == os.CLD_EXITED else -status.si_status
        return self.returncode

    def poll(self):
        return self._observe(os.WNOHANG) if self.returncode is None else self.returncode

    def wait(self, timeout=None):
        if self.returncode is not None:
            return self.returncode
        if timeout is None:
            return self._observe(0)
        deadline = time.monotonic() + timeout
        while self.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(self.args, timeout)
            time.sleep(min(.025, remaining))
        return self.returncode


def _live_session(session, stop):
    """Check only processes in the pinned session, including descendants in another process group."""
    live = False
    for name in os.listdir("/proc"):
        if not name.isdecimal():
            continue
        pid = int(name)
        try:
            if os.getsid(pid) != session:
                continue
            fd = os.pidfd_open(pid)
            try:
                poller = select.poll()
                poller.register(fd, select.POLLIN)
                if os.getsid(pid) != session or poller.poll(0):
                    continue
                if not stop:
                    return True
                live = True
                signal.pidfd_send_signal(fd, signal.SIGKILL)
            finally:
                os.close(fd)
        except ProcessLookupError:
            continue
    return live


def _drain_session(session, timeout, *, stop=False):
    deadline = time.monotonic() + timeout
    while _live_session(session, stop):
        if time.monotonic() >= deadline:
            return False
        time.sleep(.025)
    return True


def _finish_linux(process):
    # Check child ownership before any signal. WNOWAIT also pins an already exited leader.
    process._observe(os.WNOHANG)

    def reap():
        process.wait(timeout=STOP_SECONDS)
        if os.waitpid(process.pid, os.WNOHANG)[0] != process.pid:
            raise RuntimeError("Could not reap the original test session leader")

    def terminate():
        os.killpg(process.pid, signal.SIGKILL)
        if not _drain_session(process.pid, STOP_SECONDS, stop=True):
            raise RuntimeError("The private test session still has live processes after termination")

    with _cleanup(reap):
        try:
            try:
                process.wait(timeout=DRAIN_SECONDS)
            except subprocess.TimeoutExpired:
                pass
            else:
                # The leader can no longer introduce a new testhost after this scan starts.
                if _drain_session(process.pid, DRAIN_SECONDS):
                    return
        except BaseException:
            with _cleanup(terminate):
                raise
        terminate()
        raise RuntimeError("The private test session required forced cleanup")


def _windows_api():
    source = Path(__file__).resolve().parents[1] / "windows-performance/native.py"
    spec = importlib.util.spec_from_file_location("ifw_worker_win32", source)
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    return native.Win32(), native.checked


@contextmanager
def _windows_process(args, options):
    exe = shutil.which(os.fspath(args[0]), path=options["env"].get("PATH"))
    if exe is None:
        raise FileNotFoundError(args[0])
    exe = Path(exe).resolve(strict=True)
    api, checked = _windows_api()
    job = api.new_job()
    with _cleanup(lambda: checked(api.close(job))):
        process = subprocess.Popen([exe, *args[1:]], creationflags=4, **options)  # CREATE_SUSPENDED
        assigned = False

        def finish():
            if not assigned:
                process.kill()
            forced = not api.wait_job_empty(job, DRAIN_SECONDS)
            if forced:
                checked(api.terminate_job(job, 1))
                if not api.wait_job_empty(job, STOP_SECONDS):
                    raise RuntimeError("The owned test job still has live processes after termination")
            process.wait(timeout=STOP_SECONDS)
            if forced:
                raise RuntimeError("The owned test job required forced cleanup")

        with _cleanup(finish):
            api.assign_suspended(job, process, exe)
            assigned = True
            api.resume_owned_process(process.pid)
            yield process


@contextmanager
def test_process(args, *, cwd, env, log):
    """Yield the directly launched process and require natural exit of its fixture session or job."""
    options = dict(cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    if sys.platform == "win32":
        with _windows_process(args, options) as process:
            yield process
    elif sys.platform == "linux":
        process = _SessionLeader(args, start_new_session=True, **options)
        with _cleanup(lambda: _finish_linux(process)):
            yield process
    else:
        raise OSError("Worker activity assessment requires native Windows or Linux")
