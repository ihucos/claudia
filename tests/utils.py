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
        return "hello"

    def ask_diff(self, diff, stat=None):
        return True

    def diff_applied_msg(self, cmd, dir):
        return

    def __enter__(self):
        return

    def __exit__(self, exc_type, exc_val, exc_tb):
        return


class TestClaudiaMixin:
    def get_ui(self):
        return MockUI()

    def get_loop(self):
        return False

    def get_conversation(self):
        return

    def get_response(self, *, conversation, prompt):
        return "Say hello"
