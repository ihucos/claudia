from .utils import MockUI
from claudia import tools
import pytest


@pytest.fixture
def toolbox(tmp_path):
    return tools.CoderToolbox(ui=MockUI(), workdir=tmp_path)


def test_write_then_read(toolbox, tmp_path):
    assert toolbox.write_file("test.txt", "content", "writing") is None
    assert (tmp_path / "test.txt").read_text() == "content"
    assert toolbox.read_files(["test.txt"], "reading") == {"test.txt": "content"}


def test_write_creates_nested_dirs(toolbox, tmp_path):
    toolbox.write_file("a/b/c.txt", "deep", "writing")
    assert (tmp_path / "a" / "b" / "c.txt").read_text() == "deep"


def test_read_missing_file_returns_error(toolbox):
    assert toolbox.read_files(["nope.txt"], "reading") == {
        "nope.txt": {"error": "File not found"}
    }


def test_read_files_requires_a_list(toolbox):
    assert toolbox.read_files("test.txt", "reading") == {
        "error": "filenames must be a list"
    }


def test_write_outside_workdir_is_rejected(toolbox, tmp_path):
    result = toolbox.write_file("../escape.txt", "evil", "writing")
    assert result == {"error": "Disallowed filename"}
    # Nothing was written outside the sandbox.
    assert not (tmp_path.parent / "escape.txt").exists()


def test_read_outside_workdir_is_rejected(toolbox):
    assert toolbox.read_files(["../../etc/passwd"], "reading") == {
        "../../etc/passwd": {"error": "Disallowed filename"}
    }


def test_delete_outside_workdir_is_rejected(toolbox):
    assert toolbox.delete("../../etc/passwd", "deleting") == {
        "error": "Disallowed filename"
    }


def test_delete(toolbox, tmp_path):
    toolbox.write_file("test.txt", "content", "writing")
    assert toolbox.delete("test.txt", "deleting") is None
    assert not (tmp_path / "test.txt").exists()


def test_delete_missing_file(toolbox):
    assert toolbox.delete("nope.txt", "deleting") == {"error": "File not found"}


def test_delete_tree(toolbox, tmp_path):
    toolbox.write_file("a/b/c.txt", "content", "writing")
    assert toolbox.delete("a", "deleting") is None
    assert not (tmp_path / "a").exists()


def test_move(toolbox, tmp_path):
    toolbox.write_file("a/b/c.txt", "content", "writing")
    assert toolbox.move("a/b/c.txt", "a/b/d.txt", "moving") is None
    assert (tmp_path / "a" / "b" / "d.txt").read_text() == "content"
    assert not (tmp_path / "a" / "b" / "c.txt").exists()


def test_move_missing_file(toolbox):
    assert toolbox.move("a/b/c.txt", "a/b/d.txt", "moving") == {
        "error": "File not found"
    }


def test_move_outside_workdir_is_rejected(toolbox):
    assert toolbox.move("../../etc/passwd", "/tmp/a", "moving") == {
        "error": "Disallowed filename"
    }


def test_copy(toolbox, tmp_path):
    toolbox.write_file("a/b/c.txt", "content", "writing")
    assert toolbox.copy("a/b/c.txt", "a/b/d.txt", "copying") is None
    assert (tmp_path / "a" / "b" / "c.txt").read_text() == "content"
    assert (tmp_path / "a" / "b" / "d.txt").read_text() == "content"
