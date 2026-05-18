import sys
import os
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


class LoadingCtx:
    def __init__(self, exit_cb):
        self.exit_cb = exit_cb

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False
        # self.exit_cb()


class UI:
    def __init__(self, *, history_file, debug=False):
        self.progress = Progress(
            SpinnerColumn(), TextColumn("{task.description}"), transient=True
        )
        self.task_id = self.progress.add_task("", total=None)
        self.console = Console()
        self.history = FileHistory(history_file)
        self.debug = debug

    def __enter__(self):
        self.progress.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False
        self.progress.stop()

    @classmethod
    def from_env(cls):
        return cls(
            history_file=os.environ.get(
                "CLAUDIA_HISTORY", os.path.expanduser("~/.claudia_history")
            ),
            debug=os.environ.get("CLAUDIA_DEBUG") in ["1", "true"],
        )

    def loading(self, text):
        self.progress.update(self.task_id, description=f"[cyan]{text}[/cyan]")
        return LoadingCtx(self.progress.stop)

    def debug(self, text):
        if self.debug:
            self.progress.stop()
            self.console.print(text, style="dim")
            self.progress.start()

    def info(self, text):
        self.console.print(Panel.fit(Text.from_markup(text), title="Info"))

    def handle_exception(self):
        return HandleException(console=self.console, spinner=self)

    def prompt_suggest_diff(self, *, diff, on_accept):
        pass

    def answer(self, answer):
        self.progress.stop()
        self.console.print(f"[cyan]Claudia> {answer}[/cyan]")
        self.progress.start()

    def prompt(self):
        self.progress.stop()
        try:
            p = prompt("You> ", history=self.history)
        except (EOFError, KeyboardInterrupt):
            return None
        self.loading("")
        self.progress.start()
        return p

    def bye(self):
        self.progress.stop()
        self.console.print("[cyan]Claudia> Goodbye")

    def hello(self):
        self.progress.stop()
        self.console.print("[cyan]Claudia> Hello, how can I help.")
        self.progress.start()
