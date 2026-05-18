import sys
import subprocess

from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.prompt import Confirm


class HandleException:
    def __init__(self, *, console, spinner):
        self.console = console
        self.spinner = spinner

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            try:
                raise
            except subprocess.CalledProcessError as exc:
                self.spinner.stop()
                self.console.print("stodout:", exc.stdout)
                self.console.print("stderr:", exc.stderr)
                self.console.print("claudia error:", exc, style="bold red")
                sys.exit(1)
            except OSError as exc:
                self.console.print("claudia error:", exc, style="bold red")
                sys.exit(1)


class HandleExit:
    def __init__(self, exit_cb):
        self.exit_cb = exit_cb

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False
        self.exit_cb.stop()


class TUI:
    def __init__(self, *, history_file, action_handler, debug=False):
        self.progress = Progress(
            SpinnerColumn(), TextColumn("{task.description}"), transient=True
        )
        self.task_id = self.progress.add_task("Spinning...", total=None)
        self.console = Console()
        self.history = FileHistory(history_file)
        self.action_handler = action_handler

    def loading(self, text):
        self.progress.update(self.task_id, description=f"[cyan]{text}[/cyan]")
        return HandleExit(self.progress.stop)

    def debug(self, text):
        self.progress.stop()
        self.console.print(text, style="dim")
        self.progress.start()

    def info(self, text):
        self.console.print(Panel.fit(Text.from_markup(text), title="Info"))

    def handle_exception(self):
        return HandleException(console=self.console, spinner=self)

    def suggest_diff(self, *, diff, on_accept):
        pass

    def _chat_answer(self, answer):
        self.progress.stop()
        self.console.print(f"[cyan]Claudia> {answer}[/cyan]")
        self.progress.start()

    def _chat_input(self):
        self.progress.stop()
        return prompt("You> ", history=self.history)
        self.progress.stop()

    def _bye(self):
        self.progress.stop()
        self.spinner.stop()
        self.console.print("[cyan]Claudia> Goodbye")

    def loop(self):
        self.progress.stop()
        self.console.print("[cyan]Claudia> Hello, how can I help.")
        self.progress.start()
        while True:
            try:
                user_input = self._chat_input()
            except (KeyboardInterrupt, EOFError):
                self._bye()
                return
            response = self.action_handler.respond(user_input)
            self._chat_answer(response)
