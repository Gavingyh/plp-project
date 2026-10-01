"""
Tests for the shell scripts in scripts/.

Shell is easy to break in ways nothing catches until someone runs it, so these
cover the two properties that would hurt most:

  - every script parses (`bash -n`), because a typo in a rarely-run script
    surfaces at the worst possible moment;
  - start.sh refuses a port it does not own. Port 8000 on a development
    machine is as likely to be another project's server as it is to be
    this one's, and "start my API" must never take down somebody else's
    work. This is the one behaviour where being wrong is destructive rather
    than merely annoying.

Nothing here starts a real service.
"""

import os
import socket
import subprocess

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
SHELL_SCRIPTS = sorted(f for f in os.listdir(SCRIPTS_DIR) if f.endswith(".sh"))

# If this fires, the glob is wrong rather than the repo being empty.
assert SHELL_SCRIPTS, f"no .sh files found in {SCRIPTS_DIR}"


@pytest.mark.parametrize("script", SHELL_SCRIPTS)
def test_script_parses(script):
    result = subprocess.run(["bash", "-n", os.path.join(SCRIPTS_DIR, script)],
                            capture_output=True, text=True)
    assert result.returncode == 0, f"{script} failed to parse:\n{result.stderr}"


@pytest.mark.parametrize("script", SHELL_SCRIPTS)
def test_script_is_executable(script):
    assert os.access(os.path.join(SCRIPTS_DIR, script), os.X_OK), (
        f"{script} is not executable - `chmod +x scripts/{script}`")


@pytest.mark.parametrize("script", ["start.sh", "stop.sh"])
def test_unknown_target_is_rejected(script):
    """A typo'd service name must fail loudly, not silently do nothing."""
    result = subprocess.run([os.path.join(SCRIPTS_DIR, script), "notaservice"],
                            capture_output=True, text=True, cwd=BASE_DIR)
    assert result.returncode != 0
    assert "unknown target" in result.stderr.lower()


def test_stop_is_idempotent():
    """stop.sh must succeed and say so when there is nothing to stop, so it is
    safe to call unconditionally in a teardown.

    Deliberately asserts on the SECOND call rather than the first. The first
    may legitimately stop a service a developer happens to have running, and a
    test that assumed otherwise failed spuriously exactly once for that reason.
    Running it twice tests the contract without depending on machine state.
    """
    env = {**os.environ, "PLP_API_PORT": "8009"}
    first = subprocess.run([os.path.join(SCRIPTS_DIR, "stop.sh"), "api"],
                           capture_output=True, text=True, cwd=BASE_DIR, env=env)
    assert first.returncode == 0, first.stderr

    second = subprocess.run([os.path.join(SCRIPTS_DIR, "stop.sh"), "api"],
                            capture_output=True, text=True, cwd=BASE_DIR, env=env)
    assert second.returncode == 0, second.stderr
    assert "not running" in second.stdout.lower()
    assert not os.path.exists(os.path.join(BASE_DIR, "data", "run", "api.pid"))


def test_start_refuses_a_port_it_does_not_own():
    """The destructive-mistake guard: bind a port ourselves, then confirm
    start.sh declines it and names the occupant instead of killing it."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = str(sock.getsockname()[1])
    try:
        result = subprocess.run(
            [os.path.join(SCRIPTS_DIR, "start.sh"), "api"],
            capture_output=True, text=True, cwd=BASE_DIR,
            env={**os.environ, "PLP_API_PORT": port},
        )
        assert result.returncode != 0, "start.sh started on an occupied port"
        assert "already in use" in result.stderr.lower()
        # The socket must still be ours afterwards.
        assert sock.fileno() != -1
    finally:
        sock.close()

    # And no pid file was left behind claiming a service that never started.
    assert not os.path.exists(os.path.join(BASE_DIR, "data", "run", "api.pid"))
