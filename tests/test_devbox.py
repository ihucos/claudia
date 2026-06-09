"""
Crucial (integration) tests for the DevBox tool.

These tests require a running Docker daemon and actually create/manage
real containers, because the whole point of DevBox is talking to Docker.
"""
import subprocess
from claudia.tools.devbox import DevBox, DevBoxToolbox

from .utils import MockUI


def _clean(name):
    """Remove a container if it exists (best-effort)."""
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def test_devbox_create_start_run_and_cmd():
    """
    End-to-end: create a container, start it, exec a command,
    and verify the DevBoxToolbox.cmd() method works.
    """
    box = DevBox(volume="/tmp", base_image="alpine")
    _clean(box.name)

    try:
        # --- DevBox lifecycle ---
        box.create()
        assert box.exists()

        # --- DevBox.run ---
        proc = box.run(["/bin/sh", "-c", "echo hello_from_container"])
        assert proc.returncode == 0
        assert "hello_from_container" in proc.stdout

        # --- DevBoxToolbox.cmd ---
        toolbox = DevBoxToolbox(ui=MockUI(), devbox=box)
        result = toolbox.cmd("echo hello_from_toolbox", "Testing toolbox")
        assert result["exit_status"] == 0
        assert "hello_from_toolbox" in result["stdout"]

        # --- Toolbox propagates failures ---
        result = toolbox.cmd("exit 42", "Testing failure propagation")
        assert result["exit_status"] == 42
        assert result["stdout"] == ""
        assert result["stderr"] == ""

    finally:
        _clean(box.name)


def test_devbox_start_or_create_reuses_existing_container():
    """
    Starting a container that already exists should work without error
    (idempotent lifecycle).
    """
    box = DevBox(volume="/tmp", base_image="alpine")
    _clean(box.name)

    try:
        box.create()
        name_before = box.name
        # Call start_or_create on an existing container
        box.start_or_create()
        # Name should be same, container should still be running
        assert box.name == name_before
        assert box.exists()

        proc = box.run(["/bin/sh", "-c", "echo reused"])
        assert proc.returncode == 0
        assert "reused" in proc.stdout

    finally:
        _clean(box.name)


def test_devbox_run_returns_exit_code_and_output():
    """
    DevBox.run() should correctly return stdout, stderr, and the exit code,
    including for failing commands.
    """
    box = DevBox(volume="/tmp", base_image="alpine")
    _clean(box.name)

    try:
        box.create()

        # Success
        proc = box.run(["/bin/sh", "-c", "printf out; printf err >&2"])
        assert proc.returncode == 0
        assert proc.stdout == "out"
        assert proc.stderr == "err"

        # Failure
        proc = box.run(
            ["/bin/sh", "-c", "printf fail_out; printf fail_err >&2; exit 1"]
        )
        assert proc.returncode == 1
        assert proc.stdout == "fail_out"
        assert proc.stderr == "fail_err"

    finally:
        _clean(box.name)
