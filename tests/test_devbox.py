"""
Tests for DevBoxToolbox - runs real commands in an alpine container.
Requires: docker
"""

from claudia.tools.devbox import DevBoxToolbox


def test_cmd_true():
    """Verify the toolbox starts and 'true' returns exit status 0."""
    tb = DevBoxToolbox(ui=None, volume="/tmp", base_image="alpine")
    out = tb.cmd("true", "test true")
    assert out.endswith("[Exit status: 0]")


def test_cmd_echo():
    """Verify cmd returns stdout correctly."""
    tb = DevBoxToolbox(ui=None, volume="/tmp", base_image="alpine")
    out = tb.cmd("echo hello", "test echo")
    assert "hello" in out
    assert out.endswith("[Exit status: 0]")


def test_cmd_false():
    """Verify non-zero exit status is captured."""
    tb = DevBoxToolbox(ui=None, volume="/tmp", base_image="alpine")
    out = tb.cmd("false", "test false")
    assert out.endswith("[Exit status: 1]")
