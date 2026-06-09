from claudia import Claudia


class MockUI:
    def catch(self):
        return self

    def loading(self, text):
        return self

    def debug(self, text):
        return

    def info(self, header, text):
        return

    def answer(self, answer):
        return

    def bye(self):
        return

    def hello(self):
        return

    def prompt(self):
        return

    def ask_diff(self, diff, stat=None):
        return

    def diff_applied_msg(self, cmd, dir):
        return

    def __enter__(self):
        return

    def __exit__(self, exc_type, exc_val, exc_tb):
        return

    def get_response(self, conversation, prompt):
        return f"echo {prompt}"

    def ask_prompt(self):
        return "hello"


def test_simple():
    claudia = Claudia(ui=MockUI())
    claudia.run()
