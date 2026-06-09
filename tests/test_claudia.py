from pathlib import Path
import tempfile

from .utils import MockUI

from claudia import Claudia


from functools import wraps


class Claudia(Claudia):
    def get_ui(self):
        return MockUI()

    def get_prompts(self):
        return ["Hello"]


def test_does_not_fail():
    claudia = Claudia()

    @claudia.patch()
    def get_tools(self):
        return []

    @claudia.patch()
    def get_prompts(self):
        return ['Emit "hi123"']

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
