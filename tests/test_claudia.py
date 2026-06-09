from claudia import Claudia
from .utils import TestClaudiaMixin
from claudia import tools
import tempfile
from pathlib import Path

from functools import wraps


def patch(instance):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(instance, *args, **kwargs)

        setattr(instance, func.__name__, wrapper)

        return wrapper

    return decorator


class Claudia(TestClaudiaMixin, Claudia):
    pass


def test_does_not_fail():
    claudia = Claudia()
    claudia.start()


def test_write_file_then_sync_back(subtests):
    with tempfile.TemporaryDirectory() as app_dir:
        claudia = Claudia(app_dir=app_dir)
        app_dir = Path(app_dir)

        @patch(claudia)
        def get_response(self, *, conversation, prompt):
            for t in self.tools:
                if isinstance(t, tools.CoderToolbox):
                    t.write_file("test.txt", prompt, "test")

            with subtests.test("a tmpdir is used for changes"):
                assert Path(app_dir).resolve() != self.app_dir

            with subtests.test("File is written at working tmpdir"):
                assert self.app_dir.joinpath("test.txt").exists()

            with subtests.test("Written file does not exist at main app dir yet"):
                assert not app_dir.joinpath("test.txt").exists()

        claudia.start()

        with subtests.test("File is written at main app dir"):
            assert app_dir.joinpath("test.txt").exists()
