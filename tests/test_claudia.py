from pathlib import Path
import tempfile

from .utils import MockUI

from claudia import Claudia
from claudia import tools


from functools import wraps


class Claudia(Claudia):
    def get_ui(self):
        return MockUI()

    def get_loop(self):
        return False

    def patch(self):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(self, *args, **kwargs)

            setattr(self, func.__name__, wrapper)

            return wrapper

        return decorator


def test_does_not_fail():
    claudia = Claudia()

    @claudia.patch()
    def get_tools(self):
        return []

    @claudia.patch()
    def ask_prompt(self):
        return r'Emit "hi123"'

    @claudia.patch()
    def on_response(self, prompt):
        assert "hi123" in prompt.lower(), "LLM did not follow instructions or bad code"

    claudia.start()


def test_sync_back_file(subtests):
    with tempfile.TemporaryDirectory() as app_dir:
        claudia = Claudia(app_dir=app_dir)
        app_dir = Path(app_dir)

        @claudia.patch()
        def answer(self, prompt):
            with open(self.app_dir.joinpath("test.txt"), "w") as f:
                f.write("content")

            with subtests.test("a tmpdir is used for changes"):
                assert Path(app_dir).resolve() != self.app_dir

            with subtests.test("File is written at working tmpdir"):
                assert self.app_dir.joinpath("test.txt").exists()

            with subtests.test("Written file does not exist at main app dir yet"):
                assert not app_dir.joinpath("test.txt").exists()

        claudia.start()

        with subtests.test("File is written at main app dir"):
            assert app_dir.joinpath("test.txt").exists()


def test_coder_toolbox(subtests):
    claudia = Claudia()
    claudia.warmup()
    tool = None
    for tool in claudia.tools:
        if isinstance(tool, tools.CoderToolbox):
            break

    with subtests.test("can write file"):
        assert tool.write_file("test.txt", "content", "step description") is None
        assert claudia.app_dir.joinpath("test.txt").exists(), (
            "Written does not file exist"
        )

    with subtests.test("read files"):
        assert tool.read_files(["test.txt"], "step description") == {
            "test.txt": "content"
        }
        assert tool.read_files("test.txt", "step description") == {
            "error": "filenames must be a list"
        }
